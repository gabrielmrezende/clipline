import copy
import json
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from PIL import Image

from esteira import rede, wikimedia
from esteira.cartao import gerar_cartao
from esteira.cortar import TRABALHO, ler_aprovados, pasta_de_trabalho, pasta_do_corte
from esteira.episodio import slug
from esteira.folhas import montar_folha
from esteira.imagens import EXTENSOES
from esteira.ingestao import encaixar_ia
from esteira.modelos import Corte
from esteira.pedidos import ARQUIVO, Momento, ajustar_tempos, gravar_pedidos, ler_pedidos, validar_pedidos
from esteira.receita import NOME_ARQUIVO, duracao_principal, ler_receita
from esteira.wikimedia import Consulta

EXTENSOES_FOTO = {".jpg", ".jpeg", ".png", ".webp"}
TIPOS_LEGIVEIS = {"foto": "foto livre", "noticia": "notícia", "ia": "ilustração de IA"}
LISTA_JSON = "lista-imagens.json"
ERRO_ORDEM_IA = "erro: ordem das imagens de IA mudou, rode imagens lista de novo"
ERRO_SEM_LISTA = "erro: rode imagens lista antes de baixar"
ERRO_FORA_DA_LISTA = "erro: corte fora da última lista, rode imagens lista"
ERRO_SEM_MONTAGEM = f"erro: {NOME_ARQUIVO} não encontrado, rode preparar"


class ErroBusca(Exception):
    pass


def nome_arquivo(m: Momento, ext: str) -> str:
    return f"imagens/{m.numero:02d}-{slug(m.nome)}{ext}"


def extensao_foto(url: str) -> str:
    sufixo = Path(url.split("?")[0]).suffix.lower()
    return sufixo if sufixo in EXTENSOES_FOTO else ".jpg"


def _extensao(m: Momento) -> str:
    return ".png" if m.tipo == "noticia" else extensao_foto(m.url)


def _tempo(segundos: float) -> str:
    total = round(segundos * 1000)
    horas, resto = divmod(total, 3_600_000)
    minutos, resto = divmod(resto, 60_000)
    return f"{horas:02d}:{minutos:02d}:{resto // 1000:02d},{resto % 1000:03d}"


def _cortes_com_pedidos(pasta: Path, numeros: set[int] | None) -> list[tuple[Corte, Path]]:
    cortes = []
    for corte in ler_aprovados(pasta):
        if numeros is not None and corte.numero not in numeros:
            continue
        destino = pasta_do_corte(pasta, corte)
        if (destino / TRABALHO / ARQUIVO).exists():
            cortes.append((corte, destino))
    return cortes


def _carregar(destino: Path, pessoas: list[str]) -> tuple[list[Momento], float] | str:
    trabalho = destino / TRABALHO
    if not (trabalho / NOME_ARQUIVO).exists():
        return ERRO_SEM_MONTAGEM
    try:
        duracao = duracao_principal(ler_receita(trabalho))
        momentos = ler_pedidos(trabalho)
    except (OSError, ValueError, KeyError, TypeError) as erro:
        return f"erro: {erro}"
    erros = validar_pedidos(momentos, duracao, pessoas)
    if erros:
        return f"erro: {'; '.join(erros)}"
    return momentos, duracao


def _resultado(alertas: list[str]) -> str:
    return f"ok com alertas: {'; '.join(alertas)}" if alertas else "ok"


