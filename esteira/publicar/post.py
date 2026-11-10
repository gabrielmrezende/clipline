import contextlib
import hashlib
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from esteira.caminhos import garantir_escrita
from esteira.receita import Musica

LIMITE_TITULO = 100
LIMITE_DESCRICAO = 5000
LIMITE_LEGENDA = 2200
LIMITE_HASHTAGS = 30
OBRIGATORIAS = ("YouTube", "Instagram", "TikTok")
AVISO_IA = "Algumas imagens utilizadas neste vídeo foram geradas por Inteligência Artificial (IA)."


class ErroPost(Exception):
    pass


@dataclass
class Textos:
    youtube_titulo: str
    youtube_descricao: str
    instagram: str
    tiktok: str


def _secoes(texto: str) -> dict[str, str]:
    secoes: dict[str, list[str]] = {}
    atual = None
    for linha in texto.splitlines():
        if linha.startswith("## "):
            atual = linha[3:].strip()
            secoes[atual] = []
        elif atual is not None:
            secoes[atual].append(linha)
    return {nome: "\n".join(linhas).strip() for nome, linhas in secoes.items()}


def _youtube(corpo: str) -> tuple[str, str]:
    titulo = re.search(r"^Título:(.*)$", corpo, re.M)
    descricao = re.search(r"^Descrição:\s*$", corpo, re.M)
    if not titulo or not descricao:
        raise ErroPost("post.md: a seção ## YouTube precisa de 'Título:' e 'Descrição:'")
    return titulo.group(1).strip(), corpo[descricao.end():].strip()


def interpretar_post(texto: str) -> Textos:
    """Os campos de um post.md já lido, pelas mesmas regras de ler_post."""
    secoes = _secoes(texto)
    for nome in OBRIGATORIAS:
        if nome not in secoes:
            raise ErroPost(f"post.md sem a seção ## {nome}")
    titulo, descricao = _youtube(secoes["YouTube"])
    return Textos(titulo, descricao, secoes["Instagram"], secoes["TikTok"])


def ler_post(caminho: Path) -> Textos:
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroPost(f"post.md não encontrado: {caminho}")
    return interpretar_post(caminho.read_text("utf-8"))


def tem_quebra_de_linha(texto: str) -> bool:
    """Qualquer quebra que str.splitlines() reconhece (a mesma regra do leitor)."""
    return texto.splitlines(keepends=True) != texto.splitlines()


def _sem_forma(texto: str) -> str:
    """Minúsculas e cada sequência de espaços ou quebras de linha virando um espaço."""
    return re.sub(r"\s+", " ", texto).strip().lower()


def faltando_aviso_ia(textos: Textos, redes: set[str]) -> list[str]:
    """As redes cujo texto não traz o aviso de IA do canal (no YouTube, a descrição)."""
    aviso = _sem_forma(AVISO_IA)
    corpos = (("youtube", textos.youtube_descricao), ("instagram", textos.instagram), ("tiktok", textos.tiktok))
    return [f"{rede}: falta o aviso de IA" for rede, texto in corpos if rede in redes and aviso not in _sem_forma(texto)]


def conferir_textos(textos: Textos, credito: str | None, redes: set[str]) -> list[str]:
    credito = credito.rstrip(".") if credito else None
    problemas: list[str] = []
    if "youtube" in redes:
        if not textos.youtube_titulo:
            problemas.append("youtube: título vazio")
        elif len(textos.youtube_titulo) > LIMITE_TITULO:
            problemas.append("youtube: título com mais de 100 caracteres")
        if len(textos.youtube_descricao) > LIMITE_DESCRICAO:
            problemas.append("youtube: descrição com mais de 5000 caracteres")
        if re.search(r"[<>]", textos.youtube_titulo + textos.youtube_descricao):
            problemas.append("youtube: descrição com < ou >")
        if credito and credito not in textos.youtube_descricao:
            problemas.append("youtube: falta o crédito da música")
    for rede, texto in (("instagram", textos.instagram), ("tiktok", textos.tiktok)):
        if rede not in redes:
            continue
        if not texto:
            problemas.append(f"{rede}: texto vazio")
        if len(texto) > LIMITE_LEGENDA:
            problemas.append(f"{rede}: texto com mais de 2200 caracteres")
        if rede == "instagram" and len(re.findall(r"#\w+", texto)) > LIMITE_HASHTAGS:
            problemas.append("instagram: mais de 30 hashtags")
        if credito and credito not in texto:
            problemas.append(f"{rede}: falta o crédito da música")
    return problemas


