import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from esteira import cli
from esteira.painel.app import criar_app


class CofreFalso:
    def __init__(self, dados=None):
        self.dados = dict(dados or {})

    def ler(self, campo):
        return self.dados.get(campo)

    def gravar(self, campo, valor):
        self.dados[campo] = valor


COMPLETO = {"codigo": "sal$hash", "chave_sessao": "chave"}


class Servidor:
    def __init__(self):
        self.chamadas = []

    def __call__(self, app, **kwargs):
        self.chamadas.append((app, kwargs))


@pytest.fixture
def estatico(tmp_path, monkeypatch):
    pasta = tmp_path / "estatico"
    pasta.mkdir()
    (pasta / "index.html").write_text("<html>painel</html>", "utf-8")
    monkeypatch.setattr(cli, "ESTATICO", pasta)
    return pasta


def _args(*extra, tmp_path=None):
    import argparse

    return argparse.Namespace(
        rede="--rede" in extra, porta=8765, cortes=str(tmp_path) if tmp_path else None, acao=None
    )


def test_sem_build_sai_com_erro(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "ESTATICO", tmp_path / "nao-existe")
    servidor = Servidor()
    assert cli._painel(_args(tmp_path=tmp_path), servidor, CofreFalso()) == 1
    assert 'Painel sem build: rode "npm install" e "npm run build" em painel-web/' in capsys.readouterr().err
    assert servidor.chamadas == []


@pytest.mark.parametrize("dados", [{}, {"codigo": "x$y"}, {"chave_sessao": "k"}])
def test_rede_sem_codigo_sai_com_erro(estatico, tmp_path, capsys, dados):
    servidor = Servidor()
    assert cli._painel(_args("--rede", tmp_path=tmp_path), servidor, CofreFalso(dados)) == 1
    assert 'Sem código de acesso: rode "python -m esteira painel codigo"' in capsys.readouterr().err
    assert servidor.chamadas == []


@pytest.mark.parametrize("ausente", ["fastapi", "uvicorn"])
def test_sem_fastapi_ou_uvicorn_avisa_e_sai_1(estatico, tmp_path, monkeypatch, capsys, ausente):
    monkeypatch.setitem(sys.modules, ausente, None)  # import simulado ausente
    for carregado in ("esteira.painel.app", "esteira.painel.rotas"):
        monkeypatch.delitem(sys.modules, carregado, raising=False)
    servidor = Servidor()
    assert cli._painel(_args(tmp_path=tmp_path), servidor, CofreFalso()) == 1
    assert (
        'O painel precisa de fastapi e uvicorn: rode ".venv\\Scripts\\python.exe -m pip install fastapi uvicorn"'
        in capsys.readouterr().err
    )
    assert servidor.chamadas == []


def test_local_serve_em_127(estatico, tmp_path, capsys):
    servidor = Servidor()
    assert cli._painel(_args(tmp_path=tmp_path), servidor, CofreFalso()) == 0
    assert servidor.chamadas[0][1] == {"host": "127.0.0.1", "port": 8765}
    assert "Painel em http://127.0.0.1:8765" in capsys.readouterr().out


def test_rede_serve_em_0000_e_mostra_aviso(estatico, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "_ip_local", lambda: "192.168.0.7")
    servidor = Servidor()
    assert cli._painel(_args("--rede", tmp_path=tmp_path), servidor, CofreFalso(COMPLETO)) == 0
    assert servidor.chamadas[0][1] == {"host": "0.0.0.0", "port": 8765}
    saida = capsys.readouterr().out
    assert "Painel na rede: http://192.168.0.7:8765" in saida
    assert "Não use em rede pública" in saida


