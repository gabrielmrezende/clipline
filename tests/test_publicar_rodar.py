import json
from datetime import datetime, timedelta

import pytest

from esteira.publicar import fila, rodar
from esteira.publicar.agendar import FUSO
from esteira.publicar.credenciais import ErroConexao
from esteira.publicar.fila import Item, gravar_fila, ler_fila, trava
from esteira.publicar.envio import assinatura
from esteira.publicar.http import ErroIncerto, ErroRede, Resultado
from esteira.publicar.rodar import rodar_episodio, rodar_tudo
from tests.test_publicar_agendar import RedeFalsa
from tests.test_publicar_post import POST_CORTE_1

DATA = "2026-11-08T18:00:00-03:00"
NA_HORA = datetime(2026, 11, 8, 18, 5, tzinfo=FUSO)
MODOS = {"youtube": "privado", "tiktok": "rascunho"}


@pytest.fixture(autouse=True)
def _sem_restricao(monkeypatch):
    monkeypatch.setattr(fila, "garantir_escrita", lambda caminho: caminho)


def _episodio(base, nome="ep"):
    pasta = base / nome
    corte = pasta / "01-a-formula-1-faz-sportswashing"
    (corte / "video-final").mkdir(parents=True)
    (corte / "video-final" / "Corte 1.mp4").write_bytes(b"VIDEO")
    (corte / "post.md").write_text(POST_CORTE_1, "utf-8")
    aprovados = {"cortes": [{"numero": 1, "titulo": "A Fórmula 1 faz sportswashing?", "inicio": 0, "fim": 95, "clima": "tenso"}]}
    (pasta / "aprovados.json").write_text(json.dumps(aprovados), "utf-8")
    return pasta


def test_publica_vencido(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA)])
    rede = RedeFalsa(Resultado("publicado", "https://ig/reel/X", "M1"))
    linhas = rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": rede})
    item = ler_fila(pasta)[0]
    assert (item.estado, item.link, item.id_rede) == ("publicado", "https://ig/reel/X", "M1")
    assert linhas == ["01 instagram: publicado https://ig/reel/X"]
    video, textos, data, modo = rede.chamadas[0]
    assert video.name == "Corte 1.mp4" and textos.instagram.startswith("A Fórmula 1")
    assert data == datetime(2026, 11, 8, 18, 0, tzinfo=FUSO)


def test_nao_publica_futuro(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA)])
    rede = RedeFalsa(Resultado("publicado", "L", "I"))
    assert rodar_episodio(pasta, NA_HORA - timedelta(hours=1), MODOS, {"instagram": rede}) == []
    assert rede.chamadas == [] and ler_fila(pasta)[0].estado == "agendado"


def test_atrasado_dois_dias_publica(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA)])
    rodar_episodio(pasta, NA_HORA + timedelta(days=2), MODOS, {"instagram": RedeFalsa(Resultado("publicado", "L", "I"))})
    assert ler_fila(pasta)[0].estado == "publicado"


def test_enviando_vira_conferir(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA, "enviando")])
    rede = RedeFalsa(Resultado("publicado", "L", "I"))
    linhas = rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": rede})
    item = ler_fila(pasta)[0]
    assert rede.chamadas == []
    assert item.estado == "conferir"
    assert item.erro == "envio interrompido: confira no app e use publicar marcar"
    assert linhas == ["01 instagram: conferir (envio interrompido: confira no app e use publicar marcar)"]


def test_temporario_tres_vezes_vira_erro(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA)])
    rede = RedeFalsa(erro=ErroRede("instagram: HTTP 503: sem detalhe", True))
    estados = []
    for _ in range(3):
        rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": rede})
        estados.append(ler_fila(pasta)[0].estado)
    assert estados == ["agendado", "agendado", "erro"]
    assert ler_fila(pasta)[0].tentativas == 3


def test_conexao_vai_direto_para_erro(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA)])
    rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": RedeFalsa(erro=ErroConexao("token vencido", "instagram"))})
    item = ler_fila(pasta)[0]
    assert item.estado == "erro" and item.erro.endswith("reconecte com publicar conectar instagram")


def test_grava_enviando_antes_de_chamar(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA)])
    vistos = []
    rede = RedeFalsa(Resultado("publicado", "L", "I"), ao_publicar=lambda: vistos.append(ler_fila(pasta)[0].estado))
    rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": rede})
    assert vistos == ["enviando"]


def test_video_sumiu_vira_erro(tmp_path):
    pasta = _episodio(tmp_path)
    (pasta / "01-a-formula-1-faz-sportswashing" / "video-final" / "Corte 1.mp4").unlink()
    gravar_fila(pasta, [Item(1, "instagram", DATA)])
    rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": RedeFalsa(Resultado("publicado", "L", "I"))})
    item = ler_fila(pasta)[0]
    assert item.estado == "erro" and "video-final/" in item.erro


