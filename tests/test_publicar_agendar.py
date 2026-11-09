import json
import os
from datetime import datetime

import pytest

from esteira.midia import Midia
from esteira.publicar import agendar, fila
from esteira.publicar.agendar import FUSO, ErroAgendar, confirmar, ler_data, preparar_pedido, resumo
from esteira.publicar.config import ler_modos
from esteira.publicar.credenciais import ErroConexao
from esteira.publicar.fila import Item, gravar_fila, ler_fila
from esteira.publicar.http import ErroRede, Resultado
from tests.auxiliares_publicar import CREDITO
from tests.test_publicar_post import POST_CORTE_1

AGORA = datetime(2026, 11, 6, 12, 0, tzinfo=FUSO)
MODOS = {"youtube": "privado", "tiktok": "rascunho"}
TODAS = ["youtube", "instagram", "tiktok"]
CREDITO_ICE = "Música: Ice Flow — Kevin MacLeod (incompetech.com), licença CC BY 4.0"


class RedeFalsa:
    def __init__(self, resultado=None, erro=None, ao_publicar=None):
        self.resultado, self.erro, self.ao_publicar = resultado, erro, ao_publicar
        self.chamadas = []

    def publicar(self, video, textos, data, modo):
        self.chamadas.append((video, textos, data, modo))
        if self.ao_publicar:
            self.ao_publicar()
        if self.erro:
            raise self.erro
        return self.resultado


@pytest.fixture(autouse=True)
def _sem_restricao(monkeypatch):
    monkeypatch.setattr(fila, "garantir_escrita", lambda caminho: caminho)


@pytest.fixture
def episodio(tmp_path, monkeypatch):
    pasta = tmp_path / "ep"
    corte = pasta / "01-a-formula-1-faz-sportswashing"
    (corte / "video-final").mkdir(parents=True)
    (corte / "trabalho").mkdir()
    (corte / "video-final" / "Corte 1.mp4").write_bytes(b"VIDEO")
    (corte / "post.md").write_text(POST_CORTE_1, "utf-8")
    montagem = {"faixas": [], "planos": [], "legenda": [], "musica": {"arquivo": "x.mp3", "credito": CREDITO_ICE}}
    (corte / "trabalho" / "montagem.json").write_text(json.dumps(montagem), "utf-8")
    aprovados = {"cortes": [{"numero": 1, "titulo": "A Fórmula 1 faz sportswashing?", "inicio": 0, "fim": 95, "clima": "tenso"}]}
    (pasta / "aprovados.json").write_text(json.dumps(aprovados), "utf-8")
    midia = {"valor": Midia(95.8, 1080, 1920, True)}
    monkeypatch.setattr(agendar, "sondar", lambda video: midia["valor"])
    return pasta, corte, midia


def test_ler_data():
    assert ler_data("2026-11-08 18:00", AGORA) == datetime(2026, 11, 8, 18, 0, tzinfo=FUSO)


def test_ler_data_formato_errado():
    with pytest.raises(ErroAgendar, match="data inválida: use AAAA-MM-DD HH:MM"):
        ler_data("08/11 18h", AGORA)


def test_ler_data_passado():
    with pytest.raises(ErroAgendar, match="data no passado"):
        ler_data("2026-11-05 18:00", AGORA)


def test_pedido_bom(episodio):
    pasta, corte, _ = episodio
    pedido = preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)
    assert pedido.video == corte / "video-final" / "Corte 1.mp4"
    assert pedido.redes == TODAS
    assert pedido.textos.youtube_titulo.startswith("A Fórmula 1 faz sportswashing?")


def test_corte_inexistente(episodio):
    with pytest.raises(ErroAgendar, match="corte 7 não está no aprovados.json"):
        preparar_pedido(episodio[0], 7, "2026-11-08 18:00", TODAS, AGORA)


def test_rede_desconhecida(episodio):
    with pytest.raises(ErroAgendar, match="rede desconhecida: facebook"):
        preparar_pedido(episodio[0], 1, "2026-11-08 18:00", ["facebook"], AGORA)


def test_sem_video_final(episodio):
    pasta, corte, _ = episodio
    (corte / "video-final" / "Corte 1.mp4").unlink()
    with pytest.raises(ErroAgendar, match="video-final/ sem vídeo"):
        preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)


