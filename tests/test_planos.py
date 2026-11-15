import pytest
from PIL import Image

from esteira.midia import executar_ffmpeg, sondar
from esteira.planos import (
    Plano,
    centro_em,
    detectar_cortes,
    dividir_em_segmentos,
    gerar_folha,
    gravar_planos,
    ler_planos,
    marcas_do_plano,
    paineis,
    planos_iniciais,
    recorte,
    recorte_no_tempo,
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


def test_folha_com_rotulos(tmp_path):
    video = video_com_corte(tmp_path)
    saida = gerar_folha(
        video, [Plano(0, 2), Plano(2, 4, x=0.7, zoom=1.35)], tmp_path / "folha.jpg",
        rotulos=["1 Arthur · bom dia a todos", "2 P2 · obrigado pelo convite"],
        caixas=[None, (0.7, 0.4, 0.1, 0.2)],
    )
    with Image.open(saida) as imagem:
        assert imagem.format == "JPEG" and imagem.width > 0


def test_limites_de_cena_cobrem_o_trecho(monkeypatch):
    from esteira import planos

    monkeypatch.setattr(planos, "detectar_cortes", lambda video, inicio, fim: [0.6, 2.0, 3.4])
    assert planos.limites_de_cena("v.mp4", 0.5, 3.5) == [0.5, 2.0, 3.5]


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
    assert m.duracao == pytest.approx(4, abs=0.2)


# Acompanhamento suave e tela dividida (docs/enquadramento.md)

DIVISAO = [{"pessoa": "P1", "x": 0.3, "y": 0.45, "zoom": 1.35}, {"pessoa": "P2", "x": 0.7, "y": 0.42, "zoom": 1.7}]


def test_arquivo_de_sempre_nao_muda(tmp_path):
    gravar_planos(tmp_path, [Plano(1, 2, x=0.3, y=0.45, zoom=1.8)])
    texto = (tmp_path / "enquadramento.json").read_text("utf-8")
    assert "trajeto" not in texto and "divisao" not in texto
    assert texto == (
        '{\n  "planos": [\n    {\n      "inicio": 1,\n      "fim": 2,\n'
        '      "x": 0.3,\n      "y": 0.45,\n      "zoom": 1.8\n    }\n  ]\n}'
    )


def test_grava_e_le_trajeto_e_divisao(tmp_path):
    planos = [Plano(0, 4, 0.3, 0.4, 1.35, trajeto=[[0, 0.3, 0.4], [4, 0.35, 0.4]]), Plano(4, 9, divisao=DIVISAO)]
    gravar_planos(tmp_path, planos)
    assert ler_planos(tmp_path) == planos


def test_arquivo_antigo_continua_valendo(tmp_path):
    antigo = '{"planos": [{"inicio": 0, "fim": 3, "x": 0.2, "y": 0.5, "zoom": 2.0}]}'
    (tmp_path / "enquadramento.json").write_text(antigo, "utf-8")
    assert ler_planos(tmp_path) == [Plano(0, 3, 0.2, 0.5, 2.0)]


def test_centro_em_segue_o_trajeto():
    plano = Plano(10, 20, x=0.5, trajeto=[[10, 0.3, 0.4], [12, 0.5, 0.5], [20, 0.5, 0.5]])
    assert centro_em(plano, 9) == (0.3, 0.4)
    assert centro_em(plano, 11) == pytest.approx((0.4, 0.45))
    assert centro_em(plano, 30) == (0.5, 0.5)
    assert centro_em(Plano(0, 1, x=0.7, y=0.3), 0.5) == (0.7, 0.3)


def test_paineis():
    cima, baixo = paineis(Plano(4, 9, divisao=DIVISAO))
    assert (cima.inicio, cima.fim, cima.x, cima.zoom, baixo.x, baixo.zoom) == (4, 9, 0.3, 1.35, 0.7, 1.7)
    with pytest.raises(ValueError, match="divisao"):
        paineis(Plano(4, 9, divisao=DIVISAO[:1]))
    with pytest.raises(ValueError, match="x, y e zoom"):
        paineis(Plano(4, 9, divisao=[DIVISAO[0], {"x": 0.5}]))
    with pytest.raises(ValueError, match="zoom"):
        paineis(Plano(4, 9, divisao=[DIVISAO[0], {**DIVISAO[1], "zoom": 3}]))


@pytest.mark.parametrize("trajeto", [[[0, 0.3]], [[0, 0.3, "a"]], [[2, 0.3, 0.4], [1, 0.3, 0.4]], "x", []])
def test_trajeto_editado_errado_vira_erro_claro(trajeto):
    plano = Plano(0, 4, x=0.3, zoom=1.35, trajeto=trajeto)
    if trajeto == []:  # vazio é o mesmo que sem trajeto
        assert recorte_no_tempo(plano, 1920, 1080, 0, 4) == recorte(plano, 1920, 1080)
        return
    with pytest.raises(ValueError, match="trajeto"):
        recorte_no_tempo(plano, 1920, 1080, 0, 4)


def test_recorte_no_tempo_sem_trajeto_e_o_de_sempre():
    plano = Plano(0, 10, x=0.25, y=0.4, zoom=2)
    assert recorte_no_tempo(plano, 1920, 1080, 2, 5) == recorte(plano, 1920, 1080)


def _avaliar(expressao, t):
    """Avalia em Python a expressão do crop (só usa números, t, clip, +, -, *, /)."""
    if isinstance(expressao, int):
        return expressao
    texto = expressao.strip("'")
    assert set(texto) <= set("0123456789.+-*/(),tclip")
    return eval(texto, {"clip": lambda v, a, b: min(max(v, a), b), "t": t})


def test_recorte_no_tempo_interpola_em_pixels():
    plano = Plano(10, 20, x=0.3, zoom=2, trajeto=[[10, 0.3, 0.5], [14, 0.5, 0.5], [20, 0.5, 0.5]])
    w, h, x, y = recorte_no_tempo(plano, 1920, 1080, 12, 18)
    assert (w, h) == recorte(plano, 1920, 1080)[:2]
    assert y == recorte(plano, 1920, 1080)[3]  # y parado: número, sem expressão
    assert x.startswith("'") and "if(" not in x
    for t_trecho, centro in [(0, 0.4), (1, 0.45), (2, 0.5), (5, 0.5), (-1, 0.4), (9, 0.5)]:
        esperado = round(1920 * centro - w / 2)
        assert _avaliar(x, t_trecho) == pytest.approx(esperado, abs=1)


def test_recorte_no_tempo_fica_dentro_do_quadro():
    plano = Plano(0, 4, zoom=2, trajeto=[[0, 0.0, 0.0], [4, 1.0, 1.0]])
    w, h, x, y = recorte_no_tempo(plano, 1920, 1080, 0, 4)
    for t in (0, 1, 2, 3, 4):
        assert 0 <= _avaliar(x, t) <= 1920 - w and 0 <= _avaliar(y, t) <= 1080 - h


def test_expressao_descendo():
    plano = Plano(0, 2, zoom=2, trajeto=[[0, 0.6, 0.5], [2, 0.4, 0.5]])
    w, _, x, _ = recorte_no_tempo(plano, 1920, 1080, 0, 2)
    assert "-" in x.strip("'")[1:]
    assert _avaliar(x, 2) == round(1920 * 0.4 - w / 2)


def test_marcas_do_plano():
    assert marcas_do_plano(Plano(0, 4, x=0.3, zoom=1.35), 400, 225) == ("", [])
    etiqueta, marcas = marcas_do_plano(Plano(0, 4, 0.3, 0.4, 1.35, trajeto=[[0, 0.3, 0.4], [4, 0.5, 0.4]]), 400, 225)
    assert etiqueta == "SUAVE"
    assert [m[0] for m in marcas] == ["retangulo", "linha"]
    x0, _, x1, _ = marcas[0][1]
    assert (x0 + x1) / 2 == pytest.approx(400 * 0.4, abs=2)  # recorte no meio do plano (t = 2)
    assert marcas[1][1] == [(120.0, 90.0), (200.0, 90.0)]
    etiqueta, marcas = marcas_do_plano(Plano(4, 9, divisao=DIVISAO), 400, 225)
    assert etiqueta == "DIVIDIDA" and [m[0] for m in marcas] == ["retangulo", "retangulo"]
    assert marcas[0][2] != marcas[1][2]
    com_trajeto = [DIVISAO[0], {**DIVISAO[1], "trajeto": [[4, 0.7, 0.42], [9, 0.6, 0.42]]}]
    assert marcas_do_plano(Plano(4, 9, divisao=com_trajeto), 400, 225)[0] == "DIVIDIDA SUAVE"


def test_folha_com_planos_suave_e_dividido(tmp_path):
    video = video_com_corte(tmp_path)
    planos = [Plano(0, 2, 0.3, 0.4, 1.35, trajeto=[[0, 0.3, 0.4], [2, 0.6, 0.4]]), Plano(2, 4, divisao=DIVISAO)]
    saida = gerar_folha(video, planos, tmp_path / "folha.jpg", rotulos=["1 Arthur", "2 Arthur + P2"])
    with Image.open(saida) as imagem:
        imagem = imagem.convert("RGB")
        ciano = [imagem.getpixel((x, 225 * 0.4)) for x in range(130, 230)]
        assert any(g > 180 and b > 180 and r < 90 for r, g, b in ciano)  # o trajeto desenhado
