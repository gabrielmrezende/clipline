import json

import pytest

from esteira.publicar import credenciais, http
from esteira.publicar.credenciais import ErroConexao
from esteira.publicar.http import ErroRede, Resultado
from esteira.publicar.tiktok import TikTok, partes
from tests.auxiliares_publicar import DATA, TEXTOS, Cofre, Resposta, Servidor, erro_http

OK = {"code": "ok", "message": ""}


def _token():
    return Resposta(200, {"access_token": "AT", "refresh_token": "RT2"})


def _preparar(monkeypatch, respostas):
    servidor = Servidor(respostas)
    cofre = Cofre({"tiktok:client_key": "ck", "tiktok:client_secret": "cs", "tiktok:refresh_token": "RT"})
    monkeypatch.setattr(http, "_urlopen", servidor)
    monkeypatch.setattr(credenciais, "ler", cofre.ler)
    monkeypatch.setattr(credenciais, "gravar", cofre.gravar)
    return servidor, cofre


@pytest.fixture
def video(tmp_path):
    caminho = tmp_path / "Corte 1.mp4"
    caminho.write_bytes(b"V" * 1000)
    return caminho


def test_partes_de_85_mb():
    lista = partes(85_593_673)
    assert len(lista) == 8
    assert lista[0] == (0, 10_485_759)
    assert lista[-1] == (7 * 10_485_760, 85_593_672)


def test_video_pequeno_uma_parte():
    assert partes(1000) == [(0, 999)]


def test_rascunho_usa_inbox(monkeypatch, video):
    servidor, cofre = _preparar(monkeypatch, [
        _token(),
        Resposta(200, {"data": {"publish_id": "P1", "upload_url": "https://up/1"}, "error": OK}),
        Resposta(201, b""),
    ])
    r = TikTok(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "rascunho")
    assert r == Resultado("rascunho", "", "P1")
    assert servidor.pedidos[1].full_url.endswith("/v2/post/publish/inbox/video/init/")
    corpo = json.loads(servidor.pedidos[1].data)
    assert corpo == {"source_info": {"source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000, "total_chunk_count": 1}}
    assert servidor.pedidos[2].get_header("Content-range") == "bytes 0-999/1000"
    assert cofre.dados["tiktok:refresh_token"] == "RT2"


def test_direto_publica(monkeypatch, video):
    servidor, _ = _preparar(monkeypatch, [
        _token(),
        Resposta(200, {"data": {"privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]}, "error": OK}),
        Resposta(200, {"data": {"publish_id": "P2", "upload_url": "https://up/2"}, "error": OK}),
        Resposta(201, b""),
        Resposta(200, {"data": {"status": "PROCESSING_UPLOAD"}, "error": OK}),
        Resposta(200, {"data": {"status": "PUBLISH_COMPLETE"}, "error": OK}),
    ])
    r = TikTok(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "direto")
    assert r == Resultado("publicado", "https://www.tiktok.com/@tudoepoliticabr", "P2")
    info = json.loads(servidor.pedidos[2].data)["post_info"]
    assert info["title"] == TEXTOS.tiktok and info["privacy_level"] == "PUBLIC_TO_EVERYONE"


def test_direto_sem_publico_falha(monkeypatch, video):
    _preparar(monkeypatch, [_token(), Resposta(200, {"data": {"privacy_level_options": ["SELF_ONLY"]}, "error": OK})])
    with pytest.raises(ErroRede, match="não permite público") as erro:
        TikTok(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "direto")
    assert not erro.value.temporario


def test_direto_falha_na_publicacao(monkeypatch, video):
    _preparar(monkeypatch, [
        _token(),
        Resposta(200, {"data": {"privacy_level_options": ["PUBLIC_TO_EVERYONE"]}, "error": OK}),
        Resposta(200, {"data": {"publish_id": "P2", "upload_url": "https://up/2"}, "error": OK}),
        Resposta(201, b""),
        Resposta(200, {"data": {"status": "FAILED", "fail_reason": "video_pull_failed"}, "error": OK}),
    ])
    with pytest.raises(ErroRede, match="video_pull_failed"):
        TikTok(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "direto")


def test_token_recusado_pede_reconexao(monkeypatch, video):
    _preparar(monkeypatch, [erro_http(400, {"error": "invalid_grant"})])
    with pytest.raises(ErroConexao, match="conectar tiktok$"):
        TikTok(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "rascunho")


def test_erro_da_api_no_corpo(monkeypatch, video):
    _preparar(monkeypatch, [_token(), Resposta(200, {"data": {}, "error": {"code": "spam_risk_too_many_posts", "message": "muitos"}})])
    with pytest.raises(ErroRede, match="spam_risk_too_many_posts"):
        TikTok(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "rascunho")


def test_status_falha_depois_do_envio_e_incerto(monkeypatch, video):
    from esteira.publicar.http import ErroIncerto
    _preparar(monkeypatch, [
        _token(),
        Resposta(200, {"data": {"privacy_level_options": ["PUBLIC_TO_EVERYONE"]}, "error": OK}),
        Resposta(200, {"data": {"publish_id": "P2", "upload_url": "https://up/2"}, "error": OK}),
        Resposta(201, b""),
        erro_http(503),
    ])
    with pytest.raises(ErroIncerto):
        TikTok(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "direto")


def test_direto_com_ia_marca_is_aigc(monkeypatch, video):
    servidor, _ = _preparar(monkeypatch, [
        _token(),
        Resposta(200, {"data": {"privacy_level_options": ["PUBLIC_TO_EVERYONE"]}, "error": OK}),
        Resposta(200, {"data": {"publish_id": "P2", "upload_url": "https://up/2"}, "error": OK}),
        Resposta(201, b""),
        Resposta(200, {"data": {"status": "PUBLISH_COMPLETE"}, "error": OK}),
    ])
    TikTok(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "direto", ia=True)
    assert json.loads(servidor.pedidos[2].data)["post_info"]["is_aigc"] is True
