import html
import json
import re
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass

from esteira.rede import abrir

API_URL = "https://commons.wikimedia.org/w/api.php"
MIMES_ACEITOS = {"image/jpeg", "image/png", "image/webp"}
LADO_MINIMO = 800
LARGURA_MINIATURA = 640
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


def licenca_aceita(nome: str) -> bool:
    texto = re.sub(r"[-_]", " ", nome.lower()).strip()
    if {"nc", "nd"} & set(texto.split()):
        return False
    return texto.startswith(("cc0", "public domain", "pd")) or bool(re.match(r"cc by( sa)? \d", texto))


def _texto(texto: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", "", texto)).split())


def _candidata(pagina: dict) -> Candidata | None:
    info = (pagina.get("imageinfo") or [None])[0]
    if not info or not info.get("thumburl") or info.get("mime") not in MIMES_ACEITOS:
        return None
    largura, altura = info.get("width", 0), info.get("height", 0)
    if min(largura, altura) < LADO_MINIMO:
        return None
    meta = info.get("extmetadata") or {}
    licenca = (meta.get("LicenseShortName") or {}).get("value", "")
    if not licenca_aceita(licenca):
        return None
    titulo = pagina["title"]
    autor = _texto((meta.get("Artist") or {}).get("value", "")) or "desconhecido"
    link = "https://commons.wikimedia.org/wiki/" + titulo.replace(" ", "_")
    return Candidata(titulo, link, info["thumburl"], largura, altura, autor, licenca)


def buscar_candidatas(busca: str, consultar: Consulta = consultar, limite: int = 6) -> list[Candidata]:
    resposta = consultar({
        "action": "query", "generator": "search", "gsrsearch": busca, "gsrnamespace": 6,
        "gsrlimit": RESULTADOS_BUSCA, "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": LARGURA_MINIATURA,
    })
    paginas = sorted(resposta.get("query", {}).get("pages", []), key=lambda p: p.get("index", 0))
    candidatas = (_candidata(pagina) for pagina in paginas)
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
