import re

import pytest
from PIL import Image

from esteira.midia import ErroMidia, executar_ffmpeg, pico_de_audio, saida_ffmpeg, sondar
from esteira.modelos import Cue
from esteira import render
from esteira.receita import Musica, Receita
from esteira.render import renderizar_final
from tests.auxiliares import gerar_video_teste


def _cenario(tmp_path):
    pasta = tmp_path / "Tudo é Política (teste)"
    pasta.mkdir()
    return pasta, gerar_video_teste(pasta / "origem.mp4", 4), gerar_video_teste(pasta / "fim.mp4", 1, 1080, 1920)


def _quadro(video, segundo, destino):
    executar_ffmpeg(["-y", "-ss", f"{segundo}", "-i", str(video), "-frames:v", "1", str(destino)])
    return Image.open(destino).convert("RGB")


def _vermelho(pixel):
    r, g, b = pixel
    return r > 200 and g < 70 and b < 70


def _brancos_na_legenda(quadro):
    return sum(
        1 for x in range(200, 880, 4) for y in range(1530, 1640, 4) if min(quadro.getpixel((x, y))) > 235
    )


def _imagem_vermelha(caminho):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 600), (255, 0, 0)).save(caminho)
    return caminho


def _musica(caminho, segundos):
    executar_ffmpeg(["-y", "-f", "lavfi", "-i", f"sine=frequency=3000:duration={segundos}", str(caminho)])
    return caminho


