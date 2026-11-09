import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from esteira.caminhos import EscritaProibida, garantir_escrita
from esteira.cortar import TRABALHO
from esteira.musica import CLIMAS_VALIDOS, Faixa, ler_catalogo, ler_musicas_do_episodio
from esteira.painel.fila import PedidoAtivo
from esteira.painel.leitura import NaoEncontrado, resolver_episodio
from esteira.painel.rotas import _pasta_do_corte
from esteira.receita import VOLUME_MAXIMO, VOLUME_MINIMO, Musica, ler_receita

roteador = APIRouter(prefix="/api")

PREVIA = "previa-musica.m4a"


class PedidoMusica(BaseModel):
    arquivo: str
    volume_db: float


class PedidoPrevia(PedidoMusica):
    inicio: float = Field(default=0.0, ge=0)


class CatalogoIlegivel(Exception):
    pass


def _catalogo(requisicao: Request) -> list[Faixa]:
    try:
        return ler_catalogo(requisicao.app.state.pasta_musicas)
    except (OSError, ValueError, TypeError) as erro:
        raise CatalogoIlegivel("Catálogo de músicas ilegível.") from erro


def _faixa_valida(requisicao: Request, arquivo: str, volume_db: float) -> Faixa:
    try:
        catalogo = _catalogo(requisicao)
    except CatalogoIlegivel as erro:
        raise HTTPException(422, str(erro)) from erro
    faixa = next((f for f in catalogo if f.arquivo == arquivo), None)
    if faixa is None:
        raise HTTPException(422, "Faixa fora do catálogo.")
    if not VOLUME_MINIMO <= volume_db <= VOLUME_MAXIMO:
        raise HTTPException(422, f"Volume fora de {VOLUME_MINIMO:g} a {VOLUME_MAXIMO:g} dB.")
    return faixa


@roteador.get("/episodios/{ep}/musicas")
def musicas_do_episodio(ep: str, requisicao: Request) -> dict:
    pasta = resolver_episodio(requisicao.app.state.cortes, ep)
    try:
        catalogo = _catalogo(requisicao)
        ilegivel = []
    except CatalogoIlegivel:
        catalogo, ilegivel = [], ["catalogo.json ilegível"]
    faixas, avisos = ler_musicas_do_episodio(pasta, catalogo)
    avisos = ilegivel + avisos
    biblioteca: dict[str, list[dict]] = {clima: [] for clima in CLIMAS_VALIDOS}
    for f in catalogo:
        biblioteca.setdefault(f.clima, []).append(
            {"arquivo": f.arquivo, "titulo": f.titulo, "duracao": f.duracao}
        )
    return {
        "do_episodio": [
            {"arquivo": f.arquivo, "titulo": f.titulo, "clima": f.clima, "duracao": f.duracao, "motivo": motivo}
            for f, motivo in faixas
        ],
        "biblioteca": biblioteca,
        "avisos": avisos,
    }


@roteador.get("/musicas/{clima}/{arquivo}")
def faixa(clima: str, arquivo: str, requisicao: Request) -> FileResponse:
    try:
        achada = any(f.arquivo == f"{clima}/{arquivo}" for f in _catalogo(requisicao))
    except CatalogoIlegivel:
        achada = False
    if not achada:
        raise NaoEncontrado("faixa não encontrada")
    caminho = Path(requisicao.app.state.pasta_musicas) / clima / arquivo
    if not caminho.is_file():
        raise NaoEncontrado("faixa não encontrada")
    return FileResponse(caminho, media_type="audio/mpeg")


def _nome_na_biblioteca(arquivo: str, pasta_musicas: Path) -> str:
    caminho = Path(arquivo)
    for base, alvo in ((Path(pasta_musicas), caminho), (Path(pasta_musicas).resolve(), caminho.resolve())):
        try:
            return alvo.relative_to(base).as_posix()
        except ValueError:
            continue
    return caminho.name


def _atual(pasta_corte: Path, pasta_musicas: Path) -> dict | None:
    try:
        musica = ler_receita(pasta_corte / TRABALHO).musica
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if musica is None:
        return None
    return {
        "arquivo": _nome_na_biblioteca(musica.arquivo, pasta_musicas),
        "titulo": musica.titulo or Path(musica.arquivo).name,
        "volume_db": musica.volume_db,
    }


@roteador.get("/episodios/{ep}/cortes/{n}/musica")
def musica_do_corte(ep: str, n: int, requisicao: Request) -> dict:
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    fila = requisicao.app.state.fila
    pronto = fila.ultimo_pronto(pasta.name, n)
    pedido = fila.ativo(pasta.name, n) or next(
        (p for p in fila.pedidos() if p.episodio == pasta.name and p.numero == n), None
    )
    return {
        "atual": _atual(pasta / bloco.pasta, requisicao.app.state.pasta_musicas),
        "anterior": pronto.anterior if pronto else None,
        "pedido": pedido.como_dict() if pedido else None,
    }


@roteador.post("/episodios/{ep}/cortes/{n}/musica", status_code=202)
def trocar(ep: str, n: int, corpo: PedidoMusica, requisicao: Request):
    pasta, _ = _pasta_do_corte(requisicao, ep, n)
    escolhida = _faixa_valida(requisicao, corpo.arquivo, corpo.volume_db)
    try:
        pedido = requisicao.app.state.fila.pedir(pasta, n, escolhida, corpo.volume_db)
    except PedidoAtivo:
        return JSONResponse({"detail": "Este corte já está sendo montado."}, status_code=409)
    return pedido.como_dict()


@roteador.post("/episodios/{ep}/cortes/{n}/musica/previa")
def previa(ep: str, n: int, corpo: PedidoPrevia, requisicao: Request):
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    try:
        escolhida = _faixa_valida(requisicao, corpo.arquivo, corpo.volume_db)
        trabalho = pasta / bloco.pasta / TRABALHO
        saida = garantir_escrita(trabalho / PREVIA, base_extra=requisicao.app.state.cortes)
        musica = Musica(
            str(Path(requisicao.app.state.pasta_musicas) / escolhida.arquivo),
            corpo.volume_db, escolhida.titulo, escolhida.credito,
        )
        video = Path(json.loads((pasta / "episodio.json").read_text("utf-8"))["video"])
        receita = ler_receita(trabalho)
        requisicao.app.state.gerar_previa(
            receita, video, musica, corpo.inicio, saida, duracao_musica=escolhida.duracao
        )
    except HTTPException as erro:
        if erro.status_code == 422 and erro.detail == "Catálogo de músicas ilegível.":
            return _falha_previa(erro.detail)
        raise
    except EscritaProibida:
        raise  # 403, pelo tratador do app
    except Exception as erro:  # nunca 500: qualquer falha vira 422 com o motivo
        return _falha_previa(str(erro) or type(erro).__name__)
    return FileResponse(saida, media_type="audio/mp4", headers={"Cache-Control": "no-store"})


def _falha_previa(motivo: str) -> JSONResponse:
    return JSONResponse({"detail": f"Não consegui gerar a prévia: {motivo}"}, status_code=422)


@roteador.get("/tarefas")
def tarefas(requisicao: Request) -> list[dict]:
    return [p.como_dict() for p in requisicao.app.state.fila.pedidos()]


@roteador.get("/tarefas/{id}")
def tarefa(id: str, requisicao: Request) -> dict:
    pedido = requisicao.app.state.fila.pedido(id)
    if pedido is None:
        raise NaoEncontrado("tarefa não encontrada")
    return pedido.como_dict()
