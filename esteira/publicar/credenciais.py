import getpass
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

SERVICO = "tudo-e-politica"
PORTA = 8765
REDIRECIONAMENTO = f"http://localhost:{PORTA}/retorno"


class ErroConexao(Exception):
    """Falha de login ou token. Com a rede, a mensagem diz como reconectar."""

    def __init__(self, motivo: str, rede: str | None = None):
        if rede:
            motivo = f"{rede}: {motivo}; reconecte com publicar conectar {rede}"
        super().__init__(motivo)


def _keyring():
    import keyring  # importado aqui: os testes não precisam do pacote

    return keyring


def ler(rede: str, campo: str) -> str | None:
    return _keyring().get_password(SERVICO, f"{rede}:{campo}")


def gravar(rede: str, campo: str, valor: str) -> None:
    _keyring().set_password(SERVICO, f"{rede}:{campo}", valor)


def pedir_segredo(rotulo: str) -> str:
    valor = getpass.getpass(f"{rotulo} (não aparece na tela): ").strip()
    if not valor:
        raise ErroConexao(f"{rotulo} vazio")
    return valor


PAGINA = "<html><body><p>Pode fechar esta aba e voltar ao terminal.</p></body></html>".encode("utf-8")


def esperar_codigo(porta: int, estado: str, abrir_url: str, abrir=webbrowser.open, tempo: float = 300) -> str:
    """Abre a autorização no navegador e espera um único retorno em /retorno."""
    resposta: dict[str, str] = {}

    class Retorno(BaseHTTPRequestHandler):
        def do_GET(self):
            partes = urllib.parse.urlsplit(self.path)
            if partes.path != "/retorno":
                self.send_response(404)
                self.end_headers()
                return
            resposta.update({k: v[0] for k, v in urllib.parse.parse_qs(partes.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGINA)
            pronto.set()

        def log_message(self, *args):
            pass

    pronto = threading.Event()
    servidor = HTTPServer(("127.0.0.1", porta), Retorno)
    servidor.timeout = 0.2
    try:
        abrir(abrir_url)
        prazo = threading.Timer(tempo, pronto.set)
        prazo.daemon = True
        prazo.start()
        while not pronto.is_set():
            servidor.handle_request()
        prazo.cancel()
    finally:
        servidor.server_close()
    if not resposta:
        raise ErroConexao("tempo esgotado esperando a autorização no navegador")
    if resposta.get("state") != estado:
        raise ErroConexao("retorno com state diferente do pedido; tente de novo")
    if "error" in resposta:
        raise ErroConexao(f"autorização recusada: {resposta['error']}")
    if not resposta.get("code"):
        raise ErroConexao("retorno sem código de autorização")
    return resposta["code"]
