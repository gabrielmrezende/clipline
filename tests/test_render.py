import re

import pytest
from PIL import Image

from esteira.midia import ErroMidia, executar_ffmpeg, pico_de_audio, saida_ffmpeg, sondar
from esteira.modelos import Cue
from esteira import render
from esteira.receita import ImagemNoVideo, Musica, Receita
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


IMAGEM = "imagens-sugeridas/0000-placa-1.jpg"


def _salvar(caminho, imagem):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    imagem.save(caminho)
    return caminho


def _faixas_verticais(caminho, largura, altura):
    imagem = Image.new("RGB", (largura, altura), (0, 255, 0))
    imagem.paste((255, 0, 0), (0, 0, largura // 3, altura))
    imagem.paste((0, 0, 255), (largura - largura // 3, 0, largura, altura))
    return _salvar(caminho, imagem)


def _verde(pixel):
    r, g, b = pixel
    return g > 200 and r < 70 and b < 70


def test_imagem_aparece_no_tempo(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    _salvar(pasta / IMAGEM, Image.new("RGB", (1080, 1920), (255, 0, 0)))
    saida = pasta / "final.mp4"
    renderizar_final(Receita([(0.0, 3.0)], [], []), origem, cartao, pasta, saida, imagens=[ImagemNoVideo(0.5, 2.5, IMAGEM)])
    durante = _quadro(saida, 1.5, pasta / "q1.png")
    for ponto in ((540, 100), (540, 1800), (5, 960), (1075, 960)):
        assert _vermelho(durante.getpixel(ponto))
    assert not _vermelho(_quadro(saida, 0.2, pasta / "q0.png").getpixel((540, 100)))
    assert not _vermelho(_quadro(saida, 2.8, pasta / "q2.png").getpixel((540, 100)))


def test_imagem_vertical_preparada_fica_em_tela_cheia(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    _faixas_verticais(pasta / IMAGEM, 1080, 1920)
    saida = pasta / "final.mp4"
    renderizar_final(Receita([(0.0, 3.0)], [], []), origem, cartao, pasta, saida, imagens=[ImagemNoVideo(0.5, 2.5, IMAGEM)])
    durante = _quadro(saida, 1.5, pasta / "q.png")
    assert _vermelho(durante.getpixel((150, 100)))
    assert _azul(durante.getpixel((930, 1800)))


def test_imagem_de_outro_tamanho_cobre_a_tela_sem_distorcer(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    _faixas_verticais(pasta / IMAGEM, 1800, 900)
    saida = pasta / "final.mp4"
    renderizar_final(Receita([(0.0, 3.0)], [], []), origem, cartao, pasta, saida, imagens=[ImagemNoVideo(0.5, 2.5, IMAGEM)])
    durante = _quadro(saida, 1.5, pasta / "q.png")
    assert _verde(durante.getpixel((150, 960)))  # esticada, a faixa vermelha estaria aqui
    assert _verde(durante.getpixel((930, 960)))


def _quadrado_no_centro(caminho):
    imagem = Image.new("RGB", (1080, 1920), (255, 255, 255))
    imagem.paste((0, 0, 0), (270, 480, 810, 1440))
    return _salvar(caminho, imagem)


def test_zoom_aproxima_na_primeira_imagem_e_afasta_na_segunda(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    _quadrado_no_centro(pasta / IMAGEM)
    saida = pasta / "final.mp4"
    imagens = [ImagemNoVideo(0.2, 1.8, IMAGEM), ImagemNoVideo(2.0, 3.6, IMAGEM)]
    renderizar_final(Receita([(0.0, 4.0)], [], []), origem, cartao, pasta, saida, imagens=imagens)
    borda = (258, 960)  # fora do quadrado com zoom 1,00; dentro com zoom 1,08 (a borda vai a 248)
    escuro = lambda quadro: max(quadro.getpixel(borda)) < 80
    assert not escuro(_quadro(saida, 0.25, pasta / "a.png")) and escuro(_quadro(saida, 1.75, pasta / "b.png"))
    assert escuro(_quadro(saida, 2.05, pasta / "c.png")) and not escuro(_quadro(saida, 3.55, pasta / "d.png"))


def test_zoom_alterna_no_filtro():
    imagem = ImagemNoVideo(0.5, 2.5, IMAGEM)
    assert "(1+" in render._filtro_imagem(2, "img0", 0, imagem)
    assert f"({render.ZOOM_IMAGEM}-" in render._filtro_imagem(3, "img1", 1, imagem)


def test_legenda_some_durante_imagem(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    _salvar(pasta / IMAGEM, Image.new("RGB", (1080, 1920), (255, 0, 0)))
    saida = pasta / "final.mp4"
    receita = Receita([(0.0, 3.0)], [], [Cue(0, 3, ["LEGENDA BEM LONGA"])])
    renderizar_final(receita, origem, cartao, pasta, saida, imagens=[ImagemNoVideo(0.5, 2.5, IMAGEM)])
    assert _brancos_na_legenda(_quadro(saida, 0.2, pasta / "q0.png")) > 20
    assert _brancos_na_legenda(_quadro(saida, 1.5, pasta / "q1.png")) == 0


def test_imagem_ate_o_fim_da_parte_principal(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    _salvar(pasta / IMAGEM, Image.new("RGB", (1080, 1920), (255, 0, 0)))
    saida = pasta / "final.mp4"
    renderizar_final(Receita([(0.0, 3.0)], [], []), origem, cartao, pasta, saida, imagens=[ImagemNoVideo(1.0, 3.0, IMAGEM)])
    assert sondar(saida).duracao == pytest.approx(4, abs=0.2)
    assert _vermelho(_quadro(saida, 2.9, pasta / "q.png").getpixel((540, 960)))


def test_caminhos_com_acento_em_imagem_e_musica(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    arquivo = "imagens-sugeridas/0001-ação-1.jpg"
    _salvar(pasta / arquivo, Image.new("RGB", (1080, 1920), (255, 0, 0)))
    musica = _musica(pasta / "música ação.wav", 1)
    saida = pasta / "final.mp4"
    receita = Receita([(0.0, 3.0)], [], [Cue(0, 3, ["olá"])], musica=Musica(str(musica), -20.0))
    renderizar_final(receita, origem, cartao, pasta, saida, imagens=[ImagemNoVideo(0.5, 2.5, arquivo)])
    assert _vermelho(_quadro(saida, 1.5, pasta / "q.png").getpixel((540, 960)))
    assert sondar(saida).duracao == pytest.approx(4, abs=0.2)


def test_imagem_nao_muda_as_cores_do_resto_do_corte(tmp_path):
    """JPEG vem em faixa cheia (pc) e o vídeo em faixa limitada (tv): sem converter a imagem, o corte inteiro desbota."""
    pasta, origem, cartao = _cenario(tmp_path)
    _salvar(pasta / IMAGEM, Image.new("RGB", (1080, 1920), (255, 0, 0)))
    sem, com = pasta / "sem.mp4", pasta / "com.mp4"
    renderizar_final(Receita([(0.0, 3.0)], [], []), origem, cartao, pasta, sem)
    renderizar_final(Receita([(0.0, 3.0)], [], []), origem, cartao, pasta, com, imagens=[ImagemNoVideo(1.0, 2.5, IMAGEM)])
    for ponto in ((540, 960), (100, 1500), (900, 300)):
        a = _quadro(sem, 0.4, pasta / "a.png").getpixel(ponto)
        b = _quadro(com, 0.4, pasta / "b.png").getpixel(ponto)
        assert all(abs(x - y) <= 4 for x, y in zip(a, b)), (ponto, a, b)


def test_voz_normalizada_e_legenda_por_palavra_no_render_real(tmp_path, monkeypatch):
    from esteira import config

    monkeypatch.setattr(config, "atual", lambda: config.Config(normalizar_voz=True, legenda_estilo="palavra"))
    pasta, origem, cartao = _cenario(tmp_path)
    saida = pasta / "final.mp4"
    cue = Cue(0.0, 1.0, ["olá Brasil"], palavras=[[0.0, 0.4], [0.5, 1.0]])
    receita = Receita([(0.0, 1.0), (2.0, 3.0)], [], [cue], musica=Musica(str(_musica(tmp_path / "m.mp3", 5)), -24))
    renderizar_final(receita, origem, cartao, pasta, saida)
    m = sondar(saida)
    assert (m.largura, m.altura) == (1080, 1920) and m.tem_audio
    assert m.duracao == pytest.approx(3, abs=0.2)
    medida = saida_ffmpeg(["-i", str(saida), "-t", "2", "-af", "ebur128", "-f", "null", "-"])
    integrado = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", medida)[-1])
    assert -20 < integrado < -9  # perto do alvo de -14 LUFS (trecho curto, tolerância larga)


def test_filtro_de_voz_normalizada():
    from esteira.render import filtro_voz_normalizada

    assert filtro_voz_normalizada("a", "b", -14) == (
        "[a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[b]"
    )


# Acompanhamento suave e tela dividida (docs/enquadramento.md)

FILTRO_DE_SEMPRE = (
    "[0:v]trim=start=0.500:end=2.500,setpts=PTS-STARTPTS[t0];[t0]crop=562:540:103:162,split=2[v0a][v0b];"
    "[v0a]scale=-2:1920,crop=1080:1920,gblur=sigma=40[v0f];[v0b]scale=1080:1036[v0c];"
    "[v0f][v0c]overlay=0:442,fps=30,setsar=1,format=yuv420p[v0];"
    "[0:a]atrim=start=0.500:end=2.500,asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[a0];"
    "[0:v]trim=start=3.500:end=4.500,setpts=PTS-STARTPTS[t1];[t1]crop=562:540:103:162,split=2[v1a][v1b];"
    "[v1a]scale=-2:1920,crop=1080:1920,gblur=sigma=40[v1f];[v1b]scale=1080:1036[v1c];"
    "[v1f][v1c]overlay=0:442,fps=30,setsar=1,format=yuv420p[v1];"
    "[0:a]atrim=start=3.500:end=4.500,asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[a1];"
    "[0:v]trim=start=4.500:end=6.500,setpts=PTS-STARTPTS[t2];[t2]crop=832:800:1088:140,split=2[v2a][v2b];"
    "[v2a]scale=-2:1920,crop=1080:1920,gblur=sigma=40[v2f];[v2b]scale=1080:1036[v2c];"
    "[v2f][v2c]overlay=0:442,fps=30,setsar=1,format=yuv420p[v2];"
    "[0:a]atrim=start=4.500:end=6.500,asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[a2]"
)


def test_planos_de_sempre_geram_o_filtro_de_sempre():
    from esteira.planos import Plano, dividir_em_segmentos

    segmentos = dividir_em_segmentos(
        [(1.0, 3.0), (4.0, 7.0)], [Plano(0, 5, x=0.2, y=0.4, zoom=2.0), Plano(5, 10, x=0.8, zoom=1.35)]
    )
    partes, rotulos = render._filtro_segmentos(segmentos, 1920, 1080, 0.5)
    assert ";".join(partes) == FILTRO_DE_SEMPRE
    assert rotulos == "[v0][a0][v1][a1][v2][a2]"


def _vermelho_e_azul(caminho, segundos=4):
    """Metade esquerda vermelha, direita azul, com som."""
    executar_ffmpeg([
        "-y", "-f", "lavfi", "-i",
        f"color=c=red:s=1920x1080:r=30:d={segundos},drawbox=x=960:y=0:w=960:h=1080:color=blue:t=fill",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(caminho),
    ])
    return caminho


DIVISAO = [{"pessoa": "P1", "x": 0.25, "y": 0.5, "zoom": 2.0}, {"pessoa": "P2", "x": 0.75, "y": 0.5, "zoom": 2.0}]


def test_suave_move_o_recorte_dentro_do_plano(tmp_path):
    from esteira.planos import Plano

    pasta = tmp_path / "Tudo é Política (teste)"
    pasta.mkdir()
    origem = _vermelho_e_azul(pasta / "origem.mp4")
    cartao = gerar_video_teste(pasta / "fim.mp4", 1, 1080, 1920)
    plano = Plano(0, 3, x=0.25, zoom=2.0, trajeto=[[0, 0.25, 0.5], [1, 0.25, 0.5], [2, 0.75, 0.5], [3, 0.75, 0.5]])
    saida = pasta / "final.mp4"
    renderizar_final(Receita([(0.0, 3.0)], [plano], [], encerramento=False), origem, cartao, pasta, saida)
    assert sondar(saida).duracao == pytest.approx(3, abs=0.2)
    assert _vermelho(_quadro(saida, 0.5, pasta / "a.png").getpixel((540, 960)))
    assert _azul(_quadro(saida, 2.6, pasta / "b.png").getpixel((540, 960)))


def test_suave_atravessa_pausa_removida(tmp_path):
    from esteira.planos import Plano

    pasta = tmp_path / "Tudo é Política (teste)"
    pasta.mkdir()
    origem = _vermelho_e_azul(pasta / "origem.mp4")
    cartao = gerar_video_teste(pasta / "fim.mp4", 1, 1080, 1920)
    plano = Plano(0, 4, x=0.25, zoom=2.0, trajeto=[[0, 0.25, 0.5], [2, 0.25, 0.5], [2.4, 0.75, 0.5], [4, 0.75, 0.5]])
    saida = pasta / "final.mp4"
    receita = Receita([(0.0, 1.5), (2.5, 4.0)], [plano], [], encerramento=False)  # 1,5 a 2,5 removido
    renderizar_final(receita, origem, cartao, pasta, saida)
    assert sondar(saida).duracao == pytest.approx(3, abs=0.2)
    assert _vermelho(_quadro(saida, 1.2, pasta / "a.png").getpixel((540, 960)))
    assert _azul(_quadro(saida, 1.8, pasta / "b.png").getpixel((540, 960)))  # o tempo do trecho recomeça certo


def _brancos_na_emenda(quadro):
    return sum(1 for x in range(200, 880, 4) for y in range(915, 1005, 3) if min(quadro.getpixel((x, y))) > 235)


def test_tela_dividida_empilha_as_duas_pessoas_e_poe_a_legenda_na_emenda(tmp_path):
    from esteira.planos import Plano

    pasta = tmp_path / "Tudo é Política (teste)"
    pasta.mkdir()
    origem = _vermelho_e_azul(pasta / "origem.mp4")
    cartao = gerar_video_teste(pasta / "fim.mp4", 1, 1080, 1920)
    planos = [Plano(0, 1.5, x=0.25, zoom=2.0), Plano(1.5, 3, x=0.5, zoom=1.0, divisao=DIVISAO)]
    legenda = [Cue(0, 1.4, ["CHEIA"]), Cue(1.6, 3, ["DIVIDIDA"])]
    saida = pasta / "final.mp4"
    renderizar_final(Receita([(0.0, 3.0)], planos, legenda, encerramento=False), origem, cartao, pasta, saida)
    m = sondar(saida)
    assert (m.largura, m.altura) == (1080, 1920) and m.duracao == pytest.approx(3, abs=0.2)
    antes = _quadro(saida, 0.7, pasta / "a.png")
    assert _brancos_na_legenda(antes) > 20 and _brancos_na_emenda(antes) == 0
    depois = _quadro(saida, 2.3, pasta / "b.png")
    for y in (100, 480, 850):
        assert _vermelho(depois.getpixel((540, y)))  # metade de cima: pessoa da esquerda
    for y in (1100, 1440, 1850):
        assert _azul(depois.getpixel((540, y)))  # metade de baixo: pessoa da direita
    assert _brancos_na_emenda(depois) > 20  # legenda na emenda, longe dos rostos
    assert _brancos_na_legenda(depois) == 0


def test_filtro_longo_vai_num_arquivo(tmp_path, monkeypatch):
    from esteira.planos import Plano

    monkeypatch.setattr(render, "LIMITE_DO_FILTRO", 10)
    chamadas = []
    original = render.executar_ffmpeg

    def espiar(args, cwd=None, **kwargs):
        chamadas.append((list(args), cwd))
        return original(args, cwd, **kwargs)

    monkeypatch.setattr(render, "executar_ffmpeg", espiar)
    pasta = tmp_path / "Tudo é Política (teste)"
    pasta.mkdir()
    origem = _vermelho_e_azul(pasta / "origem.mp4")
    cartao = gerar_video_teste(pasta / "fim.mp4", 1, 1080, 1920)
    plano = Plano(0, 3, x=0.25, zoom=2.0, trajeto=[[0, 0.25, 0.5], [3, 0.75, 0.5]])
    saida = pasta / "final.mp4"
    renderizar_final(Receita([(0.0, 3.0)], [plano], [], encerramento=False), origem, cartao, pasta, saida)
    args, _ = chamadas[0]
    assert "-/filter_complex" in args and "-filter_complex" not in args
    assert _azul(_quadro(saida, 2.8, pasta / "b.png").getpixel((540, 960)))
    assert not (pasta / ".legenda_tmp").exists()


def test_tela_dividida_com_um_quadro_so_e_erro(tmp_path):
    from esteira.planos import Plano

    pasta, origem, cartao = _cenario(tmp_path)
    plano = Plano(0, 2, divisao=DIVISAO[:1])
    with pytest.raises(ValueError, match="divisao"):
        renderizar_final(Receita([(0.0, 2.0)], [plano], []), origem, cartao, pasta, pasta / "final.mp4")
    assert not (pasta / "final.mp4").exists()


@pytest.mark.parametrize(
    ("versao", "opcao"),
    [
        ("ffmpeg version 9.0-full_build-www.gyan.dev Copyright", "-/filter_complex"),
        ("ffmpeg version n7.1 Copyright", "-/filter_complex"),
        ("ffmpeg version 6.1.1-essentials_build-www.gyan.dev", "-filter_complex_script"),
        ("ffmpeg version 2023-11-02-git-abc-full_build-www.gyan.dev", "-filter_complex_script"),
        ("ffmpeg version 2025-06-02-git-abc-full_build-www.gyan.dev", "-/filter_complex"),
        ("ffmpeg version N-118000-gabc", "-/filter_complex"),
    ],
)
def test_opcao_do_filtro_em_arquivo_pela_versao(versao, opcao):
    assert render.opcao_filtro_em_arquivo(versao) == opcao
