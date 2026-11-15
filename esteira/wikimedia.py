import html
import json
import re
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass

from esteira import config
from esteira.rede import abrir

API_URL = "https://commons.wikimedia.org/w/api.php"
MIMES_ACEITOS = {"image/jpeg", "image/png", "image/webp"}
LADO_MINIMO = 800
LARGURA_MINIATURA = 500  # largura padrão do Wikimedia (outras dão HTTP 400), dentro dos 640 px do CLAUDE.md
LARGURA_FINAL = 1920
RESULTADOS_BUSCA = 20
INTERVALO_CONSULTAS = 2.0
ERROS_TEMPORARIOS = {"cirrussearch-too-busy-error", "ratelimited", "maxlag"}
TENTATIVAS_OCUPADA = 4
ESPERA_OCUPADA = 10.0

Consulta = Callable[[dict], dict]


@dataclass
class Candidata:
    titulo: str
    pagina: str
    miniatura: str
    largura: int
    altura: int
    autor: str
    licenca: str


_ultima_consulta = 0.0


def consultar(params: dict) -> dict:
    global _ultima_consulta
    consulta = urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    for tentativa in range(1, TENTATIVAS_OCUPADA + 1):
        # A API limita pedidos seguidos; espaçar evita o 429.
        time.sleep(max(0.0, _ultima_consulta + INTERVALO_CONSULTAS - time.monotonic()))
        _ultima_consulta = time.monotonic()
        with abrir(f"{API_URL}?{consulta}") as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
        if not (isinstance(dados, dict) and "error" in dados):
            return dados
        erro = dados["error"] if isinstance(dados["error"], dict) else {}
        codigo = erro.get("code", "desconhecido")
        if codigo not in ERROS_TEMPORARIOS or tentativa == TENTATIVAS_OCUPADA:
            raise ValueError(f"Wikimedia: {codigo}: {erro.get('info', dados['error'])}")
        time.sleep(ESPERA_OCUPADA * tentativa)


def tipo_de_licenca(nome: str) -> str | None:
    """O tipo da licença com os nomes do `[imagens] licencas` (cc0, dominio-publico, cc-by, cc-by-sa).

    None se não for livre (NC, ND, uso justo, desconhecida)."""
    texto = re.sub(r"[-_]", " ", nome.lower()).strip()
    if {"nc", "nd"} & set(texto.split()):
        return None
    if texto.startswith("cc0"):
        return "cc0"
    if texto.startswith(("public domain", "pd")):
        return "dominio-publico"
    if re.match(r"cc by sa \d", texto):
        return "cc-by-sa"
    if re.match(r"cc by \d", texto):
        return "cc-by"
    return None


def licenca_aceita(nome: str, aceitas: tuple[str, ...] | None = None) -> bool:
    """Sem `aceitas`, as do clipline.toml (padrão: CC0, domínio público, CC BY e CC BY-SA, como sempre)."""
    return tipo_de_licenca(nome) in (aceitas if aceitas is not None else config.atual().imagens_licencas)


def compartilha_igual(licenca: str) -> bool:
    return tipo_de_licenca(licenca) == "cc-by-sa"


AVISO_COMPARTILHA_IGUAL = (
    "CC BY-SA (CompartilhaIgual): a foto adaptada no vídeo (recortada, com fundo desfocado) fica sob a mesma "
    "licença; ponha o nome da licença junto do crédito."
)


def aviso_compartilha_igual(creditos: list[dict]) -> str | None:
    """A observação que vai depois dos créditos (guia.md, resumo da publicação) se alguma foto é CC BY-SA.

    Além do crédito, a CC BY-SA pede que a obra adaptada siga a mesma licença. Sem foto CC BY-SA, None: os
    créditos saem como sempre."""
    if any(isinstance(c, dict) and compartilha_igual(str(c.get("licenca") or "")) for c in creditos):
        return AVISO_COMPARTILHA_IGUAL
    return None


LIMITE_AUTOR = 120


def _texto(texto: str, limite: int | None = None) -> str:
    """Texto de terceiros (qualquer um edita o Commons): sem HTML, numa linha só e com tamanho limitado.

    Esses campos chegam ao agente e aos posts; uma linha curta reduz o espaço para instrução escondida."""
    limpo = " ".join(html.unescape(re.sub(r"<[^>]*>", "", texto)).split())
    limpo = "".join(c for c in limpo if c.isprintable())
    return limpo if limite is None or len(limpo) <= limite else limpo[: limite - 1] + "…"


def _candidata(pagina: dict, aceitas: tuple[str, ...] | None = None) -> Candidata | None:
    info = (pagina.get("imageinfo") or [None])[0]
    if not info or not info.get("thumburl") or info.get("mime") not in MIMES_ACEITOS:
        return None
    largura, altura = info.get("width", 0), info.get("height", 0)
    if min(largura, altura) < LADO_MINIMO:
        return None
    meta = info.get("extmetadata") or {}
    licenca = (meta.get("LicenseShortName") or {}).get("value", "")
    if not licenca_aceita(licenca, aceitas):
        return None
    titulo = pagina["title"]
    autor = _texto((meta.get("Artist") or {}).get("value", ""), LIMITE_AUTOR) or "desconhecido"
    link = "https://commons.wikimedia.org/wiki/" + titulo.replace(" ", "_")
    return Candidata(titulo, link, info["thumburl"], largura, altura, autor, _texto(licenca, 60))


def buscar_candidatas(
    busca: str, consultar: Consulta = consultar, limite: int = 6, aceitas: tuple[str, ...] | None = None
) -> list[Candidata]:
    """`aceitas`: as licenças do `[imagens] licencas` (sem ele, as do clipline.toml)."""
    if aceitas is None:
        aceitas = config.atual().imagens_licencas
    resposta = consultar({
        "action": "query", "generator": "search", "gsrsearch": busca, "gsrnamespace": 6,
        "gsrlimit": RESULTADOS_BUSCA, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": LARGURA_MINIATURA,
    })
    paginas = sorted(resposta.get("query", {}).get("pages", []), key=lambda p: p.get("index", 0))
    candidatas = (_candidata(pagina, aceitas) for pagina in paginas)
    return [c for c in candidatas if c][:limite]


def url_final(titulo: str, consultar: Consulta = consultar) -> str | None:
    resposta = consultar({
        "action": "query", "titles": titulo, "prop": "imageinfo", "iiprop": "url",
        "iiurlwidth": LARGURA_FINAL,
    })
    for pagina in resposta.get("query", {}).get("pages", []):
        info = (pagina.get("imageinfo") or [None])[0]
        if info and info.get("thumburl"):
            return info["thumburl"]
    return None


def tamanho(url: str) -> int | None:
    try:
        with abrir(url, "HEAD") as resposta:
            return int(resposta.headers["Content-Length"])
    except Exception:
        return None