def buscar_episodio(
    pasta: Path,
    numeros: set[int] | None,
    pessoas: list[str],
    consultar: Consulta = wikimedia.consultar,
    baixar: Callable[[str, Path], None] = rede.baixar_url,
) -> dict[int, str]:
    resultados: dict[int, str] = {}
    achadas: list[tuple[Corte, Path, list[Momento], dict[int, list]]] = []
    for corte, destino in _cortes_com_pedidos(Path(pasta), numeros):
        carregado = _carregar(destino, pessoas)
        if isinstance(carregado, str):
            resultados[corte.numero] = carregado
            continue
        momentos = carregado[0]
        candidatas = {}
        for posicao, m in enumerate(momentos, 1):
            if m.tipo != "foto" or m.descartar:
                continue
            try:
                candidatas[posicao] = wikimedia.buscar_candidatas(m.busca, consultar)
            except (OSError, ValueError) as erro:
                raise ErroBusca(f"Wikimedia indisponível: {erro}") from erro
        achadas.append((corte, destino, momentos, candidatas))

    for corte, destino, momentos, candidatas in achadas:
        alertas = []
        with tempfile.TemporaryDirectory() as temporaria:
            for posicao, lista in candidatas.items():
                m = momentos[posicao - 1]
                miniaturas: list[Path | None] = []
                for i, c in enumerate(lista, 1):
                    caminho = Path(temporaria) / f"{posicao}-{i}.jpg"
                    try:
                        baixar(c.miniatura, caminho)
                        miniaturas.append(caminho)
                    except Exception:
                        miniaturas.append(None)
                titulo = f"Corte {corte.numero:02d} · momento {posicao} · {m.nome}"
                montar_folha(titulo, lista, miniaturas, pasta_de_trabalho(destino) / "candidatas" / f"{corte.numero:02d}-{posicao}.jpg")
                m.candidatas = [asdict(c) for c in lista]
                m.escolha, m.numero, m.url, m.bytes, m.motivo = None, None, "", None, ""
                if not lista:
                    alertas.append(f"momento {posicao} sem candidata")
        for m in momentos:
            m.numero = None  # o corte precisa de nova lista
        gravar_pedidos(pasta_de_trabalho(destino), momentos)
        resultados[corte.numero] = _resultado(alertas)
    return resultados


def _bloco_imagem(m: Momento) -> str:
    linhas = [
        f"## {m.numero}. {_tempo(m.inicio)} a {_tempo(m.fim)} — {m.nome}",
        f"Tipo: {TIPOS_LEGIVEIS[m.tipo]}",
        f'Fala: "{m.fala}"',
    ]
    if m.tipo == "foto":
        c = m.candidatas[m.escolha - 1]
        linhas += [f"Origem: {c['pagina']}", f"Baixar: {m.url}", f"Autor e licença: {c['autor']}, {c['licenca']}"]
    elif m.tipo == "noticia":
        linhas += ["Origem: cartão do canal", f"Autor e licença: cartão do canal, {m.veiculo}"]
    else:
        linhas += [
            f"Prompt: {m.prompt}",
            "Origem: gerada no ChatGPT (OpenAI) a partir do prompt acima",
            "Autor e licença: ilustração de IA, ChatGPT (OpenAI)",
        ]
    return "\n".join(linhas)


def _gravar_texto(caminho: Path, texto: str) -> None:
    caminho.write_text(texto, "utf-8", newline="\n")


def _ajustados(momentos: list[Momento], duracao: float, excluidos: set[int]) -> tuple[list[Momento], list[str]]:
    copia = copy.deepcopy(momentos)
    for i in excluidos:
        copia[i].descartar = True
    avisos = ajustar_tempos(copia, duracao)
    return copia, avisos


def _listar_um(destino: Path, momentos: list[Momento], duracao: float, medir, consultar) -> str:
    for posicao, m in enumerate(momentos, 1):
        if m.tipo == "foto" and not m.descartar and not (m.escolha and 1 <= m.escolha <= len(m.candidatas)):
            return f"erro: momento {posicao} sem escolha"
    for m in momentos:
        m.numero, m.url, m.bytes = None, "", None
        if not m.descartar:
            m.motivo = ""
    alertas: list[str] = []
    sem_link: set[int] = set()
    for i, m in enumerate(momentos):
        if m.descartar or m.tipo != "foto":
            continue
        try:
            url = wikimedia.url_final(m.candidatas[m.escolha - 1]["titulo"], consultar)
        except (OSError, ValueError) as erro:
            return f"erro: Wikimedia indisponível: {erro}"
        if url is None:
            sem_link.add(i)
            m.motivo = "sem link de download"
            alertas.append(f"momento {i + 1} ({m.nome}) descartado: sem link de download")
            continue
        m.url, m.bytes = url, medir(url)
    copia, avisos = _ajustados(momentos, duracao, sem_link)
    alertas += avisos
    ativos = sorted((c for c in copia if not c.descartar), key=lambda c: c.inicio)
    for numero, c in enumerate(ativos, 1):
        c.numero = numero
    for original, c in zip(momentos, copia):
        original.numero = c.numero
        if c.descartar and not original.descartar and not original.motivo:
            original.motivo = c.motivo
    gravar_pedidos(pasta_de_trabalho(destino), momentos)
    texto = "\n\n".join(_bloco_imagem(c) for c in ativos)
    _gravar_texto(destino / "imagens.md", texto + "\n" if texto else "")
    return _resultado(alertas)


