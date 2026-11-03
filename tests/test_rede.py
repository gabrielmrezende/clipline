import io
import urllib.error

from esteira import rede


def _erro_429(espera="2"):
    return urllib.error.HTTPError("u", 429, "Too Many Requests", {"Retry-After": espera}, io.BytesIO(b""))


def test_abrir_espera_e_repete_quando_recebe_429(monkeypatch):
    respostas = [_erro_429("2"), _erro_429("3"), "ok"]
    esperas = []
    monkeypatch.setattr(rede, "_urlopen", lambda pedido, timeout: _proxima(respostas))
    monkeypatch.setattr(rede.time, "sleep", esperas.append)
    assert rede.abrir("https://x") == "ok"
    assert esperas == [2.0, 3.0]


def test_abrir_desiste_depois_de_varias_recusas(monkeypatch):
    monkeypatch.setattr(rede, "_urlopen", lambda pedido, timeout: _proxima([_erro_429()]))
    monkeypatch.setattr(rede.time, "sleep", lambda s: None)
    try:
        rede.abrir("https://x")
    except urllib.error.HTTPError as erro:
        assert erro.code == 429
    else:
        raise AssertionError("deveria desistir")


def test_abrir_limita_espera_longa(monkeypatch):
    respostas = [_erro_429("600"), "ok"]
    esperas = []
    monkeypatch.setattr(rede, "_urlopen", lambda pedido, timeout: _proxima(respostas))
    monkeypatch.setattr(rede.time, "sleep", esperas.append)
    rede.abrir("https://x")
    assert esperas == [rede.ESPERA_MAXIMA]


def test_abrir_nao_repete_outros_erros(monkeypatch):
    chamadas = []
    def falha(pedido, timeout):
        chamadas.append(1)
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b""))
    monkeypatch.setattr(rede, "_urlopen", falha)
    try:
        rede.abrir("https://x")
    except urllib.error.HTTPError:
        pass
    assert len(chamadas) == 1


def _proxima(respostas):
    r = respostas.pop(0) if len(respostas) > 1 else respostas[0]
    if isinstance(r, Exception):
        raise r
    return r