def test_post_apagado_vira_erro(tmp_path):
    pasta = _episodio(tmp_path)
    (pasta / "01-a-formula-1-faz-sportswashing" / "post.md").unlink()
    gravar_fila(pasta, [Item(1, "instagram", DATA)])
    rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": RedeFalsa(Resultado("publicado", "L", "I"))})
    assert "post.md não encontrado" in ler_fila(pasta)[0].erro


def test_rascunho_tiktok_guarda_aviso(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "tiktok", DATA)])
    rede = RedeFalsa(Resultado("rascunho", "", "P1"))
    rodar_episodio(pasta, NA_HORA, MODOS, {"tiktok": rede})
    item = ler_fila(pasta)[0]
    assert item.estado == "rascunho" and "cole o texto do post.md no app" in item.erro
    assert rede.chamadas[0][3] == "rascunho"


def test_ignora_publicados_e_cancelados(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA, "publicado"), Item(1, "tiktok", DATA, "cancelado")])
    rede = RedeFalsa(Resultado("publicado", "L", "I"))
    assert rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": rede, "tiktok": rede}) == []
    assert rede.chamadas == []


def test_trava_ocupada(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA)])
    rede = RedeFalsa(Resultado("publicado", "L", "I"))
    caminho = tmp_path / "publicar.trava"
    with trava(caminho):
        linhas = rodar_tudo(tmp_path, NA_HORA, {"instagram": rede}, caminho_trava=caminho, modos=MODOS)
    assert linhas == ["outra execução em andamento"]
    assert rede.chamadas == []


def test_erro_num_episodio_nao_para_outro(tmp_path):
    ruim = _episodio(tmp_path, "a-ruim")
    (ruim / "postagens.json").write_text("{quebrado", "utf-8")
    bom = _episodio(tmp_path, "b-bom")
    gravar_fila(bom, [Item(1, "instagram", DATA)])
    linhas = rodar_tudo(tmp_path, NA_HORA, {"instagram": RedeFalsa(Resultado("publicado", "L", "I"))},
                        caminho_trava=tmp_path / "t.trava", modos=MODOS)
    assert ler_fila(bom)[0].estado == "publicado"
    assert any(l.startswith("a-ruim: erro") for l in linhas)


def test_excecao_inesperada_vira_conferir_e_segue(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA), Item(1, "tiktok", DATA)])
    redes = {"instagram": RedeFalsa(erro=RuntimeError("boom")), "tiktok": RedeFalsa(Resultado("rascunho", "", "P"))}
    rodar_episodio(pasta, NA_HORA, MODOS, redes)
    instagram, tiktok = ler_fila(pasta)
    assert instagram.estado == "conferir" and "boom" in instagram.erro
    assert tiktok.estado == "rascunho"


def test_sem_keyring_vira_erro(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA)])
    rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": RedeFalsa(erro=ModuleNotFoundError("No module named 'keyring'"))})
    item = ler_fila(pasta)[0]
    assert item.estado == "erro" and "keyring" in item.erro


def test_erro_depois_de_publicar_vira_conferir(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "tiktok", DATA)])
    rodar_episodio(pasta, NA_HORA, MODOS, {"tiktok": RedeFalsa(erro=ErroIncerto("tiktok: status indisponível"))})
    item = ler_fila(pasta)[0]
    assert item.estado == "conferir" and item.tentativas == 0


def test_youtube_reenviado_sem_esperar_a_data(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "youtube", DATA, tentativas=1)])
    rede = RedeFalsa(Resultado("privado", "L", "I"))
    rodar_episodio(pasta, NA_HORA - timedelta(days=1), MODOS, {"youtube": rede})
    assert ler_fila(pasta)[0].estado == "privado"


def test_conteudo_mudou_depois_do_sim_vira_erro(tmp_path):
    pasta = _episodio(tmp_path)
    gravar_fila(pasta, [Item(1, "instagram", DATA, assinatura="antiga")])
    rede = RedeFalsa(Resultado("publicado", "L", "I"))
    rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": rede})
    item = ler_fila(pasta)[0]
    assert rede.chamadas == [] and item.estado == "erro" and "mudou depois da confirmação" in item.erro


def test_conteudo_igual_publica(tmp_path):
    pasta = _episodio(tmp_path)
    from esteira.publicar.post import ler_post
    corte = pasta / "01-a-formula-1-faz-sportswashing"
    marca = assinatura(corte / "video-final" / "Corte 1.mp4", ler_post(corte / "post.md"), "instagram")
    gravar_fila(pasta, [Item(1, "instagram", DATA, assinatura=marca)])
    rodar_episodio(pasta, NA_HORA, MODOS, {"instagram": RedeFalsa(Resultado("publicado", "L", "I"))})
    assert ler_fila(pasta)[0].estado == "publicado"