def _linha_lista(m: Momento) -> str:
    cabecalho = f"- {m.numero}. {_tempo(m.inicio)} a {_tempo(m.fim)} — {m.nome} — "
    if m.tipo == "ia":
        return cabecalho + "gerar por IA"
    if m.tipo == "noticia":
        return cabecalho + "cartão do canal"
    arquivo = nome_arquivo(m, _extensao(m)).removeprefix("imagens/")
    tamanho = f"{max(1, round(m.bytes / 1024))} KB" if m.bytes is not None else "tamanho desconhecido"
    c = m.candidatas[m.escolha - 1]
    return cabecalho + f"{arquivo} — Wikimedia Commons: {c['pagina']} — {c['licenca']} — {tamanho}"


def _numerados(momentos: list[Momento]) -> list[Momento]:
    return sorted((m for m in momentos if m.numero is not None), key=lambda m: m.numero)


def _nome_do_episodio(pasta: Path) -> str:
    try:
        dados = json.loads((pasta / "episodio.json").read_text("utf-8"))
        return f"{dados['quadro']} #{int(dados['numero']):02d}"
    except (OSError, ValueError, KeyError, TypeError):
        return pasta.name


def _gravar_episodio(pasta: Path, nome: str, cortes: list[tuple[Corte, Path, list[Momento]]]) -> None:
    secoes, ias, fotos, total = [], [], 0, 0
    for corte, destino, momentos in cortes:
        ativos = _numerados(momentos)
        secoes.append(f"## {destino.name}\n" + "\n".join(_linha_lista(m) for m in ativos))
        for m in ativos:
            if m.tipo == "ia":
                ias.append((corte, m, destino))
            elif m.tipo == "foto":
                fotos += 1
                total += m.bytes or 0
    ordem = [
        {"corte": c.numero, "pasta": d.name, "numero": m.numero, "nome": m.nome, "prompt": m.prompt}
        for c, m, d in ias
    ]
    dados = {"cortes": [destino.name for _, destino, _ in cortes], "ia": ordem}
    _gravar_texto(pasta / LISTA_JSON, json.dumps(dados, ensure_ascii=False, indent=2) + chr(10))
    resumo = f"Total: {fotos} fotos, {round(total / 1_048_576)} MB; {len(ias)} imagens de IA a gerar."
    _gravar_texto(pasta / "lista-imagens.md", f"# Imagens para aprovar: {nome}\n\n" + "\n\n".join(secoes) + f"\n\n{resumo}\n")
    if not ias:
        _gravar_texto(pasta / "prompts-chatgpt.md", f"# Prompts para o ChatGPT: {nome}\n\nNenhuma imagem de IA neste episódio.\n")
        return
    (pasta / "ia-entrada").mkdir(exist_ok=True)
    quantidade = len(ias)
    prompts = "\n\n".join(f"{i}. {m.prompt}" for i, (_, m, _) in enumerate(ias, 1))
    destinos = "\n".join(f"{i} → corte {c.numero:02d}, imagem {m.numero} ({m.nome})" for i, (c, m, _) in enumerate(ias, 1))
    _gravar_texto(pasta / "prompts-chatgpt.md", (
        f"# Prompts para o ChatGPT: {nome}\n\n"
        f"Cole o bloco abaixo numa conversa nova do ChatGPT. Baixe as imagens na ordem (1 a {quantidade}) "
        "para a pasta `ia-entrada/` deste episódio. Pode deixar o nome que o ChatGPT der; a esteira usa a ordem do download.\n\n"
        "```\n"
        f"Gere {quantidade} imagens, uma por resposta, na ordem abaixo. Todas em formato vertical 9:16 (1080x1920), "
        "fotorrealistas, sem nenhum texto, letra, logotipo ou marca d'água, e sem pessoas reais ou reconhecíveis. "
        'Depois de cada imagem, espere eu escrever "próxima".\n\n'
        f"{prompts}\n\n"
        "```\n\n"
        f"## Para onde vai cada imagem\n{destinos}\n"
    ))


def _cortes_da_lista_anterior(pasta: Path) -> set[str]:
    lista = _ler_lista(pasta)
    return set(lista[0]) if lista else set()


