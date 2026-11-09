import copy
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from esteira import caminhos, rede, wikimedia
from esteira.cartao import gerar_cartao, linha_fonte
from esteira.cortar import IMAGENS_SUGERIDAS, TRABALHO, ler_aprovados, pasta_de_trabalho, pasta_do_corte
from esteira.episodio import slug
from esteira.folhas import montar_folha
from esteira.imagens import prefixo_tempo, preparar_foto
from esteira.modelos import Corte
from esteira.pedidos import (
    ARQUIVO, Momento, ajustar_tempos, gravar_pedidos, ler_pedidos, validar_escolhas, validar_pedidos,
)
from esteira.receita import NOME_ARQUIVO, duracao_principal, ler_receita
from esteira.wikimedia import Consulta

SUGERIDAS = "sugeridas.json"
GUIA = "guia.md"
IA = "ia.json"
EXTENSOES_GERADAS = {".jpg", ".png"}
TIPOS_GUIA = {"foto": "foto", "noticia": "notícia", "ia": "IA"}
ERRO_SEM_MONTAGEM = f"erro: {NOME_ARQUIVO} não encontrado, rode preparar"
ERRO_SEM_RESUMO = "erro: rode imagens resumo"
LEMBRETES = """# Imagens sugeridas

- Cada imagem fica de 2 a 5 s na tela.
- Entrada e saída em corte seco, sem transição.
- Zoom lento de cerca de 8% enquanto a imagem está na tela.
- A imagem cobre a legenda enquanto aparece.
- Se usar imagem de IA, avise na publicação.
"""


class ErroBusca(Exception):
    pass


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
                m.escolhas, m.url, m.bytes, m.resumidas, m.motivo = [], [], [], [], ""
                if not lista:
                    alertas.append(f"momento {posicao} sem candidata")
        gravar_pedidos(pasta_de_trabalho(destino), momentos)
        resultados[corte.numero] = _resultado(alertas)
    return resultados


def _gravar_texto(caminho: Path, texto: str) -> None:
    caminho.write_text(texto, "utf-8", newline="\n")


def _carregar_escolhas(destino: Path, pessoas: list[str]) -> tuple[list[Momento], float] | str:
    carregado = _carregar(destino, pessoas)
    if isinstance(carregado, str):
        return carregado
    erros = validar_escolhas(carregado[0])
    return f"erro: {'; '.join(erros)}" if erros else carregado


def _ajustados(momentos: list[Momento], duracao: float) -> tuple[list[Momento], list[str]]:
    """Cópia com os tempos ajustados a 2-5 s; o pedidos.json não muda."""
    copia = copy.deepcopy(momentos)
    return copia, ajustar_tempos(copia, duracao)


def _fotos_ativas(momentos: list[Momento]) -> list[tuple[int, Momento]]:
    return [(i, m) for i, m in enumerate(momentos, 1) if m.tipo == "foto" and not m.descartar]


def resumir_episodio(
    pasta: Path,
    numeros: set[int] | None,
    consultar: Consulta = wikimedia.consultar,
    medir: Callable[[str], int | None] = wikimedia.tamanho,
    pessoas: list[str] | None = None,
) -> tuple[int, int, dict[int, str]]:
    """Resolve o link de cada foto escolhida e soma os tamanhos. Não baixa nada."""
    fotos, total = 0, 0
    resultados: dict[int, str] = {}
    for corte, destino in _cortes_com_pedidos(Path(pasta), numeros):
        carregado = _carregar_escolhas(destino, pessoas or [])
        if isinstance(carregado, str):
            resultados[corte.numero] = carregado
            continue
        momentos, duracao = carregado
        copia, alertas = _ajustados(momentos, duracao)
        resolvidos: dict[int, tuple[list[str], list[int | None]]] = {}
        try:
            for posicao, m in _fotos_ativas(copia):
                urls, tamanhos = [], []
                for k, escolha in enumerate(m.escolhas, 1):
                    url = wikimedia.url_final(m.candidatas[escolha - 1]["titulo"], consultar) or ""
                    tamanho = medir(url) if url else None
                    if not url:
                        alertas.append(f"momento {posicao} ({m.nome}): opção {k} sem link de download")
                    elif tamanho is None:
                        alertas.append(f"momento {posicao} ({m.nome}): opção {k} com tamanho desconhecido")
                    urls.append(url)
                    tamanhos.append(tamanho)
                resolvidos[posicao] = (urls, tamanhos)
        except (OSError, ValueError) as erro:
            resultados[corte.numero] = f"erro: Wikimedia indisponível: {erro}"
            continue
        for posicao, (urls, tamanhos) in resolvidos.items():
            original = momentos[posicao - 1]
            original.url, original.bytes, original.resumidas = urls, tamanhos, list(original.escolhas)
            fotos += sum(1 for u in urls if u)
            total += sum(t or 0 for t in tamanhos)
        gravar_pedidos(pasta_de_trabalho(destino), momentos)
        resultados[corte.numero] = _resultado(alertas)
    return fotos, total, resultados


