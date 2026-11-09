import json
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from esteira.midia import ErroMidia
from esteira.modelos import Corte
from esteira.musica import Faixa
from esteira.painel.acesso import gerar_codigo
from esteira.painel.app import criar_app
from esteira.painel.fila import Fila
from esteira.painel.troca_musica import Resultado
from esteira.receita import Musica
from tests.auxiliares_painel import criar_episodio
from tests.test_painel_acesso import CofreFalso, Relogio, _entrar

NOME = "Entre Assuntos 03 - Arthur Cerqueira (teste capcut)"
AGORA = datetime(2026, 11, 7, 10)
CORTE = Corte(1, "Um", 10, 20, "tenso")
FAIXAS = [
    Faixa("Sunshine A", "leve", 120.0, "leve/Sunshine A.mp3", "Música: Sunshine A"),
    Faixa("Tensa B", "tenso", 100.5, "tenso/Tensa B.mp3", "Música: Tensa B"),
    Faixa("Tensa C", "tenso", 90.0, "tenso/Tensa C.mp3", "Música: Tensa C"),
]
CORPO = {"arquivo": "tenso/Tensa C.mp3", "volume_db": -22}


@pytest.fixture
def ambiente(tmp_path):
    musicas = tmp_path / "musicas"
    for faixa in FAIXAS:
        (musicas / faixa.arquivo).parent.mkdir(parents=True, exist_ok=True)
        (musicas / faixa.arquivo).write_bytes(b"ID3dummy-mp3")
    (musicas / "catalogo.json").write_text(
        json.dumps([f.__dict__ for f in FAIXAS], ensure_ascii=False), "utf-8"
    )
    cortes = tmp_path / "cortes"
    cortes.mkdir()
    filas: list[Fila] = []

    def construir(executar=None, **extra):
        chamadas = []

        def padrao(pasta, numero, faixa, volume_db):
            chamadas.append((pasta, numero, faixa, volume_db))
            return Resultado("pronto", "ok", [], None)

        fila = Fila(executar or padrao)
        filas.append(fila)
        musica = extra.pop("musica", Musica(str(musicas / "tenso/Tensa B.mp3"), -26.0, "Tensa B", "c"))
        pasta = criar_episodio(cortes, NOME, [CORTE], {1}, musica=musica)
        (pasta / "episodio.json").write_text(json.dumps({"video": str(tmp_path / "ep.mp4")}), "utf-8")
        app = criar_app(cortes, agora=lambda: AGORA, fila=fila, pasta_musicas=musicas, **extra)
        return TestClient(app), pasta, fila, chamadas

    yield construir, musicas
    for fila in filas:
        fila.parar(2)


def _url(sufixo: str) -> str:
    return "/api/episodios/" + quote(NOME) + "/cortes/1/musica" + sufixo


def _esperar(condicao):
    for _ in range(100):
        valor = condicao()
        if valor:
            return valor
        threading.Event().wait(0.05)
    return condicao()


def test_lista_do_episodio_e_biblioteca(ambiente):
    construir, _ = ambiente
    cliente, pasta, _, _ = construir()
    (pasta / "musicas-do-episodio.json").write_text(
        json.dumps({"faixas": [
            {"arquivo": "tenso/Tensa C.mp3", "motivo": "combina"},
            {"arquivo": "tenso/Some.mp3", "motivo": "x"},
        ]}), "utf-8")
    dados = cliente.get("/api/episodios/" + quote(NOME) + "/musicas").json()
    assert dados["do_episodio"] == [
        {"arquivo": "tenso/Tensa C.mp3", "titulo": "Tensa C", "clima": "tenso", "duracao": 90.0, "motivo": "combina"}
    ]
    assert dados["avisos"] == ["faixa fora do catálogo: tenso/Some.mp3"]
    assert dados["biblioteca"]["leve"] == [{"arquivo": "leve/Sunshine A.mp3", "titulo": "Sunshine A", "duracao": 120.0}]
    assert [f["titulo"] for f in dados["biblioteca"]["tenso"]] == ["Tensa B", "Tensa C"]