def versao_dos_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def versao_post(caminho: Path) -> str:
    return versao_dos_bytes(Path(caminho).read_bytes())


def somente_leitura_do_texto(texto: str) -> dict[str, str]:
    return {n: c for n, c in _secoes(texto).items() if n not in OBRIGATORIAS}


def secoes_somente_leitura(caminho: Path) -> dict[str, str]:
    return somente_leitura_do_texto(Path(caminho).read_text("utf-8"))


@dataclass
class PostLido:
    textos: Textos
    somente_leitura: dict[str, str]
    versao: str


def ler_post_completo(caminho: Path) -> PostLido:
    """Campos, seções só de leitura e versão tirados dos mesmos bytes (uma leitura só)."""
    dados = Path(caminho).read_bytes()
    texto = dados.decode("utf-8")
    return PostLido(interpretar_post(texto), somente_leitura_do_texto(texto), versao_dos_bytes(dados))


class ConflitoPost(ErroPost):
    def __init__(self, versao_atual: str):
        self.versao_atual = versao_atual
        super().__init__("O post.md mudou desde que você abriu.")


def _linhas(texto: str) -> list[list[str]]:
    """Divide como o leitor (splitlines), guardando o fim de cada linha: [conteúdo, fim]."""
    linhas = []
    for peca in texto.splitlines(keepends=True):
        conteudo = peca.splitlines()[0]
        linhas.append([conteudo, peca[len(conteudo):]])
    return linhas


def _fim_predominante(linhas: list[list[str]]) -> str:
    contagem = Counter(fim for _, fim in linhas if fim)
    return contagem.most_common(1)[0][0] if contagem else "\n"


def _repetidas(texto: str) -> list[str]:
    nomes = [linha[3:].strip() for linha in texto.splitlines() if linha.startswith("## ")]
    return [nome for nome in OBRIGATORIAS if nomes.count(nome) > 1]


def _normalizar(texto: str) -> str:
    """O texto de várias linhas como o leitor o devolveria."""
    return "\n".join(texto.splitlines()).strip()


def _limites_secao(linhas: list[list[str]], nome: str) -> tuple[int, int]:
    """Faixa [inicio, fim) do corpo da seção, sem a linha do cabeçalho."""
    inicio = None
    for i, (conteudo, _) in enumerate(linhas):
        if conteudo.startswith("## "):
            if inicio is not None:
                return inicio, i
            if conteudo[3:].strip() == nome:
                inicio = i + 1
    if inicio is None:
        raise ErroPost(f"post.md sem a seção ## {nome}")
    return inicio, len(linhas)


def _trocar_faixa(linhas: list[list[str]], inicio: int, fim: int, novo: str, fim_linha: str) -> None:
    """Troca só da primeira à última linha não vazia de [inicio, fim)."""
    cheias = [i for i in range(inicio, fim) if linhas[i][0].strip()]
    novas = [[texto, fim_linha] for texto in novo.splitlines()]
    if cheias:
        if novas:  # a última herda o fim que a separava do resto do arquivo
            novas[-1][1] = linhas[cheias[-1]][1]
        linhas[cheias[0]:cheias[-1] + 1] = novas
        return
    if novas and inicio == len(linhas) and not linhas[inicio - 1][1]:
        linhas[inicio - 1][1] = fim_linha  # o arquivo acabava no cabeçalho, sem quebra
        novas[-1][1] = ""
    linhas[inicio:inicio] = novas


