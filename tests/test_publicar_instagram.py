import time
import urllib.parse

import pytest

from esteira.publicar import credenciais, http
from esteira.publicar.credenciais import ErroConexao
from esteira.publicar.http import ErroRede, Resultado
from esteira.publicar.instagram import Instagram
from tests.auxiliares_publicar import DATA, TEXTOS, Cofre, Resposta, Servidor, erro_http


@pytest.fixture
def video(tmp_path):
    caminho = tmp_path / "Corte 1.mp4"
    caminho.write_bytes(b"VIDEO")
    return caminho


def _preparar(monkeypatch, respostas, renovado_ha=60.0):
    servidor = Servidor(respostas)
    cofre = Cofre({
        "instagram:token": "TK",
        "instagram:user_id": "U1",
        "instagram:renovado_em": str(time.time() - renovado_ha),
    })
    monkeypatch.setattr(http, "_urlopen", servidor)
    monkeypatch.setattr(credenciais, "ler", cofre.ler)
    monkeypatch.setattr(credenciais, "gravar", cofre.gravar)
    return servidor, cofre


def _sequencia(status_final="FINISHED"):
    return [
        Resposta(200, {"id": "C1", "uri": "https://rupload.facebook.com/ig-api-upload/v21.0/C1"}),
        Resposta(200, {"success": True}),
        Resposta(200, {"status_code": "IN_PROGRESS"}),
        Resposta(200, {"status_code": status_final}),
        Resposta(200, {"id": "M1"}),
        Resposta(200, {"permalink": "https://www.instagram.com/reel/X/"}),
    ]


def test_reels_publicado(monkeypatch, video):
    servidor, _ = _preparar(monkeypatch, _sequencia())
    esperas = []
    r = Instagram(esperar=esperas.append).publicar(video, TEXTOS, DATA, "")
    assert r == Resultado("publicado", "https://www.instagram.com/reel/X/", "M1")
    criar = urllib.parse.parse_qs(servidor.pedidos[0].data.decode())
    assert servidor.pedidos[0].full_url == "https://graph.instagram.com/v21.0/U1/media"
    assert criar["media_type"] == ["REELS"] and criar["upload_type"] == ["resumable"]
    assert "Ice Flow" in criar["caption"][0]
    envio = servidor.pedidos[1]
    assert envio.get_header("Authorization") == "OAuth TK"
    assert envio.get_header("File_size") == "5"
    assert envio.data == b"VIDEO"
    assert urllib.parse.parse_qs(servidor.pedidos[4].data.decode())["creation_id"] == ["C1"]
    assert esperas == [10]


def test_status_error_nao_e_temporario(monkeypatch, video):
    _preparar(monkeypatch, _sequencia("ERROR")[:4])
    with pytest.raises(ErroRede) as erro:
        Instagram(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "")
    assert not erro.value.temporario


def test_tempo_de_processamento_esgotado(monkeypatch, video):
    respostas = _sequencia()[:2] + [Resposta(200, {"status_code": "IN_PROGRESS"}) for _ in range(60)]
    _preparar(monkeypatch, respostas)
    with pytest.raises(ErroRede, match="processamento"):
        Instagram(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "")


def test_erro_190_pede_reconexao(monkeypatch, video):
    _preparar(monkeypatch, [erro_http(400, {"error": {"message": "token expirado", "code": 190}})])
    with pytest.raises(ErroConexao, match="reconecte com publicar conectar instagram$"):
        Instagram(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "")


def test_renova_token_depois_de_um_dia(monkeypatch, video):
    respostas = [Resposta(200, {"access_token": "TK2", "expires_in": 5183944})] + _sequencia()
    servidor, cofre = _preparar(monkeypatch, respostas, renovado_ha=90000)
    Instagram(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "")
    assert "refresh_access_token" in servidor.pedidos[0].full_url
    assert cofre.dados["instagram:token"] == "TK2"
    assert servidor.pedidos[2].get_header("Authorization") == "OAuth TK2"


def test_sem_token_pede_reconexao(monkeypatch, video):
    _, cofre = _preparar(monkeypatch, [])
    cofre.dados.pop("instagram:token")
    with pytest.raises(ErroConexao, match="conectar instagram$"):
        Instagram(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "")


def test_permalink_falha_mas_reels_saiu(monkeypatch, video):
    _preparar(monkeypatch, _sequencia()[:5] + [erro_http(503)])
    r = Instagram(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "")
    assert r == Resultado("publicado", "", "M1")


def test_media_publish_falha_e_incerto(monkeypatch, video):
    from esteira.publicar.http import ErroIncerto
    _preparar(monkeypatch, _sequencia()[:4] + [erro_http(503)])
    with pytest.raises(ErroIncerto):
        Instagram(esperar=lambda s: None).publicar(video, TEXTOS, DATA, "")