def test_lista_sem_arquivo_do_episodio(ambiente):
    construir, _ = ambiente
    cliente, *_ = construir()
    dados = cliente.get("/api/episodios/" + quote(NOME) + "/musicas").json()
    assert dados["do_episodio"] == [] and dados["avisos"] == []


def test_faixa_com_espaco_na_url(ambiente):
    construir, _ = ambiente
    cliente, *_ = construir()
    resposta = cliente.get("/api/musicas/leve/Sunshine%20A.mp3")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "audio/mpeg"
    assert resposta.content == b"ID3dummy-mp3"
    parcial = cliente.get("/api/musicas/leve/Sunshine%20A.mp3", headers={"Range": "bytes=0-2"})
    assert parcial.status_code == 206 and parcial.content == b"ID3"


@pytest.mark.parametrize("caminho", [
    "/api/musicas/leve/Outra.mp3", "/api/musicas/tenso/Sunshine%20A.mp3",
    "/api/musicas/leve/..%2Fcatalogo.json", "/api/musicas/leve/%2E%2E",
])
def test_faixa_fora_do_catalogo_404(ambiente, caminho):
    construir, musicas = ambiente
    cliente, *_ = construir()
    (musicas / "leve" / "Outra.mp3").write_bytes(b"x")  # existe em disco, mas não no catálogo
    assert cliente.get(caminho).status_code == 404


def test_post_musica_202_e_409(ambiente):
    construir, _ = ambiente
    solto, entrou = threading.Event(), threading.Event()

    def bloqueado(pasta, numero, faixa, volume_db):
        entrou.set()
        solto.wait(5)
        return Resultado("pronto", "ok", [], None)

    cliente, _, _, _ = construir(bloqueado)
    try:
        primeira = cliente.post(_url(""), json=CORPO)
        assert primeira.status_code == 202
        pedido = primeira.json()
        assert pedido["numero"] == 1 and pedido["arquivo"] == "tenso/Tensa C.mp3"
        assert pedido["volume_db"] == -22 and pedido["estado"] in ("na fila", "montando")
        entrou.wait(5)
        segunda = cliente.post(_url(""), json=CORPO)
        assert segunda.status_code == 409
        assert segunda.json() == {"detail": "Este corte já está sendo montado."}
        estado = cliente.get(_url("")).json()
        assert estado["pedido"]["id"] == pedido["id"]
        grade = cliente.get("/api/episodios/" + quote(NOME)).json()
        assert grade["cortes"][0]["montando"] is True
        assert cliente.get("/api/tarefas").json()[0]["id"] == pedido["id"]
    finally:
        solto.set()


def test_post_musica_executa_com_a_faixa_do_catalogo(ambiente):
    construir, _ = ambiente
    cliente, pasta, fila, chamadas = construir()
    pedido = cliente.post(_url(""), json={"arquivo": "tenso/Tensa C.mp3", "volume_db": -20}).json()
    dados = _esperar(lambda: (d := cliente.get(f"/api/tarefas/{pedido['id']}").json())["estado"] == "pronto" and d)
    assert dados["estado"] == "pronto"
    assert chamadas[0][0] == pasta and chamadas[0][1] == 1
    assert chamadas[0][2] == FAIXAS[2] and chamadas[0][3] == -20
    grade = cliente.get("/api/episodios/" + quote(NOME)).json()
    assert grade["cortes"][0]["montando"] is False
    assert cliente.get("/api/tarefas/naoexiste").status_code == 404


@pytest.mark.parametrize("volume", [-31, -17, -30.5, -17.9])
def test_volume_fora_422(ambiente, volume):
    construir, _ = ambiente
    cliente, _, fila, chamadas = construir()
    resposta = cliente.post(_url(""), json={"arquivo": "tenso/Tensa C.mp3", "volume_db": volume})
    assert resposta.status_code == 422
    assert fila.pedidos() == []


