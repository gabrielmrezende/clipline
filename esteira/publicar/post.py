import re
from dataclasses import dataclass
from pathlib import Path

LIMITE_TITULO = 100
LIMITE_DESCRICAO = 5000
LIMITE_LEGENDA = 2200
LIMITE_HASHTAGS = 30


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


def ler_post(caminho: Path) -> Textos:
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroPost(f"post.md não encontrado: {caminho}")
    secoes = _secoes(caminho.read_text("utf-8"))
    for nome in ("YouTube", "Instagram", "TikTok"):
        if nome not in secoes:
            raise ErroPost(f"post.md sem a seção ## {nome}")
    titulo, descricao = _youtube(secoes["YouTube"])
    return Textos(titulo, descricao, secoes["Instagram"], secoes["TikTok"])


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