def test_hosts_confiaveis(estatico, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_ip_local", lambda: "192.168.0.7")
    local = Servidor()
    cli._painel(_args(tmp_path=tmp_path), local, CofreFalso())
    cliente = TestClient(local.chamadas[0][0])
    assert cliente.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert cliente.get("/", headers={"Host": "192.168.0.7"}).status_code == 400
    assert cliente.get("/", headers={"Host": "127.0.0.1:8765"}).status_code == 200
    rede = Servidor()
    cli._painel(_args("--rede", tmp_path=tmp_path), rede, CofreFalso(COMPLETO))
    cliente = TestClient(rede.chamadas[0][0])
    assert cliente.get("/", headers={"Host": "192.168.0.7:8765"}).status_code == 200
    assert cliente.get("/", headers={"Host": "evil.example"}).status_code == 400


def test_hosts_no_criar_app(tmp_path):
    app = criar_app(tmp_path, hosts=["127.0.0.1", "localhost"])
    cliente = TestClient(app)
    assert cliente.get("/api/episodios", headers={"Host": "evil.example"}).status_code == 400
    assert cliente.get("/api/episodios", headers={"Host": "127.0.0.1:8765"}).status_code == 200


def test_cortes_relativo_resolve_pelo_diretorio_atual(estatico, tmp_path, monkeypatch):
    (tmp_path / "rel").mkdir()
    monkeypatch.chdir(tmp_path)
    servidor = Servidor()
    args = _args(tmp_path=None)
    args.cortes = "rel"
    cli._painel(args, servidor, CofreFalso())
    assert servidor.chamadas[0][0].state.cortes == (tmp_path / "rel").resolve()


def test_painel_codigo_mostra_e_nao_serve(monkeypatch, capsys):
    monkeypatch.setattr(cli, "CofreKeyring", lambda: CofreFalso())
    monkeypatch.setattr(cli, "gerar_codigo", lambda cofre: "ABCD2345")
    assert cli.principal(["painel", "codigo"]) == 0
    assert "Código de acesso: ABCD2345 (anote; ele não será mostrado de novo)" in capsys.readouterr().out


def test_rota_do_react_devolve_index(tmp_path, estatico):
    (estatico / "assets").mkdir()
    (estatico / "assets" / "a.js").write_text("console.log(1)", "utf-8")
    cliente = TestClient(criar_app(tmp_path, estatico=estatico))
    resposta = cliente.get("/episodios/x")
    assert resposta.status_code == 200
    assert resposta.text == "<html>painel</html>"
    assert cliente.get("/").text == "<html>painel</html>"
    assert cliente.get("/assets/a.js").text == "console.log(1)"
    nao_existe = cliente.get("/api/nao-existe")
    assert nao_existe.status_code == 404
    assert nao_existe.headers["content-type"].startswith("application/json")
    assert cliente.get("/api/episodios").status_code == 200


def test_fallback_nao_sai_da_pasta(tmp_path, estatico):
    (tmp_path / "segredo.txt").write_text("segredo", "utf-8")
    cliente = TestClient(criar_app(tmp_path, estatico=estatico))
    assert cliente.get("/..%2Fsegredo.txt").text == "<html>painel</html>"


@pytest.mark.parametrize("caminho", ["/x%00y", "/%00", "/assets%00/a.js"])
def test_fallback_com_nulo_devolve_index(tmp_path, estatico, caminho):
    cliente = TestClient(criar_app(tmp_path, estatico=estatico))
    resposta = cliente.get(caminho)
    assert resposta.status_code == 200
    assert resposta.text == "<html>painel</html>"


def test_extra_painel_pede_as_versoes_testadas():
    import tomllib
    from pathlib import Path

    projeto = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text("utf-8"))
    assert projeto["project"]["optional-dependencies"]["painel"] == ["fastapi>=0.162", "uvicorn>=0.54"]


