from datetime import datetime
from urllib.parse import quote

from fastapi.testclient import TestClient

from esteira.cortar import IMAGENS_SUGERIDAS, VIDEO_FINAL, pasta_do_corte
from esteira.modelos import Corte
from esteira.painel.app import criar_app
from tests.auxiliares_painel import criar_episodio

NOME = "Entre Assuntos 03 - Arthur Cerqueira (teste capcut)"
AGORA = datetime(2026, 11, 7, 10)


def _cliente(tmp_path) -> TestClient:
    return TestClient(criar_app(tmp_path / "cortes", agora=lambda: AGORA))


def _ep(tmp_path, cortes, montados, **kwargs):
    (tmp_path / "cortes").mkdir(exist_ok=True)
    return criar_episodio(tmp_path / "cortes", NOME, cortes, montados, **kwargs)


def _url(sufixo: str = "") -> str:
    return "/api/episodios/" + quote(NOME) + sufixo


def test_lista_episodios(tmp_path):
    _ep(tmp_path, [Corte(1, "Um", 10, 20, "tenso")], {1})
    resposta = _cliente(tmp_path).get("/api/episodios")
    assert resposta.status_code == 200
    dados = resposta.json()
    assert [e["nome"] for e in dados] == [NOME]
    assert dados[0]["total"] == 1


def test_lista_sem_pasta_de_cortes(tmp_path):
    assert _cliente(tmp_path).get("/api/episodios").json() == []


def test_episodio_nome_com_acento_na_url(tmp_path):
    _ep(tmp_path, [Corte(1, "Um", 10, 20, "tenso")], {1})
    resposta = _cliente(tmp_path).get(_url())
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["resumo"]["nome"] == NOME
    assert dados["cortes"][0]["numero"] == 1 and dados["cortes"][0]["selo"] == "sem vídeo final"


def test_episodio_caminho_malicioso(tmp_path):
    _ep(tmp_path, [Corte(1, "Um", 10, 20, "tenso")], {1})
    resposta = _cliente(tmp_path).get("/api/episodios/..%2FAutomacao")
    assert resposta.status_code in (403, 404)
    assert "detail" in resposta.json()


def test_episodio_inexistente_404(tmp_path):
    (tmp_path / "cortes").mkdir()
    resposta = _cliente(tmp_path).get("/api/episodios/nao-existe")
    assert resposta.status_code == 404 and resposta.json()["detail"]


def test_corte_nao_montado_abre(tmp_path):
    _ep(tmp_path, [Corte(1, "Um", 10, 20, "tenso")], set())
    resposta = _cliente(tmp_path).get(_url("/cortes/1"))
    assert resposta.status_code == 200
    assert resposta.json()["bloco"]["selo"] == "erro"
    assert resposta.json()["guia"] is None and resposta.json()["imagens"] == []


def test_corte_inexistente_404(tmp_path):
    _ep(tmp_path, [Corte(1, "Um", 10, 20, "tenso")], {1})
    assert _cliente(tmp_path).get(_url("/cortes/9")).status_code == 404