def _conferir_antes_de_gravar(
    texto: str, pedido: Textos, somente_leitura: dict[str, str], livres: tuple[str, ...] = ()
) -> None:
    """Relê em memória o que vai para o disco: tem de voltar igual, sem mexer no resto.

    As seções em livres podem mudar (trocar_credito reescreve a seção Música).
    """
    try:
        relido = interpretar_post(texto)
    except ErroPost:
        relido = None
    antes = {nome: corpo for nome, corpo in somente_leitura.items() if nome not in livres}
    depois = {nome: corpo for nome, corpo in somente_leitura_do_texto(texto).items() if nome not in livres}
    if relido != pedido or depois != antes or _repetidas(texto):
        raise ErroPost(
            "post.md não gravado: o texto não seria lido de volta igual. "
            "Confira quebras de linha e linhas começando com '## '."
        )


def _gravar_atomico(caminho: Path, dados: bytes) -> None:
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        temporario.write_bytes(dados)
        os.replace(temporario, caminho)
    finally:
        with contextlib.suppress(OSError):
            temporario.unlink(missing_ok=True)


def gravar_textos(
    caminho: Path, textos: Textos, base: Path | None = None, versao: str | None = None
) -> str:
    """Troca só os quatro campos; o resto do arquivo fica igual byte a byte.

    Com versao, confere a versão nos mesmos bytes que edita e levanta ConflitoPost se mudou.
    """
    caminho = Path(caminho)
    garantir_escrita(caminho, base_extra=base)
    original = caminho.read_bytes()
    if versao is not None:
        atual_no_disco = versao_dos_bytes(original)
        if atual_no_disco != versao:
            raise ConflitoPost(atual_no_disco)
    bruto = original.decode("utf-8")
    atual = interpretar_post(bruto)
    repetidas = _repetidas(bruto)
    if repetidas:
        raise ErroPost(f"post.md com a seção ## {repetidas[0]} repetida")
    pedido = Textos(
        textos.youtube_titulo.strip(),
        _normalizar(textos.youtube_descricao),
        _normalizar(textos.instagram),
        _normalizar(textos.tiktok),
    )
    linhas = _linhas(bruto)
    fim_linha = _fim_predominante(linhas)

    if pedido.youtube_titulo != atual.youtube_titulo:
        ini, fim = _limites_secao(linhas, "YouTube")
        for i in range(ini, fim):
            if linhas[i][0].startswith("Título:"):
                linhas[i][0] = f"Título: {pedido.youtube_titulo}"
                break
    if pedido.youtube_descricao != atual.youtube_descricao:
        ini, fim = _limites_secao(linhas, "YouTube")
        for i in range(ini, fim):
            if re.fullmatch(r"Descrição:\s*", linhas[i][0]):
                _trocar_faixa(linhas, i + 1, fim, pedido.youtube_descricao, fim_linha)
                break
    for nome, novo, velho in (
        ("Instagram", pedido.instagram, atual.instagram),
        ("TikTok", pedido.tiktok, atual.tiktok),
    ):
        if novo != velho:
            ini, fim = _limites_secao(linhas, nome)
            _trocar_faixa(linhas, ini, fim, novo, fim_linha)

    texto = "".join(conteudo + fim for conteudo, fim in linhas)
    _conferir_antes_de_gravar(texto, pedido, somente_leitura_do_texto(bruto))
    dados = texto.encode("utf-8")
    _gravar_atomico(caminho, dados)
    return versao_dos_bytes(dados)


def _linhas_do_campo(linhas: list[list[str]], nome: str) -> tuple[int, int]:
    """Faixa [inicio, fim) de um campo: a descrição do YouTube ou o corpo inteiro da seção."""
    inicio, fim = _limites_secao(linhas, nome)
    if nome != "YouTube":
        return inicio, fim
    for i in range(inicio, fim):
        if re.fullmatch(r"Descrição:\s*", linhas[i][0]):
            return i + 1, fim
    return fim, fim


