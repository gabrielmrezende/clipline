"""Rotas da fila: lista, cancelar, eventos em tempo real (SSE) e o histórico que sobrevive ao reinício."""

import json
import queue
import signal
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from esteira.modelos import Corte
from esteira.painel.acesso import gerar_codigo
from esteira.painel.app import CSP, criar_app
from esteira.painel.fila import ARQUIVO, Fila
from esteira.painel.rotas_tarefas import avisar_ao_fechar, fechar_eventos
from esteira.painel.troca_musica import Resultado
from tests.auxiliares_painel import criar_episodio
from tests.test_painel_acesso import CofreFalso, Relogio, _entrar

NOME = "Entre Assuntos 03 - Arthur Cerqueira (teste capcut)"
CONFIRMADO = {"confirmado": True}
LIMITE = 5.0


def esperar(condicao, limite=LIMITE):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.01)
    return condicao()


def tarefa(liberar: threading.Event | None = None, iniciou: threading.Event | None = None):
    def executar(progresso):
        if iniciou:
            iniciou.set()
        if liberar:
            assert liberar.wait(LIMITE)
        return Resultado("pronto", "ok", [], None)

    return executar


@pytest.fixture
def filas():
    criadas: list[Fila] = []
    yield criadas
    for fila in criadas:
        fila.parar(2)


def _app(cortes: Path, filas: list[Fila], **kw):
    app = criar_app(cortes, **kw)
    filas.append(app.state.fila)
    app.state.eventos_intervalo = 0.05
    app.state.eventos_duracao = LIMITE
    return app


# --- histórico no disco --------------------------------------------------------------------------------------------


def test_painel_grava_a_fila_na_pasta_de_cortes_e_recupera_ao_abrir(tmp_path, filas):
    cortes = tmp_path / "cortes"
    pasta = criar_episodio(cortes, NOME, [Corte(1, "Um", 10, 20, "tenso")], {1})
    liberar, iniciou = threading.Event(), threading.Event()

    def montar(pasta_episodio, numero):
        iniciou.set()
        assert liberar.wait(LIMITE)
        return "ok"

    cliente = TestClient(_app(cortes, filas, montar=montar))
    try:
        pedido = cliente.post(f"/api/episodios/{quote(NOME)}/cortes/1/montar", json=CONFIRMADO).json()
        assert iniciou.wait(LIMITE)
        gravado = json.loads((cortes / ARQUIVO).read_text("utf-8"))
        assert [(p["id"], p["estado"], p["tipo"]) for p in gravado["pedidos"]] == [(pedido["id"], "montando", "montar")]
        # o painel caiu aqui (sem fechar a fila): o próximo abre com o pedido interrompido
        reaberto = TestClient(_app(cortes, filas, montar=lambda *a: "ok"))
        lista = reaberto.get("/api/tarefas").json()
        assert [(p["id"], p["estado"], p["mensagem"]) for p in lista] == [
            (pedido["id"], "interrompido", "o painel foi fechado no meio deste pedido")
        ]
        assert reaberto.get(f"/api/episodios/{quote(NOME)}").json()["cortes"][0]["montando"] is False
    finally:
        liberar.set()
    assert pasta.is_dir()


# --- cancelar --------------------------------------------------------------------------------------------------------


def test_cancelar_pela_rota(tmp_path, filas):
    liberar, iniciou = threading.Event(), threading.Event()
    app = _app(tmp_path, filas)
    cliente = TestClient(app)
    fila = app.state.fila
    try:
        rodando = fila.pedir_tarefa("fotos", tmp_path / "ep1", [1], tarefa(liberar, iniciou))
        assert iniciou.wait(LIMITE)
        esperando = fila.pedir_tarefa("ia", tmp_path / "ep1", [2], tarefa())
        r = cliente.post(f"/api/tarefas/{esperando.id}/cancelar", json=CONFIRMADO)
        assert r.status_code == 200
        assert (r.json()["estado"], r.json()["mensagem"]) == ("cancelado", "cancelado antes de começar")
        r = cliente.post(f"/api/tarefas/{rodando.id}/cancelar", json=CONFIRMADO)
        assert r.status_code == 409
        assert r.json()["detail"] == "Este pedido já começou e não para no meio. Espere terminar."
        assert cliente.post(f"/api/tarefas/{esperando.id}/cancelar", json=CONFIRMADO).status_code == 409
        assert cliente.post("/api/tarefas/naoexiste/cancelar", json=CONFIRMADO).status_code == 404
        assert cliente.post(f"/api/tarefas/{esperando.id}/cancelar").status_code == 422  # sem o corpo JSON
        outra_origem = {"Origin": "http://malicioso.example"}
        r = cliente.post(f"/api/tarefas/{esperando.id}/cancelar", json=CONFIRMADO, headers=outra_origem)
        assert r.status_code == 403
    finally:
        liberar.set()
    assert esperar(lambda: fila.pedido(rodando.id).estado == "pronto")
    assert fila.pedido(esperando.id).estado == "cancelado"


def test_rotas_da_fila_pedem_login_na_rede(tmp_path, filas):
    cofre, relogio = CofreFalso(), Relogio()
    codigo = gerar_codigo(cofre)
    app = _app(tmp_path, filas, rede=True, cofre=cofre, relogio=relogio)
    cliente = TestClient(app)
    assert cliente.get("/api/tarefas/eventos").status_code == 401
    assert cliente.post("/api/tarefas/abc/cancelar", json=CONFIRMADO).status_code == 401
    assert _entrar(cliente, codigo).status_code == 204
    fechar_eventos(app)  # a conexão abre e termina logo
    with cliente.stream("GET", "/api/tarefas/eventos") as r:
        assert r.status_code == 200
        assert r.read().decode() == "retry: 2000\n\n"


