import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "TudoEPoliticaEsteira/1.0"
TENTATIVAS = 4
ESPERA_MAXIMA = 30.0

_urlopen = urllib.request.urlopen


def _espera(erro: urllib.error.HTTPError) -> float:
    try:
        segundos = float(erro.headers.get("Retry-After", "5"))
    except (TypeError, ValueError):
        segundos = 5.0
    return min(max(segundos, 1.0), ESPERA_MAXIMA)


def abrir(url: str, metodo: str = "GET"):
    """Abre a URL; com 429 (muitos pedidos), espera o Retry-After e tenta de novo."""
    pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method=metodo)
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return _urlopen(pedido, timeout=60)
        except urllib.error.HTTPError as erro:
            if erro.code != 429 or tentativa == TENTATIVAS:
                raise
            time.sleep(_espera(erro))


def baixar_url(url: str, destino: Path) -> None:
    with abrir(url) as resposta:
        destino.write_bytes(resposta.read())
