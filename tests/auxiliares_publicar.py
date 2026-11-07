import io
import json
import urllib.error
from datetime import datetime, timedelta, timezone

from esteira.publicar.post import Textos

FUSO = timezone(timedelta(hours=-3))
DATA = datetime(2026, 11, 8, 18, 0, tzinfo=FUSO)
CREDITO = "Música: Ice Flow — Kevin MacLeod (incompetech.com), licença CC BY 4.0"
TEXTOS = Textos("Título do corte #Shorts", "Descrição.\n\n" + CREDITO, "Legenda IG. " + CREDITO, "Legenda TT. " + CREDITO)


class Resposta:
    def __init__(self, status=200, corpo=b"", cabecalhos=None):
        self.status = status
        self.headers = cabecalhos or {}
        self._corpo = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def erro_http(codigo, corpo=None):
    dados = json.dumps(corpo or {}).encode()
    return urllib.error.HTTPError("http://x", codigo, "erro", {}, io.BytesIO(dados))


class Servidor:
    """Troca o _urlopen: registra os pedidos e devolve as respostas em ordem."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    def __call__(self, pedido, timeout=None):
        self.pedidos.append(pedido)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class Cofre:
    def __init__(self, dados=None):
        self.dados = dict(dados or {})

    def ler(self, rede, campo):
        return self.dados.get(f"{rede}:{campo}")

    def gravar(self, rede, campo, valor):
        self.dados[f"{rede}:{campo}"] = valor
