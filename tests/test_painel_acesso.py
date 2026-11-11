import pytest
from fastapi.testclient import TestClient

from esteira.painel.acesso import ALFABETO, gerar_codigo
from esteira.painel.app import criar_app

DIA = 86400


class CofreFalso:
    def __init__(self):
        self.dados: dict[str, str] = {}

    def ler(self, campo):
        return self.dados.get(campo)

    def gravar(self, campo, valor):
        self.dados[campo] = valor


class Relogio:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def _app(tmp_path, cofre, relogio, rede=True):
    (tmp_path / "cortes").mkdir(exist_ok=True)
    return TestClient(criar_app(tmp_path / "cortes", rede=rede, cofre=cofre, relogio=relogio))


def _entrar(cliente, codigo):
    return cliente.post("/api/entrar", json={"codigo": codigo})


def test_codigo_tem_formato():
    assert ALFABETO == "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    codigo = gerar_codigo(CofreFalso())
    assert len(codigo) == 8
    assert all(c in ALFABETO for c in codigo)


def test_cofre_nao_guarda_codigo_em_claro():
    cofre = CofreFalso()
    codigo = gerar_codigo(cofre)
    assert cofre.dados.keys() >= {"codigo", "chave_sessao"}
    assert all(codigo not in valor for valor in cofre.dados.values())


def test_sem_rede_nao_pede_login(tmp_path):
    cliente = _app(tmp_path, None, Relogio(), rede=False)
    assert cliente.get("/api/episodios").status_code == 200


def test_com_rede_sem_sessao_401(tmp_path):
    cofre = CofreFalso()
    gerar_codigo(cofre)
    resposta = _app(tmp_path, cofre, Relogio()).get("/api/episodios")
    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "Entre com o código de acesso."}


def test_sessao_decide_pelo_caminho_do_roteador(tmp_path, monkeypatch):
    """Se url.path divergir do scope["path"] (o que o roteador usa), a trava segue o roteador."""
    from starlette.datastructures import URL
    from starlette.requests import HTTPConnection

    monkeypatch.setattr(HTTPConnection, "url", property(lambda _self: URL("http://testserver/api/entrar")))
    cofre = CofreFalso()
    gerar_codigo(cofre)
    resposta = _app(tmp_path, cofre, Relogio()).get("/api/episodios")
    assert resposta.status_code == 401


def test_entrar_e_usar_cookie(tmp_path):
    cofre = CofreFalso()
    codigo = gerar_codigo(cofre)
    cliente = _app(tmp_path, cofre, Relogio())
    resposta = _entrar(cliente, codigo)
    assert resposta.status_code == 204
    cabecalho = resposta.headers["set-cookie"]
    assert "painel_sessao=" in cabecalho
    assert "HttpOnly" in cabecalho
    assert "samesite=strict" in cabecalho.lower()
    assert "Max-Age=604800" in cabecalho
    assert "Path=/" in cabecalho
    assert cliente.get("/api/episodios").status_code == 200


def test_codigo_errado_401(tmp_path):
    cofre = CofreFalso()
    gerar_codigo(cofre)
    assert _entrar(_app(tmp_path, cofre, Relogio()), "ZZZZZZZZ").status_code == 401


def test_codigo_minusculo_aceito(tmp_path):
    cofre = CofreFalso()
    codigo = gerar_codigo(cofre)
    assert _entrar(_app(tmp_path, cofre, Relogio()), codigo.lower()).status_code == 204


def test_trava_depois_de_5_erros(tmp_path):
    cofre = CofreFalso()
    codigo = gerar_codigo(cofre)
    relogio = Relogio()
    cliente = _app(tmp_path, cofre, relogio)
    for _ in range(5):
        assert _entrar(cliente, "ZZZZZZZZ").status_code == 401
    resposta = _entrar(cliente, codigo)
    assert resposta.status_code == 429
    assert resposta.json()["detail"].startswith("Muitas tentativas. Tente de novo em ")
    relogio.t += 61
    assert _entrar(cliente, codigo).status_code == 204


def test_acerto_zera_contador_de_erros(tmp_path):
    cofre = CofreFalso()
    codigo = gerar_codigo(cofre)
    cliente = _app(tmp_path, cofre, Relogio())
    for _ in range(4):
        _entrar(cliente, "ZZZZZZZZ")
    assert _entrar(cliente, codigo).status_code == 204
    for _ in range(4):
        assert _entrar(cliente, "ZZZZZZZZ").status_code == 401
    assert _entrar(cliente, codigo).status_code == 204


