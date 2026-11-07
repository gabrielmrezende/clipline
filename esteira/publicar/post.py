import contextlib
import hashlib
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from esteira.caminhos import garantir_escrita

LIMITE_TITULO = 100
LIMITE_DESCRICAO = 5000
LIMITE_LEGENDA = 2200
LIMITE_HASHTAGS = 30
OBRIGATORIAS = ("YouTube", "Instagram", "TikTok")


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


def _conferir_antes_de_gravar(texto: str, pedido: Textos, somente_leitura: dict[str, str]) -> None:
    """Relê em memória o que vai para o disco: tem de voltar igual, sem mexer no resto."""
    try:
        relido = interpretar_post(texto)
    except ErroPost:
        relido = None
    if relido != pedido or somente_leitura_do_texto(texto) != somente_leitura or _repetidas(texto):
        raise ErroPost(
            "post.md não gravado: o texto não seria lido de volta igual. "
            "Confira quebras de linha e linhas começando com '## '."
        )


def gravar_textos(caminho: Path, textos: Textos, base: Path | None = None) -> str:
    """Troca só os quatro campos; o resto do arquivo fica igual byte a byte."""
    caminho = Path(caminho)
    garantir_escrita(caminho, base_extra=base)
    bruto = caminho.read_bytes().decode("utf-8")
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
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        temporario.write_bytes(dados)
        os.replace(temporario, caminho)
    finally:
        with contextlib.suppress(OSError):
            temporario.unlink(missing_ok=True)
    return versao_dos_bytes(dados)