def _trocar_nas_linhas(linhas: list[list[str]], inicio: int, fim: int, velho: str, novo: str) -> bool:
    """Troca velho por novo dentro de cada linha de [inicio, fim); True se achou alguma."""
    achou = False
    for i in range(inicio, fim):
        if velho in linhas[i][0]:
            linhas[i][0] = linhas[i][0].replace(velho, novo)
            achou = True
    return achou


def _primeira_linha(linhas: list[list[str]], inicio: int, fim: int, prefixo: str) -> int | None:
    return next((i for i in range(inicio, fim) if linhas[i][0].startswith(prefixo)), None)


def _trocar_secao_musica(linhas: list[list[str]], antiga: Musica | None, nova: Musica) -> bool:
    """Troca as linhas 'Crédito:' e 'Faixa:' da seção Música; False se faltou a seção ou uma linha."""
    try:
        inicio, fim = _limites_secao(linhas, "Música")
    except ErroPost:
        return False
    completa = True
    credito = _primeira_linha(linhas, inicio, fim, "Crédito:")
    if credito is None:
        completa = False
    else:
        linhas[credito][0] = f"Crédito: {nova.credito}"
    if antiga is not None and antiga.titulo:  # sem título antigo não há o que trocar na linha Faixa:
        faixa = _primeira_linha(linhas, inicio, fim, "Faixa:")
        valor = "" if faixa is None else linhas[faixa][0].removeprefix("Faixa:")
        if faixa is not None and antiga.titulo in valor:  # só no valor: a linha segue começando com Faixa:
            linhas[faixa][0] = "Faixa:" + valor.replace(antiga.titulo, nova.titulo)
        else:
            completa = False
    return completa


def trocar_credito(caminho: Path, antiga: Musica | None, nova: Musica, base: Path | None = None) -> list[str]:
    """Troca o crédito da música nos textos e as linhas da seção Música; o resto fica igual byte a byte.

    Devolve avisos do que não achou para trocar. Mesma faixa (só o volume mudou): nem lê o arquivo.
    Nada para trocar: não grava. A seção Música fica fora da releitura, então o crédito e o título
    novos não podem ter quebra de linha (criariam linhas, ou seções, que ninguém conferiu).
    """
    if antiga is not None and antiga.arquivo == nova.arquivo:
        return []
    caminho = Path(caminho)
    garantir_escrita(caminho, base_extra=base)
    if tem_quebra_de_linha(nova.credito) or tem_quebra_de_linha(nova.titulo):
        raise ErroPost(
            "post.md não gravado: o crédito e o título da música nova não podem ter quebra de linha."
        )
    bruto = caminho.read_bytes().decode("utf-8")
    atual = interpretar_post(bruto)
    repetidas = _repetidas(bruto)
    if repetidas:
        raise ErroPost(f"post.md com a seção ## {repetidas[0]} repetida")
    linhas = _linhas(bruto)
    velho = antiga.credito if antiga is not None else ""
    avisos: list[str] = []
    esperados: list[str] = []
    for rede, nome, campo in (
        ("youtube", "YouTube", atual.youtube_descricao),
        ("instagram", "Instagram", atual.instagram),
        ("tiktok", "TikTok", atual.tiktok),
    ):
        inicio, fim = _linhas_do_campo(linhas, nome)
        if velho and _trocar_nas_linhas(linhas, inicio, fim, velho, nova.credito):
            esperados.append(_normalizar(campo.replace(velho, nova.credito)))
        else:
            esperados.append(campo)
            avisos.append(f"{rede}: crédito antigo não encontrado; confira o crédito")
    if not _trocar_secao_musica(linhas, antiga, nova):
        avisos.append("seção Música não atualizada")

    texto = "".join(conteudo + fim for conteudo, fim in linhas)
    if texto == bruto:
        return avisos
    esperado = Textos(atual.youtube_titulo, *esperados)
    _conferir_antes_de_gravar(texto, esperado, somente_leitura_do_texto(bruto), livres=("Música",))
    _gravar_atomico(caminho, texto.encode("utf-8"))
    return avisos