# --- eventos (SSE) ---------------------------------------------------------------------------------------------------


class Leitor:
    """Lê o fluxo numa thread: o teste espera cada evento com prazo, sem travar se ele não vier."""

    def __init__(self, resposta):
        self.blocos: queue.Queue = queue.Queue()
        self.terminou = threading.Event()
        self._thread = threading.Thread(target=self._ler, args=(resposta,), daemon=True)
        self._thread.start()

    def _ler(self, resposta):
        linhas: list[str] = []
        try:
            for linha in resposta.iter_lines():
                if linha:
                    linhas.append(linha)
                elif linhas:
                    self.blocos.put(linhas)
                    linhas = []
        except Exception:  # a conexão fechada pelo teste
            pass
        finally:
            self.terminou.set()

    def proximo_evento(self) -> list[dict]:
        fim = time.monotonic() + LIMITE
        while time.monotonic() < fim:
            try:
                bloco = self.blocos.get(timeout=0.1)
            except queue.Empty:
                continue
            if bloco[0] == "event: tarefas":
                return json.loads(bloco[1].removeprefix("data: "))
        raise AssertionError("nenhum evento chegou")

    def blocos_ate_agora(self) -> list[list[str]]:
        saida = []
        while not self.blocos.empty():
            saida.append(self.blocos.get())
        return saida


@pytest.fixture
def eventos(tmp_path, filas):
    app = _app(tmp_path, filas)
    cliente = TestClient(app)
    with cliente.stream("GET", "/api/tarefas/eventos", headers={"Sec-Fetch-Site": "same-origin"}) as resposta:
        yield app, resposta, Leitor(resposta)
        fechar_eventos(app)


def test_eventos_cabecalhos_e_csp(eventos):
    _, resposta, _ = eventos
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/event-stream")
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.headers["content-security-policy"] == CSP
    assert "connect-src 'self'" in CSP  # o EventSource do painel abre na mesma origem


def test_eventos_mandam_a_lista_agora_e_a_cada_mudanca(eventos):
    app, _, leitor = eventos
    assert leitor.proximo_evento() == []
    liberar, iniciou = threading.Event(), threading.Event()
    fila = app.state.fila
    try:
        p = fila.pedir_tarefa("ia", Path("x/ep1"), [1], tarefa(liberar, iniciou))
        estados = []
        while not estados or estados[-1] != "montando":
            lista = leitor.proximo_evento()
            assert [t["id"] for t in lista] == [p.id]
            estados.append(lista[0]["estado"])
    finally:
        liberar.set()
    while leitor.proximo_evento()[0]["estado"] != "pronto":
        pass
    assert esperar(lambda: any(b == [": vivo"] for b in leitor.blocos_ate_agora()))  # o comentário de vida


def test_eventos_nao_repetem_a_mesma_lista(eventos):
    app, _, leitor = eventos
    assert leitor.proximo_evento() == []
    app.state.fila.acordar()  # acorda sem mudança: nada novo para mandar
    time.sleep(0.2)
    assert all(b == [": vivo"] for b in leitor.blocos_ate_agora())


def test_eventos_terminam_quando_o_painel_fecha(eventos):
    app, _, leitor = eventos
    assert leitor.proximo_evento() == []
    fechar_eventos(app)
    assert leitor.terminou.wait(LIMITE)
    assert app.state.fila._ouvintes == []  # a conexão deixou de ouvir a fila


def test_eventos_terminam_depois_da_duracao_maxima(tmp_path, filas):
    app = _app(tmp_path, filas)
    app.state.eventos_duracao = 0.2
    with TestClient(app).stream("GET", "/api/tarefas/eventos") as resposta:
        corpo = resposta.read().decode()  # termina sozinho: o navegador reabre depois de `retry`
    assert corpo.startswith("retry: 2000\n\nevent: tarefas\ndata: []\n\n")


def test_eventos_de_outra_pagina_sao_recusados(tmp_path, filas):
    cliente = TestClient(_app(tmp_path, filas))
    assert cliente.get("/api/tarefas/eventos", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_fechar_o_painel_pelo_ciclo_de_vida_encerra_os_eventos(tmp_path, filas):
    app = _app(tmp_path, filas)
    with TestClient(app):
        assert not app.state.fechando.is_set()
    assert app.state.fechando.is_set()


# --- Ctrl+C ----------------------------------------------------------------------------------------------------------


@pytest.mark.skipif(threading.current_thread() is not threading.main_thread(), reason="sinais só na thread principal")
def test_ctrl_c_avisa_antes_do_tratador_do_uvicorn():
    original = signal.getsignal(signal.SIGINT)
    chamadas = []
    tratador_do_uvicorn = lambda sinal, quadro: chamadas.append(("uvicorn", sinal))  # noqa: E731
    signal.signal(signal.SIGINT, tratador_do_uvicorn)
    try:
        desfazer = avisar_ao_fechar(lambda: chamadas.append(("aviso", None)))
        signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
        assert chamadas == [("aviso", None), ("uvicorn", signal.SIGINT)]
        desfazer()
        assert signal.getsignal(signal.SIGINT) is tratador_do_uvicorn
    finally:
        signal.signal(signal.SIGINT, original)


def test_fora_da_thread_principal_nao_mexe_nos_sinais():
    resultado = []
    antes = signal.getsignal(signal.SIGINT)
    thread = threading.Thread(target=lambda: resultado.append(avisar_ao_fechar(lambda: None)))
    thread.start()
    thread.join(LIMITE)
    resultado[0]()
    assert signal.getsignal(signal.SIGINT) is antes