def test_dois_videos(episodio):
    pasta, corte, _ = episodio
    (corte / "video-final" / "Corte 1 v2.MP4").write_bytes(b"V")
    with pytest.raises(ErroAgendar, match="video-final/ com 2 vídeos: deixe só um"):
        preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)


def test_video_horizontal(episodio):
    pasta, _, midia = episodio
    midia["valor"] = Midia(95.8, 1920, 1080, True)
    with pytest.raises(ErroAgendar, match="vídeo 1920x1080, esperado 1080x1920"):
        preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)


def test_video_longo_so_barra_youtube(episodio):
    pasta, _, midia = episodio
    midia["valor"] = Midia(185.0, 1080, 1920, True)
    with pytest.raises(ErroAgendar, match="youtube: vídeo com 3:05; o Shorts aceita até 3:00"):
        preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)
    assert preparar_pedido(pasta, 1, "2026-11-08 18:00", ["instagram"], AGORA).redes == ["instagram"]


def test_junta_todos_os_problemas(episodio):
    pasta, corte, _ = episodio
    (corte / "video-final" / "Corte 1.mp4").unlink()
    (corte / "post.md").unlink()
    with pytest.raises(ErroAgendar) as erro:
        preparar_pedido(pasta, 1, "2026-11-05 18:00", TODAS, AGORA)
    linhas = str(erro.value).splitlines()
    assert any("video-final/ sem vídeo" in l for l in linhas)
    assert any("post.md não encontrado" in l for l in linhas)
    assert any("data no passado" in l for l in linhas)


def test_falta_credito_da_musica(episodio):
    pasta, corte, _ = episodio
    (corte / "post.md").write_text(POST_CORTE_1.replace("Ice Flow", "Outra"), "utf-8")
    with pytest.raises(ErroAgendar, match="youtube: falta o crédito da música"):
        preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)


def test_ja_agendado(episodio):
    pasta, _, _ = episodio
    gravar_fila(pasta, [Item(1, "youtube", "2026-11-08T18:00:00-03:00")])
    with pytest.raises(ErroAgendar, match="youtube: corte 1 já agendado"):
        preparar_pedido(pasta, 1, "2026-11-09 18:00", TODAS, AGORA)
    assert preparar_pedido(pasta, 1, "2026-11-09 18:00", ["instagram"], AGORA)


def test_item_com_erro_ou_cancelado_libera(episodio):
    pasta, _, _ = episodio
    gravar_fila(pasta, [Item(1, "youtube", "x", "erro"), Item(1, "instagram", "x", "cancelado")])
    assert preparar_pedido(pasta, 1, "2026-11-09 18:00", TODAS, AGORA)


def test_resumo(episodio):
    pedido = preparar_pedido(episodio[0], 1, "2026-11-08 18:00", TODAS, AGORA)
    texto = resumo(pedido, MODOS)
    assert texto.splitlines()[0] == "Corte 1: A Fórmula 1 faz sportswashing?"
    assert "Corte 1.mp4 (1:36, 1080x1920)" in texto
    assert "domingo, 08/11/2026 às 18:00 (Brasília)" in texto
    assert "YouTube (privado: você muda para agendado no Studio)" in texto
    assert "TikTok (rascunho: o texto não vai junto; cole no app)" in texto
    assert pedido.textos.instagram in texto and pedido.textos.youtube_descricao in texto


def test_confirmar_envia_youtube_e_agenda_resto(episodio):
    pasta, _, _ = episodio
    pedido = preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)
    rede = RedeFalsa(Resultado("privado", "L", "I"))
    itens = confirmar(pedido, MODOS, {"youtube": rede})
    assert [(i.rede, i.estado) for i in itens] == [("youtube", "privado"), ("instagram", "agendado"), ("tiktok", "agendado")]
    assert itens[0].link == "L" and itens[0].id_rede == "I"
    assert itens[1].data == "2026-11-08T18:00:00-03:00"
    assert ler_fila(pasta) == itens
    assert rede.chamadas[0][3] == "privado"


def test_confirmar_grava_enviando_antes(episodio):
    pasta, _, _ = episodio
    pedido = preparar_pedido(pasta, 1, "2026-11-08 18:00", ["youtube"], AGORA)
    vistos = []
    rede = RedeFalsa(Resultado("privado", "L", "I"), ao_publicar=lambda: vistos.append(ler_fila(pasta)[0].estado))
    confirmar(pedido, MODOS, {"youtube": rede})
    assert vistos == ["enviando"]


