import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from esteira.caminhos import EscritaProibida
from esteira.painel.acesso import COOKIE, Cofre, Porteiro
from esteira.painel.leitura import CaminhoProibido, NaoEncontrado
from esteira.painel.rotas import roteador


def criar_app(
    cortes: Path,
    rede: bool = False,
    cofre: Cofre | None = None,
    relogio: Callable[[], float] = time.time,
    agora: Callable[[], datetime] = datetime.now,
    estatico: Path | None = None,
    hosts: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="Painel de revisão", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cortes = Path(cortes)
    app.state.agora = agora
    app.state.relogio = relogio
    app.state.cofre = cofre
    app.state.rede = rede
    app.state.porteiro = None
    if rede:
        if cofre is None:
            raise ValueError("O painel na rede precisa de um cofre para o código de acesso.")
        app.state.porteiro = Porteiro(cofre, relogio)

        @app.middleware("http")
        async def _exigir_sessao(requisicao: Request, seguir):
            caminho = requisicao.scope["path"]  # o mesmo caminho que o roteador usa
            if caminho.startswith("/api/") and caminho != "/api/entrar":
                if not app.state.porteiro.sessao_valida(requisicao.cookies.get(COOKIE)):
                    return JSONResponse({"detail": "Entre com o código de acesso."}, status_code=401)
            return await seguir(requisicao)

    @app.exception_handler(CaminhoProibido)
    async def _proibido(_requisicao, erro: CaminhoProibido) -> JSONResponse:
        return JSONResponse({"detail": str(erro)}, status_code=403)

    @app.exception_handler(NaoEncontrado)
    async def _nao_encontrado(_requisicao, erro: NaoEncontrado) -> JSONResponse:
        return JSONResponse({"detail": str(erro)}, status_code=404)

    @app.exception_handler(EscritaProibida)
    async def _escrita_proibida(_requisicao, erro: EscritaProibida) -> JSONResponse:
        return JSONResponse({"detail": f"Escrita não permitida: {erro}"}, status_code=403)

    app.include_router(roteador)

    if estatico is not None and (Path(estatico) / "index.html").is_file():
        _servir_estatico(app, Path(estatico).resolve())

    if hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)  # contra DNS rebinding
    return app


def _servir_estatico(app: FastAPI, estatico: Path) -> None:
    if (estatico / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=estatico / "assets"), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    async def _pagina(caminho: str):
        if caminho == "api" or caminho.startswith("api/"):
            return JSONResponse({"detail": "Não encontrado."}, status_code=404)
        try:
            candidato = (estatico / caminho).resolve()
            if caminho and candidato.is_file() and candidato.is_relative_to(estatico):
                return FileResponse(candidato)
        except (ValueError, OSError):  # por exemplo, %00 no caminho
            pass
        return FileResponse(estatico / "index.html")