def _nivel_da_musica(video, de, ate):
    log = saida_ffmpeg(
        ["-ss", f"{de}", "-t", f"{ate - de}", "-i", str(video), "-vn",
         "-af", "highpass=f=2000,highpass=f=2000,highpass=f=2000,volumedetect", "-f", "null", "-"]
    )
    return float(re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", log).group(1))


def test_final_sem_imagem_nem_musica(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    saida = pasta / "final.mp4"
    receita = Receita([(0.0, 1.0), (2.0, 3.0)], [], [Cue(0, 1, ["olá Brasil"])])
    alertas = renderizar_final(receita, origem, cartao, pasta, saida)
    m = sondar(saida)
    assert (m.largura, m.altura) == (1080, 1920)
    assert m.duracao == pytest.approx(3, abs=0.2)
    assert m.tem_audio
    assert "sem música" in alertas


def test_final_sem_encerramento(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    saida = pasta / "final.mp4"
    receita = Receita([(0.0, 2.0)], [], [], encerramento=False)
    renderizar_final(receita, origem, cartao, pasta, saida)
    assert sondar(saida).duracao == pytest.approx(2, abs=0.2)


def _azul(pixel):
    r, g, b = pixel
    return b > 200 and r < 70 and g < 70


def test_legenda_aparece_o_corte_inteiro(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    saida = pasta / "corte.mp4"
    receita = Receita([(0.0, 3.0)], [], [Cue(0, 3, ["LEGENDA BEM LONGA"])])
    renderizar_final(receita, origem, cartao, pasta, saida)
    assert _brancos_na_legenda(_quadro(saida, 0.2, pasta / "q0.png")) > 20
    assert _brancos_na_legenda(_quadro(saida, 1.5, pasta / "q1.png")) > 20


def test_musica_curta_repete_e_duracao_mantem(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    musica = _musica(pasta / "musica.wav", 1)
    saida = pasta / "final.mp4"
    receita = Receita([(0.0, 3.0)], [], [], musica=Musica(str(musica), -20.0))
    alertas = renderizar_final(receita, origem, cartao, pasta, saida)
    m = sondar(saida)
    assert m.duracao == pytest.approx(4, abs=0.2)
    assert m.tem_audio
    assert "sem música" not in alertas
    assert _nivel_da_musica(saida, 1.6, 2.4) > -60
    assert _nivel_da_musica(saida, 3.1, 3.4) < -60


def test_musica_longa_e_cortada(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    musica = _musica(pasta / "musica.wav", 10)
    saida = pasta / "final.mp4"
    receita = Receita([(0.0, 2.0)], [], [], musica=Musica(str(musica), -20.0))
    renderizar_final(receita, origem, cartao, pasta, saida)
    assert sondar(saida).duracao == pytest.approx(3, abs=0.2)


def test_caminhos_com_acento_em_musica(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    musica = _musica(pasta / "música ação.wav", 1)
    saida = pasta / "final.mp4"
    receita = Receita(
        [(0.0, 3.0)], [], [Cue(0, 3, ["olá"])],
        musica=Musica(str(musica), -20.0),
    )
    renderizar_final(receita, origem, cartao, pasta, saida)
    assert sondar(saida).duracao == pytest.approx(4, abs=0.2)


def test_final_com_sobreposicao_no_encerramento(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    logo = pasta / "logo.png"
    Image.new("RGBA", (1080, 1920), (255, 0, 0, 255)).save(logo)
    saida = pasta / "final.mp4"
    receita = Receita([(0.0, 1.0)], [], [])
    renderizar_final(receita, origem, cartao, pasta, saida, sobreposicao=logo)
    quadro = pasta / "q.png"
    executar_ffmpeg(["-y", "-sseof", "-0.2", "-i", str(saida), "-frames:v", "1", str(quadro)])
    assert Image.open(quadro).convert("RGB").getpixel((540, 960))[0] > 200


def test_falha_nao_deixa_final(tmp_path):
    pasta, _, cartao = _cenario(tmp_path)
    saida = pasta / "final.mp4"
    with pytest.raises(ErroMidia):
        renderizar_final(Receita([(0.0, 1.0)], [], []), pasta / "nao.mp4", cartao, pasta, saida)
    assert not saida.exists()
    assert not list(pasta.glob("*.tmp.mp4"))
    assert not (pasta / ".legenda_tmp").exists()


def test_alerta_de_audio_perto_de_saturar(tmp_path, monkeypatch):
    pasta, origem, cartao = _cenario(tmp_path)
    monkeypatch.setattr(render, "pico_de_audio", lambda *_: -0.06)
    alertas = renderizar_final(Receita([(0.0, 1.0)], [], []), origem, cartao, pasta, pasta / "final.mp4")
    assert "áudio perto de saturar: -0.1 dB" in alertas


def test_falha_na_medicao_do_pico_nao_deixa_final(tmp_path, monkeypatch):
    pasta, origem, cartao = _cenario(tmp_path)

    def falhar(*args):
        raise ErroMidia("não mediu")

    monkeypatch.setattr(render, "pico_de_audio", falhar)
    saida = pasta / "final.mp4"
    with pytest.raises(ErroMidia):
        renderizar_final(Receita([(0.0, 1.0)], [], []), origem, cartao, pasta, saida)
    assert not saida.exists()
    assert not list(pasta.glob("*.tmp.mp4"))


def test_pico_e_medido_so_na_parte_principal(tmp_path, monkeypatch):
    pasta, origem, cartao = _cenario(tmp_path)
    medidas = []
    monkeypatch.setattr(render, "pico_de_audio", lambda arquivo, duracao=None: medidas.append((arquivo, duracao)) or -9)
    renderizar_final(Receita([(0.0, 1.0)], [], []), origem, cartao, pasta, pasta / "final.mp4")
    assert [(a.name, d) for a, d in medidas] == [("final.tmp.mp4", 1.0)]


def test_pico_de_audio(tmp_path):
    pasta, origem, _ = _cenario(tmp_path)
    assert -30 < pico_de_audio(origem) <= 0


def _cor_solida(caminho, cor, largura, altura, segundos, audio=True):
    args = ["-y", "-f", "lavfi", "-i", f"color=c={cor}:s={largura}x{altura}:r=30:d={segundos}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}", "-c:a", "aac"]
    executar_ffmpeg(args + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(caminho)])
    return caminho


def test_transicao_suave_para_o_encerramento(tmp_path):
    pasta = tmp_path / "Tudo é Política (teste)"
    pasta.mkdir()
    origem = _cor_solida(pasta / "origem.mp4", "blue", 1920, 1080, 3)
    cartao = _cor_solida(pasta / "fim.mp4", "red", 1080, 1920, 1.5)
    saida = pasta / "final.mp4"
    renderizar_final(Receita([(0.0, 2.0)], [], []), origem, cartao, pasta, saida)
    assert sondar(saida).duracao == pytest.approx(3.5, abs=0.2)
    assert _azul(_quadro(saida, 1.9, pasta / "antes.png").getpixel((540, 960)))
    r, _, b = _quadro(saida, 2.25, pasta / "meio.png").getpixel((540, 960))
    assert 50 < r < 210 and 50 < b < 210
    assert _vermelho(_quadro(saida, 2.7, pasta / "depois.png").getpixel((540, 960)))


def test_fala_termina_antes_da_transicao(tmp_path):
    pasta = tmp_path / "Tudo é Política (teste)"
    pasta.mkdir()
    origem = _cor_solida(pasta / "origem.mp4", "blue", 1920, 1080, 3)
    cartao = _cor_solida(pasta / "fim.mp4", "red", 1080, 1920, 1.5, audio=False)
    saida = pasta / "final.mp4"
    renderizar_final(Receita([(0.0, 2.0)], [], []), origem, cartao, pasta, saida)
    def volume(inicio):
        log = saida_ffmpeg(["-ss", str(inicio), "-t", "0.15", "-i", str(saida), "-af", "volumedetect", "-f", "null", "-"])
        return float(re.search(r"mean_volume: (-?[\d.]+) dB", log).group(1))

    assert volume(1.83) > volume(1.0) - 1.5


FAIXAS_PREVIA = [(100.0, 110.0), (200.0, 220.0)]


def test_trechos_inicio_no_meio_de_uma_faixa():
    assert render.trechos_da_previa(FAIXAS_PREVIA, 5, 15) == [(105, 110), (200, 210)]


def test_trechos_perto_do_fim():
    assert render.trechos_da_previa(FAIXAS_PREVIA, 25, 15) == [(215, 220)]


def test_trechos_alem_do_fim_recomeca():
    assert render.trechos_da_previa(FAIXAS_PREVIA, 40, 15) == [(100, 110), (200, 205)]


def _receita_previa():
    return Receita(faixas=FAIXAS_PREVIA, planos=[], legenda=[])


def test_gerar_previa_monta_comando(tmp_path):
    chamadas = []

    def falso(args, cwd=None, **kwargs):
        chamadas.append((args, kwargs))

    saida = tmp_path / "previa-musica.m4a"
    resultado = render.gerar_previa(
        _receita_previa(), tmp_path / "ep.mp4", Musica(arquivo=str(tmp_path / "m.mp3"), volume_db=-22),
        5, saida, executar=falso,
    )
    assert resultado == saida
    args, kwargs = chamadas[0]
    filtro = args[args.index("-filter_complex") + 1]
    assert "sidechaincompress" in filtro
    assert "volume=-22.0dB" in filtro
    assert "[aprin]" in filtro and "concat=n=2:v=0:a=1[aprin]" in filtro
    assert "-vn" in args
    assert args[-1].endswith("previa-musica.m4a")
    assert kwargs.get("timeout") == 60


def test_gerar_previa_erro_do_ffmpeg(tmp_path):
    def falso(args, cwd=None, **kwargs):
        raise ErroMidia("ffmpeg falhou: x")

    with pytest.raises(ErroMidia, match="ffmpeg falhou"):
        render.gerar_previa(
            _receita_previa(), tmp_path / "ep.mp4", Musica(arquivo="m.mp3"), 0, tmp_path / "p.m4a", executar=falso
        )


def _entrada_da_musica(args):
    i = args.index("-stream_loop")
    return args[i: args.index("-i", i) + 2]


@pytest.mark.parametrize(
    ("inicio", "duracao_musica", "esperado"),
    [(5, 120.0, "5.000"), (25, 20.0, "5.000"), (40, 120.0, "0.000"), (12.5, None, "12.500")],
)
def test_previa_musica_comeca_no_mesmo_ponto_do_corte(tmp_path, inicio, duracao_musica, esperado):
    chamadas = []
    musica = Musica(arquivo=str(tmp_path / "m.mp3"), volume_db=-22)
    render.gerar_previa(
        _receita_previa(), tmp_path / "ep.mp4", musica, inicio, tmp_path / "p.m4a",
        duracao_musica=duracao_musica, executar=lambda args, cwd=None, **kw: chamadas.append(args),
    )
    args = chamadas[0]
    assert _entrada_da_musica(args) == ["-stream_loop", "-1", "-ss", esperado, "-i", str((tmp_path / "m.mp3").resolve())]
    filtro = args[args.index("-filter_complex") + 1]
    duracao = sum(b - a for a, b in render.trechos_da_previa(FAIXAS_PREVIA, inicio, 15.0))
    assert ";".join(render._filtro_musica(1, musica, duracao)) in filtro  # mesmo filtro do corte, com os fades
