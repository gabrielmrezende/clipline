import pytest

from esteira.midia import ErroMidia, sondar
from esteira.modelos import Cue
from esteira.legenda import escrever_ass
from esteira.render import filtro_9x16, queimar_legenda, renderizar_sem_legenda
from tests.auxiliares import gerar_video_teste


def _cenario(tmp_path):
    pasta = tmp_path / "Tudo é Política (teste)"
    pasta.mkdir()
    return pasta, gerar_video_teste(pasta / "origem.mp4", 4), gerar_video_teste(pasta / "fim.mp4", 1, 1080, 1920)


def test_render_em_caminho_com_acento(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    base = pasta / "sem.mp4"
    renderizar_sem_legenda(origem, [(0.0, 1.0)], cartao, base)
    ass = pasta / "origem.ass"
    escrever_ass([Cue(0, 1, ["olá Brasil"])], ass)
    saida = pasta / "com.mp4"
    queimar_legenda(base, ass, saida)
    m = sondar(saida)
    assert (m.largura, m.altura) == (1080, 1920)
    assert m.tem_audio


def test_duracao_soma_faixas_e_cartao(tmp_path):
    pasta, origem, cartao = _cenario(tmp_path)
    saida = pasta / "s.mp4"
    renderizar_sem_legenda(origem, [(0.0, 1.0), (2.0, 3.0)], cartao, saida)
    assert sondar(saida).duracao == pytest.approx(3, abs=0.2)


def test_cartao_sem_audio_recebe_silencio(tmp_path):
    pasta, origem, _ = _cenario(tmp_path)
    mudo = gerar_video_teste(pasta / "mudo.mp4", 1, 1080, 1920, audio=False)
    saida = pasta / "s.mp4"
    renderizar_sem_legenda(origem, [(0.0, 1.0)], mudo, saida)
    assert sondar(saida).tem_audio


def test_falha_nao_deixa_arquivo_final(tmp_path):
    pasta, _, cartao = _cenario(tmp_path)
    saida = pasta / "s.mp4"
    with pytest.raises(ErroMidia):
        renderizar_sem_legenda(pasta / "nao.mp4", [(0.0, 1.0)], cartao, saida)
    assert not saida.exists()
    assert not list(pasta.glob("*.tmp.mp4"))
