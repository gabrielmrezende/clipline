"""A fila do painel vista pelo navegador: a lista, um pedido, cancelar e os eventos em tempo real (SSE).

Os eventos mandam a lista inteira (até 50 pedidos) sempre que ela muda, e um comentário de vida a cada 15 s. Cada
conexão dura no máximo alguns minutos: o navegador reabre sozinho (`retry`) e a sessão é conferida de novo pelo
mesmo porteiro das outras rotas. Ao fechar o painel (Ctrl+C), as conexões terminam na hora.
"""

import asyncio
import json
import signal
import threading
import time
from collections.abc import AsyncIterator, Callable
from typing import Literal

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from esteira.painel.fila import Fila, NaoCancela
from esteira.painel.leitura import NaoEncontrado

roteador = APIRouter(prefix="/api")

INTERVALO_VIDA = 15.0  # segundos entre os comentários que mantêm a conexão aberta
DURACAO_MAXIMA = 300.0  # depois disso a conexão fecha e o navegador reabre, passando de novo pelo porteiro
REABRIR_MS = 2000  # quanto o navegador espera para reabrir a conexão
SINAIS = ("SIGINT", "SIGTERM", "SIGBREAK")  # SIGBREAK: Ctrl+Break no Windows


class Cancelamento(BaseModel):
    """Corpo JSON obrigatório: uma página de outra origem não cancela nada sem passar pelo preflight."""

    confirmado: Literal[True]


@roteador.get("/tarefas")
def tarefas(requisicao: Request) -> list[dict]:
    return [p.como_dict() for p in requisicao.app.state.fila.pedidos()]


@roteador.get("/tarefas/eventos")
async def eventos(requisicao: Request) -> StreamingResponse:
    estado = requisicao.app.state
    fluxo = fluxo_de_eventos(
        estado.fila,
        fechando=estado.fechando.is_set,
        intervalo=getattr(estado, "eventos_intervalo", INTERVALO_VIDA),
        duracao=getattr(estado, "eventos_duracao", DURACAO_MAXIMA),
    )
    return StreamingResponse(fluxo, media_type="text/event-stream", headers={"Cache-Control": "no-store"})


@roteador.get("/tarefas/{id}")
def tarefa(id: str, requisicao: Request) -> dict:
    pedido = requisicao.app.state.fila.pedido(id)
    if pedido is None:
        raise NaoEncontrado("tarefa não encontrada")
    return pedido.como_dict()


@roteador.post("/tarefas/{id}/cancelar")
def cancelar(id: str, corpo: Cancelamento, requisicao: Request):
    """Na fila: sai sem rodar. Interrompido: descartado. Montando: só a IA, que para antes da próxima imagem."""
    try:
        pedido = requisicao.app.state.fila.cancelar(id)
    except KeyError:
        raise NaoEncontrado("tarefa não encontrada") from None
    except NaoCancela as erro:
        return JSONResponse({"detail": str(erro)}, status_code=409)
    return pedido.como_dict()


def _evento(lista: str) -> str:
    return f"event: tarefas\ndata: {lista}\n\n"


async def fluxo_de_eventos(
    fila: Fila,
    fechando: Callable[[], bool],
    intervalo: float = INTERVALO_VIDA,
    duracao: float = DURACAO_MAXIMA,
    relogio: Callable[[], float] = time.monotonic,
) -> AsyncIterator[str]:
    """A lista da fila agora e a cada mudança; um comentário de vida a cada `intervalo`; fim depois de `duracao`
    ou quando o painel fecha. Nada de thread por conexão: a fila acorda o laço de eventos quando muda."""
    laco = asyncio.get_running_loop()
    mudou = asyncio.Event()

    def avisar() -> None:
        try:
            laco.call_soon_threadsafe(mudou.set)
        except RuntimeError:  # o laço já fechou
            pass

    parar_de_ouvir = fila.ouvir(avisar)
    fim = relogio() + duracao
    enviado = None
    try:
        yield f"retry: {REABRIR_MS}\n\n"
        while not fechando():
            mudou.clear()
            lista = json.dumps([p.como_dict() for p in fila.pedidos()], ensure_ascii=False)
            if lista != enviado:
                enviado = lista
                yield _evento(lista)
            restante = fim - relogio()
            if restante <= 0:
                return
            try:
                await asyncio.wait_for(mudou.wait(), timeout=min(intervalo, restante))
            except TimeoutError:
                if not fechando():
                    yield ": vivo\n\n"
    finally:
        parar_de_ouvir()


def fechar_eventos(app: FastAPI) -> None:
    """Termina as conexões de eventos abertas (o painel está fechando)."""
    app.state.fechando.set()
    acordar = getattr(app.state.fila, "acordar", None)
    if acordar is not None:
        acordar()


def avisar_ao_fechar(aviso: Callable[[], None]) -> Callable[[], None]:
    """Chama `aviso` antes do tratador de Ctrl+C que já está instalado (o do uvicorn) e devolve o que desfaz isso.

    Sem isto, o uvicorn espera as conexões de eventos terminarem antes de fechar ("Waiting for connections to
    close") e o Ctrl+C parece travado. Só na thread principal, que é a única que recebe sinais; fora dela (os
    testes, por exemplo), não faz nada. O uvicorn devolve os tratadores originais ao sair."""
    if threading.current_thread() is not threading.main_thread():
        return lambda: None
    instalados: dict[int, tuple[object, Callable]] = {}
    for nome in SINAIS:
        numero = getattr(signal, nome, None)
        if numero is None:
            continue
        anterior = signal.getsignal(numero)
        if anterior is None:  # tratador instalado fora do Python: não dá para encadear
            continue

        def tratar(sinal: int, quadro, anterior=anterior) -> None:
            aviso()
            if callable(anterior):
                anterior(sinal, quadro)
            else:  # SIG_DFL ou SIG_IGN: devolve e repete o sinal
                signal.signal(sinal, anterior)
                signal.raise_signal(sinal)

        try:
            signal.signal(numero, tratar)
        except (OSError, ValueError):
            continue
        instalados[numero] = (anterior, tratar)

    def desfazer() -> None:
        for numero, (anterior, tratar) in instalados.items():
            if signal.getsignal(numero) is tratar:
                signal.signal(numero, anterior)

    return desfazer
