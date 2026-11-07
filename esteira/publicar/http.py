import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from esteira.rede import USER_AGENT

_urlopen = urllib.request.urlopen
TEMPO = 300


@dataclass
class Resultado:
    estado: str
    link: str = ""
    id_rede: str = ""


class ErroRede(Exception):
    def __init__(self, mensagem: str, temporario: bool, codigo: int | None = None, dados: dict | None = None):
        super().__init__(mensagem)
        self.temporario = temporario
        self.codigo = codigo
        self.dados = dados or {}


class ErroIncerto(Exception):
    """A rede pode já ter publicado: não tentar de novo, mandar conferir."""


def json_de(corpo: bytes) -> dict:
    try:
        dados = json.loads(corpo.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _motivo(dados: dict) -> str:
    """Só campos de mensagem conhecidos: o corpo inteiro pode conter tokens."""
    erro = dados.get("error")
    if isinstance(erro, dict):
        texto = erro.get("message") or erro.get("code") or ""
    else:
        texto = dados.get("error_description") or dados.get("error_message") or (erro if isinstance(erro, str) else "")
    return str(texto)[:200] or "sem detalhe"


def pedir(metodo: str, url: str, corpo: bytes | None = None, cabecalhos: dict | None = None) -> tuple[int, dict, bytes]:
    pedido = urllib.request.Request(url, data=corpo, method=metodo, headers={"User-Agent": USER_AGENT, **(cabecalhos or {})})
    try:
        with _urlopen(pedido, timeout=TEMPO) as resposta:
            return resposta.status, dict(resposta.headers), resposta.read()
    except urllib.error.HTTPError as erro:
        dados = json_de(erro.read() or b"")
        temporario = erro.code == 429 or erro.code >= 500
        raise ErroRede(f"HTTP {erro.code}: {_motivo(dados)}", temporario, erro.code, dados) from None
    except (urllib.error.URLError, OSError) as erro:
        raise ErroRede(f"falha de conexão: {getattr(erro, 'reason', erro)}", True) from None