def _minutos(segundos: float) -> str:
    minutos, resto = divmod(int(segundos), 60)
    return f"{minutos}:{resto:02d}"


def chave_momento(m: Momento) -> str:
    return f"{prefixo_tempo(m.inicio)}-{slug(m.nome)}"


_base = chave_momento


def ler_ia(trabalho: Path) -> list[dict]:
    """Imagens de IA geradas (ia.json); ausente, ilegível ou fora do formato vira []."""
    try:
        dados = json.loads((Path(trabalho) / IA).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return [item for item in dados if isinstance(item, dict)] if isinstance(dados, list) else []


def registrar_ia(trabalho: Path, item: dict, base: Path | None = None) -> None:
    caminho = caminhos.garantir_escrita(Path(trabalho) / IA, base_extra=base)
    texto = json.dumps(ler_ia(trabalho) + [item], ensure_ascii=False, indent=2) + "\n"
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(texto, "utf-8", newline="\n")
    os.replace(temporario, caminho)


def _linha_ia(pasta: Path, m: Momento, ia: list[dict]) -> str:
    itens = [i for i in ia if i.get("momento") == chave_momento(m) and isinstance(i.get("arquivo"), str)
             and Path(i["arquivo"]).name == i["arquivo"] and (pasta / i["arquivo"]).exists()]
    if not itens:
        return ""
    itens.sort(key=lambda i: i.get("versao") if isinstance(i.get("versao"), int) else 0)
    ultimo = itens[-1]
    data = str(ultimo.get("data", ""))[:10]
    return f"Imagem de IA: {', '.join(i['arquivo'] for i in itens)} ({ultimo.get('provedor', '')}, {data})"


def _arquivos(m: Momento) -> list[str]:
    if m.tipo == "foto":
        return [f"{_base(m)}-{k}.jpg" for k in range(1, len(m.escolhas) + 1)]
    return [f"{_base(m)}.png"] if m.tipo == "noticia" else []


def _bloco_guia(pasta: Path, m: Momento, geradas: set[str], ia: list[dict]) -> str:
    linhas = [f"## {_minutos(m.inicio)} a {_minutos(m.fim)} · {m.nome} ({TIPOS_GUIA[m.tipo]})", f'Fala: "{m.fala}"']
    if m.tipo == "ia":
        linha = _linha_ia(pasta, m, ia)
        if linha:
            linhas.append(linha)
        linhas.append(f'Prompt (9:16): "{m.prompt}"')
        return "\n".join(linhas)
    presentes = [(k, nome) for k, nome in enumerate(_arquivos(m), 1) if nome in geradas and (pasta / nome).exists()]
    if presentes:
        linhas.append("Opções: " + ", ".join(nome for _, nome in presentes))
    if m.motivo or not presentes:
        linhas.append(f"Sem imagem: {m.motivo or 'arquivo não encontrado'}")
    if m.tipo == "noticia":
        linhas.append(linha_fonte(m.veiculo, m.data))
    elif presentes:
        linhas.append("Créditos:")
        for k, _ in presentes:
            c = m.candidatas[m.escolhas[k - 1] - 1]
            linhas.append(f"{k}. {c['autor']}, {c['licenca']}, {c['pagina']}")
    return "\n".join(linhas)


def escrever_guia(destino: Path, momentos: list[Momento]) -> Path:
    """Grava imagens-sugeridas/guia.md com um bloco por momento, em ordem de tempo."""
    pasta = Path(destino) / IMAGENS_SUGERIDAS
    pasta.mkdir(parents=True, exist_ok=True)
    ativos = sorted((m for m in momentos if not m.descartar), key=lambda m: m.inicio)
    geradas = set(_ler_sugeridas(Path(destino) / TRABALHO))
    ia = ler_ia(Path(destino) / TRABALHO)
    blocos = [_bloco_guia(pasta, m, geradas, ia) for m in ativos] or ["Nenhuma imagem sugerida neste corte."]
    caminho = pasta / GUIA
    _gravar_texto(caminho, LEMBRETES + "\n" + "\n\n".join(blocos) + "\n")
    return caminho


def _ler_sugeridas(trabalho: Path) -> list[str]:
    try:
        dados = json.loads((trabalho / SUGERIDAS).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(dados, list):
        return []
    return [n for n in dados if isinstance(n, str) and Path(n).name == n and Path(n).suffix in EXTENSOES_GERADAS]


def _gravar_sugeridas(trabalho: Path, geradas: list[str]) -> None:
    _gravar_texto(trabalho / SUGERIDAS, json.dumps(sorted(geradas), ensure_ascii=False, indent=2) + "\n")


def _produzir(caminho: Path, produzir: Callable[[Path], object], falha: str) -> str:
    """Gera um arquivo; devolve o motivo da falha, ou "" quando deu certo."""
    if caminho.exists():
        return f"arquivo do dono mantido ({caminho.name})"
    try:
        produzir(caminho)
        return ""
    except Exception:  # fronteira de isolamento de um item: qualquer falha vira alerta
        caminho.unlink(missing_ok=True)
        return falha


def _sugerir_um(destino: Path, momentos: list[Momento], alertas: list[str], baixar: Callable[[str, Path], None]) -> str:
    trabalho = pasta_de_trabalho(destino)
    pasta = destino / IMAGENS_SUGERIDAS
    pasta.mkdir(exist_ok=True)
    for nome in _ler_sugeridas(trabalho):  # só o que a própria esteira gerou
        (pasta / nome).unlink(missing_ok=True)
    geradas: list[str] = []
    _gravar_sugeridas(trabalho, geradas)
    for m in momentos:
        if not m.descartar:
            m.motivo = ""  # não herda "Sem imagem" de rodadas antigas
    with tempfile.TemporaryDirectory() as temporaria:
        for posicao, m in enumerate(momentos, 1):
            if m.descartar or m.tipo == "ia":
                continue
            falhas: list[tuple[int, str]] = []
            for k, nome in enumerate(_arquivos(m), 1):
                if m.tipo == "noticia":
                    def produzir(c: Path, m: Momento = m) -> None:
                        gerar_cartao(m.titulo, m.veiculo, m.data, c)
                    motivo = _produzir(pasta / nome, produzir, "cartão falhou")
                elif not m.url[k - 1]:
                    motivo = "sem link de download"
                else:
                    def produzir(c: Path, url: str = m.url[k - 1], baixada: Path = Path(temporaria) / f"{posicao}-{k}") -> None:
                        baixar(url, baixada)
                        preparar_foto(baixada, c)
                    motivo = _produzir(pasta / nome, produzir, "download falhou")
                if motivo:
                    falhas.append((k, motivo))
                else:
                    geradas.append(nome)
                    _gravar_sugeridas(trabalho, geradas)  # lista sempre em dia, mesmo se interromper
            if not falhas:
                continue
            if len(falhas) == len(_arquivos(m)) and len({motivo for _, motivo in falhas}) == 1:
                m.motivo = falhas[0][1]
            else:
                m.motivo = "; ".join(f"opção {k}: {motivo}" for k, motivo in falhas)
            alertas.append(f"momento {posicao} ({m.nome}): {m.motivo}")
    escrever_guia(destino, momentos)
    return _resultado(alertas)


def _resumido(m: Momento) -> bool:
    """O resumo foi feito com estas mesmas escolhas (o download que o dono confirmou)."""
    return m.resumidas == m.escolhas and len(m.url) == len(m.bytes) == len(m.escolhas)


def sugerir_episodio(
    pasta: Path,
    numeros: set[int] | None,
    pessoas: list[str],
    consultar: Consulta = wikimedia.consultar,
    baixar: Callable[[str, Path], None] = rede.baixar_url,
) -> dict[int, str]:
    """Baixa e prepara as fotos escolhidas, gera os cartões e o guia em imagens-sugeridas/.

    Os links vêm do `imagens resumo`; `consultar` fica na assinatura do contrato, sem uso aqui.
    """
    resultados: dict[int, str] = {}
    for corte, destino in _cortes_com_pedidos(Path(pasta), numeros):
        carregado = _carregar_escolhas(destino, pessoas)
        if isinstance(carregado, str):
            resultados[corte.numero] = carregado
            continue
        copia, alertas = _ajustados(*carregado)
        if any(not _resumido(m) for _, m in _fotos_ativas(copia)):
            resultados[corte.numero] = ERRO_SEM_RESUMO
            continue
        resultados[corte.numero] = _sugerir_um(destino, copia, alertas, baixar)
    return resultados