def test_cli_funciona_sem_fastapi():
    codigo = (
        "import sys\n"
        "from esteira import cli\n"
        "try:\n"
        "    cli.principal(['revisao', 'C:/nao/existe/pasta'])\n"
        "except BaseException:\n"
        "    pass\n"
        "assert 'fastapi' not in sys.modules and 'uvicorn' not in sys.modules\n"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stderr


def test_painel_montagem_falsa_por_ambiente(estatico, tmp_path, monkeypatch):
    import time

    from esteira.cortar import pasta_do_corte
    from esteira.modelos import Corte
    from tests.auxiliares_painel import criar_episodio

    monkeypatch.setenv("ESTEIRA_PAINEL_MONTAGEM_FALSA", "1")
    corte = Corte(1, "Um", 10, 20, "tenso")
    pasta = criar_episodio(tmp_path, "ep", [corte], {1})
    mp4 = pasta_do_corte(pasta, corte) / "corte.mp4"
    mp4.write_bytes(b"bytes-do-corte")
    servidor = Servidor()
    assert cli._painel(_args(tmp_path=tmp_path), servidor, CofreFalso()) == 0
    app = servidor.chamadas[0][0]
    try:
        fila = app.state.fila
        montar = fila._executar.keywords["montar"]
        assert montar(pasta, 1) == "ok"
        assert mp4.read_bytes() == b"bytes-do-corte"
        mp4.unlink()
        assert montar(pasta, 1) == "ok"
        assert mp4.read_bytes() == b""
    finally:
        fila.parar(2)


def test_painel_sem_variavel_usa_a_montagem_real(estatico, tmp_path, monkeypatch):
    monkeypatch.delenv("ESTEIRA_PAINEL_MONTAGEM_FALSA", raising=False)
    servidor = Servidor()
    cli._painel(_args(tmp_path=tmp_path), servidor, CofreFalso())
    app = servidor.chamadas[0][0]
    try:
        assert app.state.fila._executar.keywords["montar"].__name__ != "_montagem_falsa"
    finally:
        app.state.fila.parar(2)


def test_painel_pasta_de_musicas_por_ambiente(estatico, tmp_path, monkeypatch):
    outra = tmp_path / "musicas-de-teste"
    monkeypatch.setenv("ESTEIRA_PAINEL_PASTA_MUSICAS", str(outra))
    servidor = Servidor()
    assert cli._painel(_args(tmp_path=tmp_path), servidor, CofreFalso()) == 0
    app = servidor.chamadas[0][0]
    try:
        assert app.state.pasta_musicas == outra.resolve()
    finally:
        app.state.fila.parar(2)


def test_painel_sem_variavel_usa_a_pasta_de_musicas_real(estatico, tmp_path, monkeypatch):
    monkeypatch.delenv("ESTEIRA_PAINEL_PASTA_MUSICAS", raising=False)
    servidor = Servidor()
    cli._painel(_args(tmp_path=tmp_path), servidor, CofreFalso())
    app = servidor.chamadas[0][0]
    try:
        assert app.state.pasta_musicas == cli.MUSICAS
    finally:
        app.state.fila.parar(2)


def test_painel_imagem_falsa_por_ambiente(estatico, tmp_path, monkeypatch):
    import io

    from PIL import Image

    monkeypatch.setenv("ESTEIRA_PAINEL_IMAGEM_FALSA", "1")
    servidor = Servidor()
    assert cli._painel(_args(tmp_path=tmp_path), servidor, CofreFalso()) == 0
    app = servidor.chamadas[0][0]
    try:
        assert app.state.tem_chave("openai") is True and app.state.tem_chave("google") is True
        assert set(app.state.provedores) == {"openai", "google"}
        for nome, fabrica in app.state.provedores.items():
            provedor = fabrica({})
            assert provedor.nome == nome
            imagem = Image.open(io.BytesIO(provedor.gerar("qualquer coisa")))
            assert imagem.size == (1024, 1536)
    finally:
        app.state.fila.parar(2)


def test_painel_sem_variavel_usa_os_provedores_reais(estatico, tmp_path, monkeypatch):
    monkeypatch.delenv("ESTEIRA_PAINEL_IMAGEM_FALSA", raising=False)
    servidor = Servidor()
    cli._painel(_args(tmp_path=tmp_path), servidor, CofreFalso())
    app = servidor.chamadas[0][0]
    try:
        assert app.state.provedores is None
    finally:
        app.state.fila.parar(2)