@pytest.mark.parametrize("volume", [-30, -18])
def test_volume_nos_limites_aceito(ambiente, volume):
    construir, _ = ambiente
    cliente, *_ = construir()
    assert cliente.post(_url(""), json={"arquivo": "tenso/Tensa C.mp3", "volume_db": volume}).status_code == 202


def test_faixa_desconhecida_422(ambiente):
    construir, _ = ambiente
    cliente, _, fila, _ = construir()
    resposta = cliente.post(_url(""), json={"arquivo": "tenso/Nao Existe.mp3", "volume_db": -22})
    assert resposta.status_code == 422
    assert fila.pedidos() == []


def test_corte_inexistente_404(ambiente):
    construir, _ = ambiente
    cliente, *_ = construir()
    url = "/api/episodios/" + quote(NOME) + "/cortes/9/musica"
    assert cliente.post(url, json=CORPO).status_code == 404
    assert cliente.get(url).status_code == 404


def test_get_musica_atual_do_montagem(ambiente):
    construir, _ = ambiente
    cliente, *_ = construir()
    assert cliente.get(_url("")).json() == {
        "atual": {"arquivo": "tenso/Tensa B.mp3", "titulo": "Tensa B", "volume_db": -26.0},
        "anterior": None,
        "pedido": None,
    }


def test_get_musica_sem_musica(ambiente):
    construir, _ = ambiente
    cliente, *_ = construir(musica=None)
    assert cliente.get(_url("")).json()["atual"] is None


def test_get_musica_fora_da_biblioteca_usa_nome_do_arquivo(ambiente, tmp_path):
    construir, _ = ambiente
    cliente, *_ = construir(musica=Musica(str(tmp_path / "solta" / "x.mp3"), -24.0, "Solta", ""))
    assert cliente.get(_url("")).json()["atual"] == {"arquivo": "x.mp3", "titulo": "Solta", "volume_db": -24.0}


def test_get_musica_anterior_do_ultimo_pronto(ambiente):
    construir, _ = ambiente
    anterior = Musica("C:/x/tenso/Tensa B.mp3", -26.0, "Tensa B", "c")
    cliente, *_ = construir(lambda *a: Resultado("pronto", "ok", [], anterior))
    pedido = cliente.post(_url(""), json=CORPO).json()
    dados = _esperar(lambda: (d := cliente.get(_url("")).json())["anterior"] and d)
    assert dados["anterior"] == {"arquivo": "Tensa B.mp3", "titulo": "Tensa B", "volume_db": -26.0}
    assert dados["pedido"]["id"] == pedido["id"]  # sem ativo, o último pedido do corte


def test_previa_ok(ambiente):
    construir, _ = ambiente
    recebido = {}

    def gerador(receita, video, musica, inicio, saida, **kw):
        recebido.update(receita=receita, video=video, musica=musica, inicio=inicio, saida=saida)
        Path(saida).write_bytes(b"m4a-falso")
        return saida

    cliente, *_ = construir(gerar_previa=gerador)
    resposta = cliente.post(_url("/previa"), json={**CORPO, "inicio": 4.5})
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "audio/mp4"
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.content == b"m4a-falso"
    assert recebido["inicio"] == 4.5 and recebido["musica"].volume_db == -22
    assert recebido["musica"].arquivo.replace("\\", "/").endswith("musicas/tenso/Tensa C.mp3")
    assert recebido["saida"].name == "previa-musica.m4a" and recebido["saida"].parent.name == "trabalho"
    assert recebido["video"].name == "ep.mp4"


def test_previa_422(ambiente):
    construir, _ = ambiente

    def gerador(*a, **kw):
        raise ErroMidia("ffmpeg falhou")

    cliente, *_ = construir(gerar_previa=gerador)
    resposta = cliente.post(_url("/previa"), json={**CORPO, "inicio": 0})
    assert resposta.status_code == 422
    assert resposta.json() == {"detail": "Não consegui gerar a prévia: ffmpeg falhou"}


