from datetime import datetime
from urllib.parse import quote

from fastapi.testclient import TestClient

from esteira.cortar import pasta_do_corte
from esteira.modelos import Corte
from esteira.painel.app import criar_app
from esteira.publicar.post import ler_post, versao_post
from tests.auxiliares_painel import criar_episodio

NOME = "Entre Assuntos 03 - Arthur Cerqueira (teste capcut)"
AGORA = datetime(2026, 11, 7, 10)
CORTE = Corte(1, "Um", 10, 20, "tenso")


def _montar(tmp_path):
    (tmp_path / "cortes").mkdir(exist_ok=True)
    pasta = criar_episodio(tmp_path / "cortes", NOME, [CORTE], {1})
    cliente = TestClient(criar_app(tmp_path / "cortes", agora=lambda: AGORA))
    return cliente, pasta_do_corte(pasta, CORTE) / "post.md"


def _url(sufixo: str = "") -> str:
    return "/api/episodios/" + quote(NOME) + "/cortes/1/post" + sufixo


def _campos(caminho, **troca) -> dict:
    campos = dict(ler_post(caminho).__dict__)
    campos.update(troca)
    return campos


def test_get_post(tmp_path):
    cliente, post = _montar(tmp_path)
    resposta = cliente.get(_url())
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["campos"] == ler_post(post).__dict__
    assert "Música" in dados["somente_leitura"]
    assert len(dados["versao"]) == 64
    assert dados["erro"] is None
    assert dados["redes"] == ["youtube", "tiktok"]
    assert dados["credito"] is None


def test_conferir_nao_grava(tmp_path):
    cliente, post = _montar(tmp_path)
    antes = post.read_bytes()
    resposta = cliente.post(_url("/conferir"), json={"campos": _campos(post, youtube_titulo="x" * 101)})
    assert resposta.status_code == 200
    assert "youtube: título com mais de 100 caracteres" in resposta.json()["avisos"]
    assert post.read_bytes() == antes


def test_put_grava_e_devolve_versao_nova(tmp_path):
    cliente, post = _montar(tmp_path)
    versao = cliente.get(_url()).json()["versao"]
    resposta = cliente.put(
        _url(), json={"versao": versao, "campos": _campos(post, youtube_titulo="Título novo")}
    )
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["versao"] == versao_post(post) != versao
    assert ler_post(post).youtube_titulo == "Título novo"


def test_put_conflito_409(tmp_path):
    cliente, post = _montar(tmp_path)
    versao = cliente.get(_url()).json()["versao"]
    post.write_bytes(post.read_bytes() + b"\nmudou por fora\n")
    por_fora = post.read_bytes()
    resposta = cliente.put(
        _url(), json={"versao": versao, "campos": _campos(post, youtube_titulo="Outro")}
    )
    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["detail"] == "O post.md mudou desde que você abriu."
    assert corpo["versao_atual"] == versao_post(post)
    assert post.read_bytes() == por_fora


def test_put_com_avisos_grava_mesmo_assim(tmp_path):
    cliente, post = _montar(tmp_path)
    versao = cliente.get(_url()).json()["versao"]
    resposta = cliente.put(
        _url(), json={"versao": versao, "campos": _campos(post, youtube_titulo="x" * 101)}
    )
    assert resposta.status_code == 200
    assert "youtube: título com mais de 100 caracteres" in resposta.json()["avisos"]
    assert ler_post(post).youtube_titulo == "x" * 101


def test_post_quebrado_devolve_erro(tmp_path):
    cliente, post = _montar(tmp_path)
    texto = post.read_text("utf-8")
    post.write_text(texto.split("## TikTok")[0], "utf-8")
    resposta = cliente.get(_url())
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["erro"] == "post.md sem a seção ## TikTok"
    assert dados["versao"] is None


def test_put_sem_post_404(tmp_path):
    cliente, post = _montar(tmp_path)
    campos = _campos(post)
    post.unlink()
    resposta = cliente.put(_url(), json={"versao": "a" * 64, "campos": campos})
    assert resposta.status_code == 404


def test_put_corpo_invalido_422(tmp_path):
    cliente, post = _montar(tmp_path)
    resposta = cliente.put(_url(), json={"versao": "a", "campos": {"youtube_titulo": "x"}})
    assert resposta.status_code == 422


def test_put_titulo_com_quebra_de_linha_422(tmp_path):
    cliente, post = _montar(tmp_path)
    antes = post.read_bytes()
    versao = versao_post(post)
    for titulo in ("linha 1\nlinha 2", "linha 1\rlinha 2"):
        resposta = cliente.put(
            _url(), json={"versao": versao, "campos": _campos(post, youtube_titulo=titulo)}
        )
        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "O título do YouTube não pode ter quebra de linha."
    assert post.read_bytes() == antes


def test_put_linha_com_cabecalho_422(tmp_path):
    cliente, post = _montar(tmp_path)
    antes = post.read_bytes()
    versao = versao_post(post)
    resposta = cliente.put(
        _url(),
        json={"versao": versao, "campos": _campos(post, tiktok="texto\n## Outra seção\nmais")},
    )
    assert resposta.status_code == 422
    assert resposta.json()["detail"] == "Nenhum texto pode ter linha começando com '## '."
    assert post.read_bytes() == antes


def test_conferir_lista_avisos_de_formato(tmp_path):
    cliente, post = _montar(tmp_path)
    antes = post.read_bytes()
    resposta = cliente.post(
        _url("/conferir"),
        json={"campos": _campos(post, youtube_titulo="a\nb", instagram="x\n## y")},
    )
    avisos = resposta.json()["avisos"]
    assert "O título do YouTube não pode ter quebra de linha." in avisos
    assert "Nenhum texto pode ter linha começando com '## '." in avisos
    assert post.read_bytes() == antes


def test_put_escrita_proibida_403(tmp_path, monkeypatch):
    from esteira.caminhos import EscritaProibida

    def recusar(*_args, **_kwargs):
        raise EscritaProibida("fora das pastas permitidas")

    monkeypatch.setattr("esteira.publicar.post.garantir_escrita", recusar)
    cliente, post = _montar(tmp_path)
    antes = post.read_bytes()
    resposta = cliente.put(
        _url(), json={"versao": versao_post(post), "campos": _campos(post, youtube_titulo="Novo")}
    )
    assert resposta.status_code == 403
    assert resposta.json()["detail"].startswith("Escrita não permitida")
    assert post.read_bytes() == antes
