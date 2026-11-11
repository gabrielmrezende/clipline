import asyncio
import functools
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from esteira import render, wikimedia
from esteira import rede as modulo_rede
from esteira.caminhos import CONTEXTO, MUSICAS, EscritaProibida
from esteira.imagens_ia import chaves
from esteira.imagens_ia import config as config_imagens
from esteira.imagens_ia.provedor import Provedor
from esteira.montar import montar_episodio
from esteira.pedidos import pessoas_do_glossario
from esteira.painel.acesso import COOKIE, Cofre, Porteiro
from esteira.painel.leitura import CaminhoProibido, NaoEncontrado
from esteira.painel.fila import Fila
from esteira.painel.rotas import _TRAVA_GRAVACAO, roteador
from esteira.painel.rotas_imagens import roteador as roteador_imagens
from esteira.painel.rotas_musica import roteador as roteador_musica
from esteira.painel.rotas_publicar import roteador as roteador_publicar
from esteira.painel.troca_musica import recuperar_trocas_interrompidas, trocar_musica

ESPERA_AO_DESLIGAR = 120  # segundos esperando a montagem atual quando o painel fecha


def _montar_real(pasta: Path, numero: int) -> str:
    return montar_episodio(pasta, numeros={numero}, forcar=True).get(numero, f"erro: corte {numero} não montado")


def _pessoas_do_glossario() -> list[str]:
    """Lido a cada pedido. Ausente ou ilegível levanta (OSError, UnicodeDecodeError): o painel recusa
    aprovar e gerar em vez de aceitar qualquer nome (a regra de pessoa real não falha aberta)."""
    return pessoas_do_glossario(CONTEXTO / "glossario.md")


def criar_app(
    cortes: Path,
    rede: bool = False,
    cofre: Cofre | None = None,
    relogio: Callable[[], float] = time.time,
    agora: Callable[[], datetime] = datetime.now,
    estatico: Path | None = None,
    hosts: list[str] | None = None,
    fila: Fila | None = None,
    gerar_previa: Callable = render.gerar_previa,
    pasta_musicas: Path = MUSICAS,
    montar: Callable[[Path, int], str] = _montar_real,
    buscar_candidatas: Callable[[str], list[wikimedia.Candidata]] = wikimedia.buscar_candidatas,
    pessoas: Callable[[], list[str]] = _pessoas_do_glossario,
    consultar: wikimedia.Consulta = wikimedia.consultar,
    medir: Callable[[str], int | None] = wikimedia.tamanho,
    baixar: Callable[[str, Path], None] = modulo_rede.baixar_url,
    provedores: dict[str, Callable[[dict], Provedor]] | None = None,
    tem_chave: Callable[[str], bool] = chaves.tem_chave,
    config_ia: Path = config_imagens.ARQUIVO,
) -> FastAPI:
    for corte in recuperar_trocas_interrompidas(cortes):
        print(f"Troca de música interrompida desfeita: {corte}")

    @asynccontextmanager
    async def _vida(app: FastAPI):
        yield
        if getattr(app.state.fila, "montando", lambda: False)():
            print("Esperando a montagem em andamento terminar (até 2 min)...")
        await asyncio.to_thread(app.state.fila.parar, ESPERA_AO_DESLIGAR)

    app = FastAPI(title="Painel de revisão", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_vida)
    app.state.cortes = Path(cortes)
    app.state.agora = agora
    app.state.relogio = relogio
    app.state.cofre = cofre
    app.state.rede = rede
    app.state.porteiro = None
    app.state.pasta_musicas = Path(pasta_musicas)
    app.state.gerar_previa = gerar_previa
    app.state.buscar_candidatas = buscar_candidatas
    app.state.pessoas = pessoas
    app.state.consultar = consultar
    app.state.medir = medir
    app.state.baixar = baixar
    app.state.provedores = provedores
    app.state.tem_chave = tem_chave
    app.state.config_ia = Path(config_ia)
    app.state.montar = montar
    if fila is None:
        fila = Fila(executar=functools.partial(
            trocar_musica, montar=montar, base=app.state.cortes,
            pasta_musicas=app.state.pasta_musicas, trava=_TRAVA_GRAVACAO,
        ))
    app.state.fila = fila
    if rede:
        if cofre is None:
            raise ValueError("O painel na rede precisa de um cofre para o código de acesso.")
        app.state.porteiro = Porteiro(cofre, relogio)

        @app.middleware("http")
        async def _exigir_sessao(requisicao: Request, seguir):
            caminho = requisicao.scope["path"]  # o mesmo caminho que o roteador usa
            if caminho.startswith("/api/") and caminho not in ("/api/entrar", "/api/sair"):
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
    app.include_router(roteador_musica)
    app.include_router(roteador_imagens)
    app.include_router(roteador_publicar)

    if estatico is not None and (Path(estatico) / "index.html").is_file():
        _servir_estatico(app, Path(estatico).resolve())

    @app.middleware("http")
    async def _mesma_origem(requisicao: Request, seguir):
        motivo = recusa_de_origem(requisicao.scope["path"], requisicao.method, requisicao.headers)
        if motivo:
            return JSONResponse({"detail": motivo}, status_code=403)
        resposta = await seguir(requisicao)
        for nome, valor in CABECALHOS_DE_SEGURANCA.items():
            resposta.headers.setdefault(nome, valor)
        return resposta

    if hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)  # contra DNS rebinding
    return app


CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://upload.wikimedia.org",
    "media-src 'self' blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])
CABECALHOS_DE_SEGURANCA = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
OUTRA_ORIGEM = "Pedido vindo de outra página recusado. Abra o painel pelo endereço dele."


def recusa_de_origem(caminho: str, metodo: str, cabecalhos) -> str | None:
    """Defesa explícita contra CSRF e contra GETs com efeito disparados por outra página (um <img>, por exemplo).

    Antes, a proteção dependia de o FastAPI só aceitar JSON com Content-Type: application/json, o que obriga o
    navegador a um preflight. Isso continua valendo; isto acrescenta uma regra que não depende do framework.
    Pedidos sem esses cabeçalhos (curl, testes, scripts locais) passam: não vêm de um navegador enganado."""
    if not caminho.startswith("/api/"):
        return None
    sitio = cabecalhos.get("sec-fetch-site")
    if sitio is not None and sitio not in ("same-origin", "none"):
        return OUTRA_ORIGEM
    origem = cabecalhos.get("origin")
    if origem is not None and metodo not in ("GET", "HEAD", "OPTIONS"):
        host = cabecalhos.get("host", "")
        if origem not in (f"http://{host}", f"https://{host}"):
            return OUTRA_ORIGEM
    return None


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
