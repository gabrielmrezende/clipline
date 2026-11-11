import json
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from esteira.modelos import Corte, Cue
from esteira.painel.app import criar_app
from esteira.publicar.agendar import FUSO
from esteira.publicar.http import Resultado
from esteira.receita import Musica, Receita, gravar_receita, ler_receita
from tests.auxiliares import gerar_video_teste
from tests.auxiliares_painel import criar_episodio

CREDITO = "Música: Ice Flow — Kevin MacLeod (incompetech.com), licença CC BY 4.0"
AGORA = datetime(2026, 11, 1, 10, 0, tzinfo=FUSO)


class RedeFalsa:
    def __init__(self, estado):
        self.estado = estado
        self.chamadas = []

    def publicar(self, video, textos, data, modo, **extras):
        self.chamadas.append((modo, extras))
        return Resultado(self.estado, "https://x/1", "1")


@pytest.fixture
def cenario(tmp_path):
    cortes = tmp_path / "cortes"
    corte = Corte(1, "Bom corte", 1.0, 20.0, "leve", instagram=False)
    pasta = criar_episodio(cortes, "Ep 01", [corte], {1}, musica=Musica("m.mp3", credito=CREDITO))
    destino = pasta / "01-bom-corte"
    (destino / "video-final").mkdir()
    time.sleep(0.01)
    gerar_video_teste(destino / "video-final" / "final.mp4", 1, 1080, 1920)
    app = criar_app(cortes)
    youtube = RedeFalsa("privado")
    app.state.redes_publicar = lambda: {"youtube": youtube, "tiktok": RedeFalsa("rascunho"), "instagram": RedeFalsa("publicado")}
    app.state.modos_publicar = lambda: {"youtube": "privado", "tiktok": "rascunho"}
    app.state.agora_publicar = lambda: AGORA
    app.state.trava_publicar = tmp_path / "publicar.trava"
    return TestClient(app), pasta, youtube, app


def _esperar(app, id_):
    for _ in range(200):
        pedido = app.state.fila.pedido(id_)
        if pedido.estado in ("pronto", "erro"):
            return pedido
        time.sleep(0.02)
    raise AssertionError("a tarefa não terminou")


BASE = "/api/episodios/Ep%2001/cortes/1"


def test_resumo_e_confirmacao_pelo_painel(cenario):
    cliente, pasta, youtube, app = cenario
    corpo = {"data": "2026-11-08T18:00", "redes": ["youtube", "tiktok"]}
    r = cliente.post(f"{BASE}/publicacao/resumo", json=corpo)
    assert r.status_code == 200, r.text
    assert "Corte 1: Bom corte" in r.json()["resumo"]
    marca = r.json()["marca"]

    assert cliente.post(f"{BASE}/publicacao", json={**corpo, "marca": "outra", "confirmado": True}).status_code == 409
    r = cliente.post(f"{BASE}/publicacao", json={**corpo, "marca": marca, "confirmado": True})
    assert r.status_code == 202, r.text
    assert _esperar(app, r.json()["id"]).estado == "pronto"
    assert youtube.chamadas == [("privado", {})]
    itens = {i["rede"]: i["estado"] for i in cliente.get(f"{BASE}/publicacao").json()["itens"]}
    assert itens == {"youtube": "privado", "tiktok": "agendado"}


def test_sem_confirmado_nao_publica(cenario):
    cliente, *_ = cenario
    r = cliente.post(f"{BASE}/publicacao", json={"data": "2026-11-08T18:00", "redes": ["youtube"], "marca": "x"})
    assert r.status_code == 422


def test_resumo_com_problema_lista_os_motivos(cenario):
    cliente, pasta, *_ = cenario
    (pasta / "01-bom-corte" / "video-final" / "final.mp4").unlink()
    r = cliente.post(f"{BASE}/publicacao/resumo", json={"data": "2026-11-08T18:00", "redes": ["youtube"]})
    assert r.status_code == 422
    assert "video-final/ sem vídeo" in r.json()["problemas"]


def test_cancelar_o_que_esta_agendado(cenario):
    cliente, pasta, _, app = cenario
    corpo = {"data": "2026-11-08T18:00", "redes": ["tiktok"]}
    marca = cliente.post(f"{BASE}/publicacao/resumo", json=corpo).json()["marca"]
    _esperar(app, cliente.post(f"{BASE}/publicacao", json={**corpo, "marca": marca, "confirmado": True}).json()["id"])
    r = cliente.post(f"{BASE}/publicacao/cancelar", json={"redes": ["tiktok"], "confirmado": True})
    assert r.json()["mensagens"] == ["tiktok: cancelado"] and r.json()["itens"] == []


# --- legenda -------------------------------------------------------------------------------------------


@pytest.fixture
def legenda(tmp_path):
    cortes = tmp_path / "cortes"
    pasta = criar_episodio(cortes, "Ep 01", [Corte(1, "Bom corte", 1.0, 20.0, "leve")], {1})
    trabalho = pasta / "01-bom-corte" / "trabalho"
    cues = [Cue(0.0, 1.0, ["olá Brazil"], palavras=[[0.0, 0.4], [0.5, 1.0]]), Cue(1.0, 2.0, ["tudo bem"])]
    gravar_receita(trabalho, Receita([(1.0, 20.0)], [], cues))
    return TestClient(criar_app(cortes)), trabalho


def test_editar_texto_da_legenda(legenda):
    cliente, trabalho = legenda
    lida = cliente.get(f"{BASE}/legenda").json()
    assert [t["linhas"] for t in lida["telas"]] == [["olá Brazil"], ["tudo bem"]]
    r = cliente.put(f"{BASE}/legenda", json={"versao": lida["versao"], "telas": [{"indice": 0, "linhas": ["olá  Brasil"]}]})
    assert r.status_code == 200, r.text
    receita = ler_receita(trabalho)
    assert receita.legenda[0].linhas == ["olá Brasil"]
    assert receita.legenda[0].palavras == [[0.0, 0.4], [0.5, 1.0]]  # mesmo número de palavras: o tempo continua
    assert "olá Brasil" in (trabalho / "legenda.srt").read_text("utf-8")


def test_mudar_o_numero_de_palavras_tira_o_tempo_por_palavra(legenda):
    cliente, trabalho = legenda
    versao = cliente.get(f"{BASE}/legenda").json()["versao"]
    cliente.put(f"{BASE}/legenda", json={"versao": versao, "telas": [{"indice": 0, "linhas": ["olá"]}]})
    assert ler_receita(trabalho).legenda[0].palavras is None


@pytest.mark.parametrize("linhas, trecho", [([""], "vazia"), (["a", "b", "c"], "2 linhas"), (["x" * 41], "40")])
def test_legenda_invalida(legenda, linhas, trecho):
    cliente, _ = legenda
    versao = cliente.get(f"{BASE}/legenda").json()["versao"]
    r = cliente.put(f"{BASE}/legenda", json={"versao": versao, "telas": [{"indice": 0, "linhas": linhas}]})
    assert r.status_code == 422 and trecho in r.json()["detail"]


def test_legenda_mudou_por_fora(legenda):
    cliente, trabalho = legenda
    versao = cliente.get(f"{BASE}/legenda").json()["versao"]
    dados = json.loads((trabalho / "montagem.json").read_text("utf-8"))
    dados["legenda"][1]["linhas"] = ["mudou"]
    (trabalho / "montagem.json").write_text(json.dumps(dados), "utf-8")
    r = cliente.put(f"{BASE}/legenda", json={"versao": versao, "telas": [{"indice": 0, "linhas": ["x"]}]})
    assert r.status_code == 409
