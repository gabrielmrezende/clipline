import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from esteira.painel.leitura import CaminhoProibido, NaoEncontrado
from esteira.painel.rotas import roteador


def criar_app(
    cortes: Path,
    rede: bool = False,
    cofre: object | None = None,
    relogio: Callable[[], float] = time.time,
    agora: Callable[[], datetime] = datetime.now,
    estatico: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Painel de revisão", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cortes = Path(cortes)
    app.state.agora = agora
    app.state.relogio = relogio
    app.state.cofre = cofre
    app.state.rede = rede

    @app.exception_handler(CaminhoProibido)
    async def _proibido(_requisicao, erro: CaminhoProibido) -> JSONResponse:
        return JSONResponse({"detail": str(erro)}, status_code=403)

    @app.exception_handler(NaoEncontrado)
    async def _nao_encontrado(_requisicao, erro: NaoEncontrado) -> JSONResponse:
        return JSONResponse({"detail": str(erro)}, status_code=404)

    app.include_router(roteador)
    return app