def test_sessao_expira_em_7_dias(tmp_path):
    cofre = CofreFalso()
    codigo = gerar_codigo(cofre)
    relogio = Relogio()
    cliente = _app(tmp_path, cofre, relogio)
    _entrar(cliente, codigo)
    relogio.t += 7 * DIA - 1
    assert cliente.get("/api/episodios").status_code == 200
    relogio.t += 2
    assert cliente.get("/api/episodios").status_code == 401


def test_cookie_adulterado_401(tmp_path):
    cofre = CofreFalso()
    gerar_codigo(cofre)
    cliente = _app(tmp_path, cofre, Relogio())
    cliente.cookies.set("painel_sessao", f"{int(Relogio()() + DIA)}.{'0' * 64}")
    assert cliente.get("/api/episodios").status_code == 401


@pytest.mark.parametrize("cookie", ["1800086400.é", "é.abc", "²³.abc", "١٨٠٠٠٨٦٤٠٠.abc", "1800086400.ａｂ"])
def test_cookie_nao_ascii_e_invalido(cookie):
    from esteira.painel.acesso import Porteiro

    cofre = CofreFalso()
    gerar_codigo(cofre)
    assert Porteiro(cofre, Relogio()).sessao_valida(cookie) is False


def test_cookie_nao_ascii_401_e_nao_500(tmp_path):
    cofre = CofreFalso()
    gerar_codigo(cofre)
    cliente = _app(tmp_path, cofre, Relogio())
    cabecalho = "painel_sessao=1800086400.é".encode("utf-8")
    assert cliente.get("/api/episodios", headers={"cookie": cabecalho}).status_code == 401


def test_reiniciar_servidor_mantem_sessao(tmp_path):
    cofre = CofreFalso()
    codigo = gerar_codigo(cofre)
    relogio = Relogio()
    primeiro = _app(tmp_path, cofre, relogio)
    _entrar(primeiro, codigo)
    segundo = _app(tmp_path, cofre, relogio)
    segundo.cookies.set("painel_sessao", primeiro.cookies["painel_sessao"])
    assert segundo.get("/api/episodios").status_code == 200


def test_novo_codigo_derruba_sessoes(tmp_path):
    cofre = CofreFalso()
    codigo = gerar_codigo(cofre)
    cliente = _app(tmp_path, cofre, Relogio())
    _entrar(cliente, codigo)
    assert cliente.get("/api/episodios").status_code == 200
    gerar_codigo(cofre)
    assert cliente.get("/api/episodios").status_code == 401


def test_trava_resiste_a_tentativas_simultaneas():
    import threading

    from esteira.painel.acesso import CodigoErrado, Porteiro, Travado

    cofre = CofreFalso()
    gerar_codigo(cofre)
    porteiro = Porteiro(cofre, Relogio())
    total = 20
    barreira = threading.Barrier(total)
    resultados = []

    def tentar():
        barreira.wait()
        try:
            porteiro.entrar("ERRADO00")
        except (CodigoErrado, Travado) as erro:
            resultados.append(type(erro))

    fios = [threading.Thread(target=tentar) for _ in range(total)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join()
    assert resultados.count(CodigoErrado) == 5
    assert resultados.count(Travado) == total - 5


def test_trava_e_por_aparelho_e_dobra():
    from esteira.painel.acesso import CodigoErrado, Porteiro, Travado

    cofre = CofreFalso()
    codigo = gerar_codigo(cofre)
    relogio = Relogio()
    porteiro = Porteiro(cofre, relogio)
    for _ in range(5):
        with pytest.raises(CodigoErrado):
            porteiro.entrar("ZZZZZZZZ", "10.0.0.9")
    with pytest.raises(Travado):
        porteiro.entrar(codigo, "10.0.0.9")
    assert porteiro.entrar(codigo, "10.0.0.2")  # o dono, em outro aparelho, entra
    relogio.t += 61
    for _ in range(5):
        with pytest.raises(CodigoErrado):
            porteiro.entrar("ZZZZZZZZ", "10.0.0.9")
    relogio.t += 61
    with pytest.raises(Travado):  # a segunda trava dura 120 s
        porteiro.entrar(codigo, "10.0.0.9")


def test_sair_apaga_o_cookie(tmp_path):
    cofre = CofreFalso()
    codigo = gerar_codigo(cofre)
    cliente = _app(tmp_path, cofre, Relogio())
    _entrar(cliente, codigo)
    resposta = cliente.post("/api/sair")
    assert resposta.status_code == 204
    assert 'painel_sessao=""' in resposta.headers["set-cookie"] or "Max-Age=0" in resposta.headers["set-cookie"]
