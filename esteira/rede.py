import urllib.request
from pathlib import Path

USER_AGENT = "TudoEPoliticaEsteira/1.0"


def abrir(url: str, metodo: str = "GET"):
    pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method=metodo)
    return urllib.request.urlopen(pedido, timeout=60)


def baixar_url(url: str, destino: Path) -> None:
    with abrir(url) as resposta:
        destino.write_bytes(resposta.read())
