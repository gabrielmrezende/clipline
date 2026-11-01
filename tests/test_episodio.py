import json

import pytest

from esteira.episodio import criar_episodio, slug
from esteira.midia import ErroMidia, sondar
from tests.auxiliares import gerar_video_teste


def test_sonda_video(tmp_path):
    m = sondar(gerar_video_teste(tmp_path / "a.mp4", 2))
    assert (m.largura, m.altura, m.tem_audio) == (1920, 1080, True)
    assert m.duracao == pytest.approx(2, abs=0.2)


def test_rejeita_video_vertical(tmp_path):
    v = gerar_video_teste(tmp_path / "v.mp4", 1, 1080, 1920)
    with pytest.raises(ErroMidia, match="horizontal"):
        criar_episodio(v, "Entre Assuntos", 3, "Arthur", tmp_path)


def test_rejeita_sem_audio(tmp_path):
    v = gerar_video_teste(tmp_path / "s.mp4", 1, audio=False)
    with pytest.raises(ErroMidia, match="áudio"):
        criar_episodio(v, "Entre Assuntos", 3, "Arthur", tmp_path)


def test_cria_pasta_e_json(tmp_path):
    v = gerar_video_teste(tmp_path / "e.mp4", 1)
    p = criar_episodio(v, "Entre Assuntos", 3, "Arthur Cerqueira", tmp_path)
    assert p.name == "Entre Assuntos 03 - Arthur Cerqueira"
    assert json.loads((p / "episodio.json").read_text("utf-8"))["convidado"] == "Arthur Cerqueira"


def test_recusa_outro_video_na_mesma_pasta(tmp_path):
    a = gerar_video_teste(tmp_path / "a.mp4", 1)
    b = gerar_video_teste(tmp_path / "b.mp4", 1)
    criar_episodio(a, "Entre Assuntos", 3, "Arthur", tmp_path)
    with pytest.raises(ErroMidia, match="outro vídeo"):
        criar_episodio(b, "Entre Assuntos", 3, "Arthur", tmp_path)


def test_slug():
    assert slug("Como é o A-29?") == "como-e-o-a-29"