def test_corte_guia_e_imagens(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = _ep(tmp_path, [a], {1})
    imagens = pasta_do_corte(pasta, a) / IMAGENS_SUGERIDAS
    imagens.mkdir()
    (imagens / "guia.md").write_text("# Guia ação", "utf-8")
    (imagens / "b.PNG").write_bytes(b"x")
    (imagens / "a.jpg").write_bytes(b"x")
    (imagens / "c.txt").write_bytes(b"x")
    dados = _cliente(tmp_path).get(_url("/cortes/1")).json()
    assert dados["guia"] == "# Guia ação"
    assert dados["imagens"] == ["a.jpg", "b.PNG"]
    assert dados["bloco"]["tem_guia"] is True


def test_video_com_range(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = _ep(tmp_path, [a], {1})
    (pasta_do_corte(pasta, a) / "corte.mp4").write_bytes(bytes(range(100)) * 10)
    resposta = _cliente(tmp_path).get(_url("/cortes/1/video"), headers={"Range": "bytes=0-99"})
    assert resposta.status_code == 206
    assert len(resposta.content) == 100
    assert resposta.headers["content-type"] == "video/mp4"


def test_video_inexistente_404(tmp_path):
    _ep(tmp_path, [Corte(1, "Um", 10, 20, "tenso")], set())
    assert _cliente(tmp_path).get(_url("/cortes/1/video")).status_code == 404


def test_video_final_mov_maiusculo(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = _ep(tmp_path, [a], {1})
    final = pasta_do_corte(pasta, a) / VIDEO_FINAL
    final.mkdir()
    (final / "a.mp4").write_bytes(b"1")
    (final / "b.MOV").write_bytes(b"22")
    cliente = _cliente(tmp_path)
    resposta = cliente.get(_url("/cortes/1/video-final/b.MOV"))
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "video/quicktime"
    assert cliente.get(_url("/cortes/1/video-final/a.mp4")).headers["content-type"] == "video/mp4"


def test_video_final_extensao_proibida(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = _ep(tmp_path, [a], {1})
    final = pasta_do_corte(pasta, a) / VIDEO_FINAL
    final.mkdir()
    (final / "x.txt").write_text("x", "utf-8")
    assert _cliente(tmp_path).get(_url("/cortes/1/video-final/x.txt")).status_code == 403


def test_imagem_extensao_proibida(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = _ep(tmp_path, [a], {1})
    imagens = pasta_do_corte(pasta, a) / IMAGENS_SUGERIDAS
    imagens.mkdir()
    (imagens / "guia.md").write_text("x", "utf-8")
    (imagens / "f.jpeg").write_bytes(b"x")
    cliente = _cliente(tmp_path)
    assert cliente.get(_url("/cortes/1/imagens/guia.md")).status_code == 403
    assert cliente.get(_url("/cortes/1/imagens/f.jpeg")).status_code == 200


def test_imagem_caminho_malicioso(tmp_path):
    _ep(tmp_path, [Corte(1, "Um", 10, 20, "tenso")], {1})
    resposta = _cliente(tmp_path).get(_url("/cortes/1/imagens/..%2Fcorte.mp4"))
    assert resposta.status_code in (403, 404)


def test_calendario_ordenado(tmp_path):
    cortes = [
        Corte(1, "Um", 10, 20, "tenso", data="2026-11-09 18:00"),
        Corte(2, "Dois", 30, 40, "leve"),
        Corte(3, "Três", 50, 60, "leve", instagram=True, data="2026-11-08 12:00"),
    ]
    pasta = _ep(tmp_path, cortes, {1, 2, 3})
    (pasta / "calendario.md").write_text("# Calendário\nconteúdo", "utf-8")
    dados = _cliente(tmp_path).get(_url("/calendario")).json()
    assert [i["numero"] for i in dados["itens"]] == [3, 1, 2]
    assert dados["itens"][0] == {
        "numero": 3, "titulo": "Três", "data": "2026-11-08 12:00",
        "redes": ["youtube", "tiktok", "instagram"],
    }
    assert dados["texto"] == "# Calendário\nconteúdo"


def test_calendario_sem_arquivo(tmp_path):
    _ep(tmp_path, [Corte(1, "Um", 10, 20, "tenso")], {1})
    assert _cliente(tmp_path).get(_url("/calendario")).json()["texto"] == ""


def test_descartados(tmp_path):
    pasta = _ep(tmp_path, [Corte(1, "Um", 10, 20, "tenso")], {1})
    cliente = _cliente(tmp_path)
    assert cliente.get(_url("/descartados")).json() == {"texto": ""}
    (pasta / "descartados.md").write_text("fora", "utf-8")
    assert cliente.get(_url("/descartados")).json() == {"texto": "fora"}


def test_post_ilegivel_nao_da_500(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = _ep(tmp_path, [a], {1})
    (pasta_do_corte(pasta, a) / "post.md").write_bytes(b"\xff\xfe\x80\x81 invalido")
    cliente = _cliente(tmp_path)
    assert cliente.get("/api/episodios").status_code == 200
    resposta = cliente.get(_url())
    assert resposta.status_code == 200
    assert any(x.startswith("post:") for x in resposta.json()["cortes"][0]["avisos_post"])
    resposta = cliente.get(_url("/cortes/1"))
    assert resposta.status_code == 200
    assert any(x.startswith("post:") for x in resposta.json()["bloco"]["avisos_post"])


def test_aprovados_ilegivel_nao_da_500(tmp_path):
    pasta = _ep(tmp_path, [Corte(1, "Um", 10, 20, "tenso")], {1})
    (pasta / "aprovados.json").write_text("{quebrado", "utf-8")
    cliente = _cliente(tmp_path)
    assert cliente.get("/api/episodios").status_code == 200
    assert cliente.get(_url()).status_code == 200
    assert cliente.get(_url("/calendario")).status_code == 200
    assert cliente.get(_url("/cortes/1")).status_code == 404