def test_confirmar_youtube_falha_temporaria_fica_agendado(episodio):
    pasta, _, _ = episodio
    pedido = preparar_pedido(pasta, 1, "2026-11-08 18:00", ["youtube"], AGORA)
    itens = confirmar(pedido, MODOS, {"youtube": RedeFalsa(erro=ErroRede("youtube: HTTP 503", True))})
    assert (itens[0].estado, itens[0].tentativas, itens[0].erro) == ("agendado", 1, "youtube: HTTP 503")


def test_confirmar_youtube_sem_conexao_vira_erro(episodio):
    pasta, _, _ = episodio
    pedido = preparar_pedido(pasta, 1, "2026-11-08 18:00", ["youtube"], AGORA)
    itens = confirmar(pedido, MODOS, {"youtube": RedeFalsa(erro=ErroConexao("conta não conectada", "youtube"))})
    assert itens[0].estado == "erro"
    assert itens[0].erro.endswith("reconecte com publicar conectar youtube")


def test_confirmar_substitui_item_com_erro(episodio):
    pasta, _, _ = episodio
    gravar_fila(pasta, [Item(1, "instagram", "x", "erro", 3, "", "", "falhou")])
    pedido = preparar_pedido(pasta, 1, "2026-11-08 18:00", ["instagram"], AGORA)
    itens = confirmar(pedido, MODOS, {})
    assert [(i.rede, i.estado) for i in ler_fila(pasta)] == [("instagram", "agendado")]
    assert itens == ler_fila(pasta)


def test_nao_grava_nada_em_video_final(episodio):
    pasta, corte, _ = episodio
    antes = sorted(p.name for p in (corte / "video-final").iterdir())
    pedido = preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)
    confirmar(pedido, MODOS, {"youtube": RedeFalsa(Resultado("privado", "L", "I"))})
    assert sorted(p.name for p in (corte / "video-final").iterdir()) == antes


def test_modos_padrao(tmp_path):
    assert ler_modos(tmp_path / "nao.json") == {"youtube": "privado", "tiktok": "rascunho"}


def test_modos_do_arquivo(tmp_path):
    caminho = tmp_path / "publicacao.json"
    caminho.write_text('{"youtube": "agendado"}', "utf-8")
    assert ler_modos(caminho) == {"youtube": "agendado", "tiktok": "rascunho"}


def test_modo_desconhecido(tmp_path):
    caminho = tmp_path / "publicacao.json"
    caminho.write_text('{"tiktok": "publico"}', "utf-8")
    with pytest.raises(ValueError, match="tiktok"):
        ler_modos(caminho)


def test_confirmar_grava_assinatura(episodio):
    from esteira.publicar.envio import assinatura
    pasta, _, _ = episodio
    pedido = preparar_pedido(pasta, 1, "2026-11-08 18:00", ["instagram"], AGORA)
    item = confirmar(pedido, MODOS, {})[0]
    assert item.assinatura == assinatura(pedido.video, pedido.textos, "instagram") != ""


DESATUALIZADO = "vídeo final mais antigo que o corte.mp4: refaça no CapCut"


def _datas(corte, video_final, corte_mp4):
    os.utime(corte / "video-final" / "Corte 1.mp4", (video_final, video_final))
    (corte / "corte.mp4").write_bytes(b"CORTE")
    os.utime(corte / "corte.mp4", (corte_mp4, corte_mp4))


def test_recusa_video_final_mais_antigo_que_o_corte(episodio):
    pasta, corte, _ = episodio
    _datas(corte, video_final=1_000_000, corte_mp4=2_000_000)
    with pytest.raises(ErroAgendar) as erro:
        preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)
    assert DESATUALIZADO in str(erro.value).splitlines()


def test_aceita_video_final_mais_novo_que_o_corte(episodio):
    pasta, corte, _ = episodio
    _datas(corte, video_final=2_000_000, corte_mp4=1_000_000)
    assert preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA).video == corte / "video-final" / "Corte 1.mp4"


def test_sem_corte_mp4_nao_recusa_por_data(episodio):
    pasta, corte, _ = episodio
    os.utime(corte / "video-final" / "Corte 1.mp4", (1_000_000, 1_000_000))
    assert not (corte / "corte.mp4").exists()
    assert preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)
