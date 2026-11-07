import socket
import threading
import urllib.request

import pytest

from esteira.publicar import credenciais
from esteira.publicar.credenciais import ErroConexao, esperar_codigo, gravar, ler, pedir_segredo


class KeyringFalso:
    def __init__(self):
        self.dados = {}

    def get_password(self, servico, chave):
        return self.dados.get((servico, chave))

    def set_password(self, servico, chave, valor):
        self.dados[(servico, chave)] = valor


@pytest.fixture
def cofre(monkeypatch):
    falso = KeyringFalso()
    monkeypatch.setattr(credenciais, "_keyring", lambda: falso)
    return falso


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _chamar_depois(porta: int, consulta: str):
    def abrir(_url):
        def pedir():
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/retorno?{consulta}", timeout=5).read()
        threading.Thread(target=pedir, daemon=True).start()
        return True
    return abrir


def test_grava_e_le(cofre):
    gravar("youtube", "token", "abc")
    assert ler("youtube", "token") == "abc"
    assert cofre.dados[("tudo-e-politica", "youtube:token")] == "abc"
    assert ler("x", "y") is None


def test_pedir_segredo_vazio(monkeypatch):
    monkeypatch.setattr(credenciais.getpass, "getpass", lambda rotulo: "  ")
    with pytest.raises(ErroConexao, match="vazio"):
        pedir_segredo("Client ID")


def test_esperar_codigo_devolve_code():
    porta = _porta_livre()
    assert esperar_codigo(porta, "E1", "https://x", abrir=_chamar_depois(porta, "code=C1&state=E1")) == "C1"


def test_esperar_codigo_state_errado():
    porta = _porta_livre()
    with pytest.raises(ErroConexao, match="state"):
        esperar_codigo(porta, "E1", "https://x", abrir=_chamar_depois(porta, "code=C1&state=OUTRO"))


def test_esperar_codigo_erro_da_rede():
    porta = _porta_livre()
    with pytest.raises(ErroConexao, match="access_denied"):
        esperar_codigo(porta, "E1", "https://x", abrir=_chamar_depois(porta, "error=access_denied&state=E1"))


def test_esperar_codigo_tempo_esgotado():
    porta = _porta_livre()
    with pytest.raises(ErroConexao, match="tempo"):
        esperar_codigo(porta, "E1", "https://x", abrir=lambda url: True, tempo=0.5)