def listar_episodio(
    pasta: Path,
    numeros: set[int] | None,
    pessoas: list[str],
    consultar: Consulta = wikimedia.consultar,
    medir: Callable[[str], int | None] = wikimedia.tamanho,
) -> dict[int, str]:
    pasta = Path(pasta)
    resultados: dict[int, str] = {}
    for corte, destino in _cortes_com_pedidos(pasta, numeros):
        carregado = _carregar(destino, pessoas)
        if isinstance(carregado, str):
            resultados[corte.numero] = carregado
            continue
        resultados[corte.numero] = _listar_um(destino, carregado[0], carregado[1], medir, consultar)

    anteriores = _cortes_da_lista_anterior(pasta)
    listados = []
    for corte, destino in _cortes_com_pedidos(pasta, None):
        if resultados.get(corte.numero, "ok").startswith("erro"):
            continue
        if corte.numero not in resultados and destino.name not in anteriores:
            continue  # não reprocessado agora e fora da última lista
        try:
            momentos = ler_pedidos(destino / TRABALHO)
            duracao = duracao_principal(ler_receita(destino / TRABALHO))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not any(m.numero is not None for m in momentos):
            continue
        excluidos = {i for i, m in enumerate(momentos) if m.numero is None and not m.descartar}
        copia, _ = _ajustados(momentos, duracao, excluidos)
        listados.append((corte, destino, copia))
    _gravar_episodio(pasta, _nome_do_episodio(pasta), listados)
    return resultados


def _irmaos(pasta: Path, caminho: Path) -> list[Path]:
    """Imagens com o mesmo nome-base e outra extensão."""
    if not pasta.is_dir():
        return []
    return sorted(
        p for p in pasta.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSOES and p.stem == caminho.stem and p.name != caminho.name
    )


def _conflitos(destino: Path, esperados: dict[str, str], finais: dict[str, str]) -> list[str]:
    """Arquivos de rodadas anteriores com o mesmo número NN- e outro nome, ou outra extensão sem origem registrada."""
    pasta = destino / "imagens"
    if not pasta.is_dir():
        return []
    origens = _ler_origens(pasta)
    return sorted(
        p.name for p in pasta.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSOES and p.name[:3] in esperados and (
            p.stem != esperados[p.name[:3]]
            or (p.name[:3] in finais and p.name != finais[p.name[:3]] and p.name not in origens)
        )
    )


def _baixar_foto(m: Momento, caminho: Path, baixar: Callable[[str, Path], None]) -> bool:
    parcial = caminho.with_name(caminho.name + ".parcial")
    try:
        baixar(m.url, parcial)
        with Image.open(parcial) as imagem:
            imagem.load()
        parcial.replace(caminho)
        return True
    except Exception:  # fronteira de isolamento de um item: qualquer falha vira alerta
        parcial.unlink(missing_ok=True)
        return False


ORIGENS = ".origens.json"


def _origem(m: Momento) -> str:
    return m.url if m.tipo == "foto" else f"cartao|{m.titulo}|{m.veiculo}|{m.data}"


