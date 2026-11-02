import re

import pytest
from PIL import Image

from esteira.midia import ErroMidia, executar_ffmpeg, pico_de_audio, saida_ffmpeg, sondar
from esteira.modelos import Cue
from esteira import render
from esteira.receita import Imagem, Musica, Receita
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


def test_imagem_aparece_no_tempo(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    _imagem_vermelha(pasta / "imagens" / "01.png")
    saida = pasta / "final.mp4"
    receita = Receita([(0.0, 3.0)], [], [], imagens=[Imagem(0.5, 2.5, "imagens/01.png")])
    renderizar_final(receita, origem, cartao, pasta, saida)
    durante = _quadro(saida, 1.5, pasta / "q1.png")
    assert _vermelho(durante.getpixel((540, 100)))
    assert _vermelho(durante.getpixel((540, 1800)))
    assert _vermelho(durante.getpixel((5, 960)))
    assert _vermelho(durante.getpixel((1075, 960)))
    antes = _quadro(saida, 0.2, pasta / "q0.png")
    depois = _quadro(saida, 2.8, pasta / "q2.png")
    assert not _vermelho(antes.getpixel((540, 100)))
    assert not _vermelho(depois.getpixel((540, 100)))


def test_legenda_some_durante_imagem(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    _imagem_vermelha(pasta / "imagens" / "01.png")
    saida = pasta / "final.mp4"
    receita = Receita(
        [(0.0, 3.0)], [], [Cue(0, 3, ["LEGENDA BEM LONGA"])], imagens=[Imagem(0.5, 2.5, "imagens/01.png")]
    )
    renderizar_final(receita, origem, cartao, pasta, saida)
    assert _brancos_na_legenda(_quadro(saida, 0.2, pasta / "q0.png")) > 20
    assert _brancos_na_legenda(_quadro(saida, 1.5, pasta / "q1.png")) == 0


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
    assert _nivel_da_musica(saida, 3.3, 3.9) < -60


def test_musica_longa_e_cortada(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    musica = _musica(pasta / "musica.wav", 10)
    saida = pasta / "final.mp4"
    receita = Receita([(0.0, 2.0)], [], [], musica=Musica(str(musica), -20.0))
    renderizar_final(receita, origem, cartao, pasta, saida)
    assert sondar(saida).duracao == pytest.approx(3, abs=0.2)


def test_caminhos_com_acento_em_imagem_e_musica(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    _imagem_vermelha(pasta / "imagens" / "01-ação.png")
    musica = _musica(pasta / "música ação.wav", 1)
    saida = pasta / "final.mp4"
    receita = Receita(
        [(0.0, 3.0)], [], [Cue(0, 3, ["olá"])],
        imagens=[Imagem(0.5, 2.5, "imagens/01-ação.png")], musica=Musica(str(musica), -20.0),
    )
    renderizar_final(receita, origem, cartao, pasta, saida)
    assert _vermelho(_quadro(saida, 1.5, pasta / "q.png").getpixel((540, 960)))
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
    monkeypatch.setattr(render, "pico_de_audio", lambda _: -0.06)
    alertas = renderizar_final(Receita([(0.0, 1.0)], [], []), origem, cartao, pasta, pasta / "final.mp4")
    assert "áudio perto de saturar: -0.1 dB" in alertas


def test_pico_de_audio(tmp_path):
    pasta, origem, _ = _cenario(tmp_path)
    assert -30 < pico_de_audio(origem) <= 0
