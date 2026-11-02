import pytest
from PIL import Image

from esteira.midia import executar_ffmpeg, sondar
from esteira.planos import (
    Plano,
    detectar_cortes,
    dividir_em_segmentos,
    gerar_folha,
    gravar_planos,
    ler_planos,
    planos_iniciais,
    recorte,
)
from esteira.receita import Receita
from esteira.render import filtro_9x16, renderizar_final
from tests.auxiliares import gerar_video_teste


def video_com_corte(tmp_path):
    saida = tmp_path / "dois.mp4"
    executar_ffmpeg([
        "-y", "-f", "lavfi", "-i", "color=c=red:s=1920x1080:r=30:d=2",
        "-f", "lavfi", "-i", "color=c=blue:s=1920x1080:r=30:d=2",
        "-f", "lavfi", "-i", "sine=duration=4",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-map", "2:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(saida),
    ])
    return saida


def test_recorte_sem_zoom_usa_altura_inteira():
    largura, altura, x, y = recorte(Plano(0, 1), 1920, 1080)
    assert altura == 1080 and largura == pytest.approx(1126, abs=2)
    assert x == pytest.approx(397, abs=2) and y == 0


def test_recorte_com_zoom_centraliza_no_ponto():
    largura, altura, x, y = recorte(Plano(0, 1, x=0.25, y=0.4, zoom=2), 1920, 1080)
    assert altura == 540 and largura == pytest.approx(562, abs=2)
    assert x + largura / 2 == pytest.approx(480, abs=2)
    assert y + altura / 2 == pytest.approx(432, abs=2)


def test_recorte_nao_sai_da_imagem():
    largura, altura, x, y = recorte(Plano(0, 1, x=1, y=1, zoom=2), 1920, 1080)
    assert x + largura <= 1920 and y + altura <= 1080


def test_recorte_e_par():
    largura, altura, _, _ = recorte(Plano(0, 1, zoom=1.37), 1920, 1080)
    assert largura % 2 == 0 and altura % 2 == 0


def test_divide_faixas_nas_trocas_de_plano():
    planos = [Plano(0, 5, x=0.2), Plano(5, 10, x=0.8)]
    segmentos = dividir_em_segmentos([(1.0, 3.0), (4.0, 7.0)], planos)
    assert [(a, b, p.x) for a, b, p in segmentos] == [
        (1.0, 3.0, 0.2), (4.0, 5.0, 0.2), (5.0, 7.0, 0.8),
    ]


def test_tempo_sem_plano_usa_centro():
    segmentos = dividir_em_segmentos([(1.0, 3.0)], [Plano(2, 3, x=0.9)])
    assert [(a, b, p.x) for a, b, p in segmentos] == [(1.0, 2.0, 0.5), (2.0, 3.0, 0.9)]


def test_grava_e_le_planos(tmp_path):
    gravar_planos(tmp_path, [Plano(1, 2, x=0.3, y=0.45, zoom=1.8)])
    assert ler_planos(tmp_path) == [Plano(1, 2, x=0.3, y=0.45, zoom=1.8)]


def test_sem_arquivo_nao_ha_planos(tmp_path):
    assert ler_planos(tmp_path) == []


def test_detecta_troca_de_camera(tmp_path):
    cortes = detectar_cortes(video_com_corte(tmp_path), 0, 4)
    assert len(cortes) == 1 and cortes[0] == pytest.approx(2, abs=0.1)


def test_planos_iniciais_cobrem_o_trecho(tmp_path):
    planos = planos_iniciais(video_com_corte(tmp_path), 0.5, 3.5)
    assert [p.inicio for p in planos][0] == 0.5 and planos[-1].fim == 3.5
    assert len(planos) == 2


def test_folha_mostra_um_quadro_por_plano(tmp_path):
    video = video_com_corte(tmp_path)
    saida = gerar_folha(video, [Plano(0, 2), Plano(2, 4)], tmp_path / "folha.jpg")
    assert Image.open(saida).width > 0


def test_filtro_usa_recorte_e_faixa():
    f = filtro_9x16("in", "out", (562, 540, 100, 50))
    assert "crop=562:540:100:50" in f
    assert "overlay=0:442" in f and "scale=1080:1036" in f and "gblur=sigma=40" in f


def test_render_aplica_planos_diferentes(tmp_path):
    origem = gerar_video_teste(tmp_path / "o.mp4", 4)
    cartao = gerar_video_teste(tmp_path / "f.mp4", 1, 1080, 1920)
    saida = tmp_path / "s.mp4"
    planos = [Plano(0, 2, x=0.2, zoom=2), Plano(2, 4, x=0.8, zoom=1.5)]
    renderizar_final(Receita([(0.0, 3.0)], planos, []), origem, cartao, tmp_path, saida)
    m = sondar(saida)
    assert (m.largura, m.altura) == (1080, 1920)
    assert m.duracao == pytest.approx(3.5, abs=0.2)