def _ler_origens(pasta: Path) -> dict[str, str]:
    try:
        dados = json.loads((pasta / ORIGENS).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gerar_cartao_seguro(m: Momento, caminho: Path) -> bool:
    parcial = caminho.with_name(caminho.name + ".parcial")
    try:
        gerar_cartao(m.titulo, m.veiculo, m.data, parcial)
        parcial.replace(caminho)
        return True
    except Exception:  # fronteira de isolamento de um item
        return False
    finally:
        parcial.unlink(missing_ok=True)


def _baixar_um(destino: Path, momentos: list[Momento], baixar: Callable[[str, Path], None]) -> str:
    alertas: list[str] = []
    pasta_imagens = destino / "imagens"
    origens = _ler_origens(pasta_imagens)
    anteriores = dict(origens)
    for m in _numerados(momentos):
        if m.tipo == "ia":
            continue
        caminho = destino / nome_arquivo(m, _extensao(m))
        origem = _origem(m)
        if caminho.exists():
            if caminho.name not in origens:
                alertas.append(f"imagem {m.numero}: arquivo existente sem origem registrada, mantido")
                continue
            if origens[caminho.name] == origem:
                continue
        caminho.parent.mkdir(exist_ok=True)
        if m.tipo == "foto":
            ok = _baixar_foto(m, caminho, baixar)
            falha = "download falhou"
        else:
            ok = _gerar_cartao_seguro(m, caminho)
            falha = "cartão falhou"
        if ok:
            origens[caminho.name] = origem
            for irmao in _irmaos(pasta_imagens, caminho):
                if irmao.name in origens:  # criado pela própria esteira
                    irmao.unlink(missing_ok=True)
                    del origens[irmao.name]
        else:
            alertas.append(f"imagem {m.numero}: {falha}")
    if origens != anteriores:
        _gravar_texto(pasta_imagens / ORIGENS, json.dumps(origens, ensure_ascii=False, indent=2) + chr(10))
    quantidade = sum(1 for c in pasta_imagens.glob("*") if c.is_file() and c.suffix.lower() in EXTENSOES)
    return f"ok com alertas: {'; '.join(alertas)}" if alertas else f"ok: {quantidade} imagens"


def _texto_linha(texto: str) -> str:
    return " ".join(str(texto).split())


def _ler_lista(pasta: Path) -> tuple[list[str], list[dict]] | None:
    try:
        dados = json.loads((pasta / LISTA_JSON).read_text("utf-8"))
        cortes, ordem = dados["cortes"], dados["ia"]
        if not isinstance(cortes, list) or not all(isinstance(c, str) for c in cortes):
            return None
        for item in ordem:
            item["corte"], item["pasta"], item["numero"], item["nome"], item["prompt"]
        return cortes, ordem
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _ordem_confere(pasta: Path, ordem: list[dict]) -> bool:
    pedidos: dict[str, list[Momento]] = {}
    for item in ordem:
        if item["pasta"] not in pedidos:
            try:
                pedidos[item["pasta"]] = ler_pedidos(pasta / item["pasta"] / TRABALHO)
            except (OSError, ValueError, KeyError, TypeError):
                return False
        if not any(
            m.tipo == "ia" and m.numero == item["numero"] and m.nome == item["nome"]
            for m in pedidos[item["pasta"]]
        ):
            return False
    return True


def baixar_episodio(
    pasta: Path,
    numeros: set[int] | None,
    baixar: Callable[[str, Path], None] = rede.baixar_url,
) -> dict[int, str]:
    pasta = Path(pasta)
    selecionados = _cortes_com_pedidos(pasta, numeros)
    if not selecionados:
        return {}
    if not (pasta / LISTA_JSON).exists():
        return {corte.numero: ERRO_SEM_LISTA for corte, _ in selecionados}
    lista = _ler_lista(pasta)
    if lista is None or not _ordem_confere(pasta, lista[1]):
        return {corte.numero: ERRO_ORDEM_IA for corte, _ in selecionados}
    listados, ordem = lista
    lidos: dict[Path, list[Momento]] = {}
    erros: dict[int, str] = {}
    pular: set[Path] = set()
    for corte, destino in _cortes_com_pedidos(pasta, None):
        if destino.name not in listados:
            erros[corte.numero] = ERRO_FORA_DA_LISTA
            pular.add(destino)
            continue
        try:
            momentos = ler_pedidos(destino / TRABALHO)
        except (OSError, ValueError, KeyError, TypeError) as erro:
            erros[corte.numero] = f"erro: {erro}"
            pular.add(destino)
            continue
        lidos[destino] = momentos
        esperados = {f"{m.numero:02d}-": f"{m.numero:02d}-{slug(m.nome)}" for m in _numerados(momentos)}
        finais = {
            f"{m.numero:02d}-": Path(nome_arquivo(m, _extensao(m))).name for m in _numerados(momentos) if m.tipo != "ia"
        }
        if not (destino / TRABALHO / NOME_ARQUIVO).exists():
            erros.setdefault(corte.numero, ERRO_SEM_MONTAGEM)
            pular.add(destino)
        elif conflitos := _conflitos(destino, esperados, finais):
            erros.setdefault(corte.numero, f"erro: imagens/ tem arquivo antigo com o mesmo número: {', '.join(conflitos)}")
            pular.add(destino)

    destinos = []
    for item in ordem:
        rotulo = f"{int(item['corte']):02d}\t{item['numero']}\t{_texto_linha(item['nome'])}\t{_texto_linha(item['prompt'])}"
        nome = f"{item['numero']:02d}-{slug(item['nome'])}"
        destinos.append((pasta / item["pasta"], nome, rotulo))
    try:
        encaixar_ia(pasta, destinos, pular)
    except ValueError as erro:
        return {corte.numero: f"erro: {erro}" for corte, _ in selecionados}

    resultados: dict[int, str] = {}
    for corte, destino in selecionados:
        if corte.numero in erros:
            resultados[corte.numero] = erros[corte.numero]
        else:
            resultados[corte.numero] = _baixar_um(destino, lidos[destino], baixar)
    return resultados