def test_previa_valida_faixa_e_volume(ambiente):
    construir, _ = ambiente
    cliente, *_ = construir(gerar_previa=lambda *a, **kw: pytest.fail("não devia gerar"))
    assert cliente.post(_url("/previa"), json={"arquivo": "x/y.mp3", "volume_db": -22, "inicio": 0}).status_code == 422
    assert cliente.post(_url("/previa"), json={**CORPO, "volume_db": -5, "inicio": 0}).status_code == 422


def test_previa_sem_episodio_json_422(ambiente):
    construir, _ = ambiente
    cliente, pasta, *_ = construir(gerar_previa=lambda *a, **kw: pytest.fail("não devia gerar"))
    (pasta / "episodio.json").unlink()
    resposta = cliente.post(_url("/previa"), json={**CORPO, "inicio": 0})
    assert resposta.status_code == 422
    assert resposta.json()["detail"].startswith("Não consegui gerar a prévia: ")


def test_rotas_novas_pedem_login_na_rede(tmp_path):
    musicas = tmp_path / "musicas"
    musicas.mkdir()
    cofre, relogio = CofreFalso(), Relogio()
    codigo = gerar_codigo(cofre)
    (tmp_path / "cortes").mkdir()
    fila = Fila(lambda *a: Resultado("pronto", "ok", [], None))
    try:
        cliente = TestClient(criar_app(
            tmp_path / "cortes", rede=True, cofre=cofre, relogio=relogio, fila=fila, pasta_musicas=musicas
        ))
        pedidas = [
            ("get", "/api/episodios/x/musicas"), ("get", "/api/musicas/leve/a.mp3"),
            ("get", "/api/episodios/x/cortes/1/musica"), ("post", "/api/episodios/x/cortes/1/musica"),
            ("post", "/api/episodios/x/cortes/1/musica/previa"),
            ("get", "/api/tarefas"), ("get", "/api/tarefas/abc"),
        ]
        for metodo, caminho in pedidas:
            assert getattr(cliente, metodo)(caminho).status_code == 401, caminho
        assert _entrar(cliente, codigo).status_code == 204
        assert cliente.get("/api/tarefas").status_code == 200
    finally:
        fila.parar(2)


def _estragar_catalogo(musicas):
    (musicas / "catalogo.json").write_text("{não é json", "utf-8")


def test_previa_com_faixas_vazias_422(ambiente):
    from esteira import render

    construir, _ = ambiente
    cliente, pasta, *_ = construir(gerar_previa=render.gerar_previa)
    montagem = next(pasta.glob("*/trabalho/montagem.json"))
    dados = json.loads(montagem.read_text("utf-8"))
    dados["faixas"] = []
    montagem.write_text(json.dumps(dados), "utf-8")
    resposta = cliente.post(_url("/previa"), json={**CORPO, "inicio": 0})
    assert resposta.status_code == 422
    assert resposta.json()["detail"].startswith("Não consegui gerar a prévia: ")


def test_previa_com_catalogo_ilegivel_422(ambiente):
    construir, musicas = ambiente
    cliente, *_ = construir(gerar_previa=lambda *a, **kw: pytest.fail("não devia gerar"))
    _estragar_catalogo(musicas)
    resposta = cliente.post(_url("/previa"), json={**CORPO, "inicio": 0})
    assert resposta.status_code == 422
    assert resposta.json()["detail"].startswith("Não consegui gerar a prévia: ")


def test_lista_com_catalogo_ilegivel_200_com_aviso(ambiente):
    construir, musicas = ambiente
    cliente, *_ = construir()
    _estragar_catalogo(musicas)
    resposta = cliente.get("/api/episodios/" + quote(NOME) + "/musicas")
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["do_episodio"] == []
    assert all(v == [] for v in dados["biblioteca"].values())
    assert "catalogo.json ilegível" in dados["avisos"]


def test_post_musica_com_catalogo_ilegivel_422(ambiente):
    construir, musicas = ambiente
    cliente, _, fila, _ = construir()
    _estragar_catalogo(musicas)
    resposta = cliente.post(_url(""), json=CORPO)
    assert resposta.status_code == 422
    assert resposta.json() == {"detail": "Catálogo de músicas ilegível."}
    assert fila.pedidos() == []
