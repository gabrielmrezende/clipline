import json

import pytest

from esteira.publicar import credenciais, http, youtube
from esteira.publicar.credenciais import ErroConexao
from esteira.publicar.http import ErroRede, Resultado
from esteira.publicar.youtube import YouTube
from tests.auxiliares_publicar import DATA, TEXTOS, Cofre, Resposta, Servidor, erro_http

TOKEN = {"access_token": "SEGREDO-ACESSO"}
CHEIO = {"youtube:client_id": "cid", "youtube:client_secret": "csec", "youtube:refresh_token": "rt"}


@pytest.fixture
def video(tmp_path):
    caminho = tmp_path / "Corte 1.mp4"
    caminho.write_bytes(b"VIDEO")
    return caminho


def _preparar(monkeypatch, respostas, dados=CHEIO):
    servidor = Servidor(respostas)
    cofre = Cofre(dados)
    monkeypatch.setattr(http, "_urlopen", servidor)
    monkeypatch.setattr(credenciais, "ler", cofre.ler)
    monkeypatch.setattr(credenciais, "gravar", cofre.gravar)
    return servidor


def _envio_ok():
    return [Resposta(200, TOKEN), Resposta(200, b"", {"Location": "https://up/sessao"}), Resposta(201, {"id": "abc123"})]


def test_envio_privado(monkeypatch, video):
    servidor = _preparar(monkeypatch, _envio_ok())
    r = YouTube().publicar(video, TEXTOS, DATA, "privado")
    assert r == Resultado("privado", "https://youtube.com/shorts/abc123", "abc123")
    meta = json.loads(servidor.pedidos[1].data)
    assert meta["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    assert meta["snippet"] == {"title": TEXTOS.youtube_titulo, "description": TEXTOS.youtube_descricao, "categoryId": "22"}
    assert servidor.pedidos[1].get_header("Authorization") == "Bearer SEGREDO-ACESSO"
    assert servidor.pedidos[2].full_url == "https://up/sessao"
    assert servidor.pedidos[2].get_method() == "PUT"
    assert servidor.pedidos[2].data == b"VIDEO"


def test_envio_agendado_tem_publish_at(monkeypatch, video):
    servidor = _preparar(monkeypatch, _envio_ok())
    r = YouTube().publicar(video, TEXTOS, DATA, "agendado")
    assert r.estado == "publicado"
    assert json.loads(servidor.pedidos[1].data)["status"]["publishAt"] == "2026-11-08T21:00:00Z"


def test_sem_refresh_token_pede_reconexao(monkeypatch, video):
    _preparar(monkeypatch, [], {"youtube:client_id": "cid", "youtube:client_secret": "csec"})
    with pytest.raises(ErroConexao, match="reconecte com publicar conectar youtube$"):
        YouTube().publicar(video, TEXTOS, DATA, "privado")


def test_token_recusado_pede_reconexao(monkeypatch, video):
    _preparar(monkeypatch, [erro_http(400, {"error": "invalid_grant"})])
    with pytest.raises(ErroConexao, match="reconecte com publicar conectar youtube$"):
        YouTube().publicar(video, TEXTOS, DATA, "privado")


def test_503_e_temporario(monkeypatch, video):
    _preparar(monkeypatch, [Resposta(200, TOKEN), erro_http(503)])
    with pytest.raises(ErroRede) as erro:
        YouTube().publicar(video, TEXTOS, DATA, "privado")
    assert erro.value.temporario


def test_cota_esgotada_403_nao_e_temporario(monkeypatch, video):
    _preparar(monkeypatch, [Resposta(200, TOKEN), erro_http(403, {"error": {"message": "quota exceeded"}})])
    with pytest.raises(ErroRede, match="quota exceeded") as erro:
        YouTube().publicar(video, TEXTOS, DATA, "privado")
    assert not erro.value.temporario


def test_token_nunca_aparece_no_erro(monkeypatch, video):
    _preparar(monkeypatch, [Resposta(200, TOKEN), erro_http(400, {"detalhe": "SEGREDO-ACESSO"})])
    with pytest.raises(ErroRede) as erro:
        YouTube().publicar(video, TEXTOS, DATA, "privado")
    assert "SEGREDO" not in str(erro.value)


def test_agendado_com_data_passada_publica_ja(monkeypatch, video):
    from datetime import datetime, timedelta, timezone
    servidor = _preparar(monkeypatch, _envio_ok())
    passado = datetime(2020, 1, 1, 18, 0, tzinfo=timezone(timedelta(hours=-3)))
    r = YouTube().publicar(video, TEXTOS, passado, "agendado")
    status = json.loads(servidor.pedidos[1].data)["status"]
    assert status == {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    assert r.estado == "publicado"
