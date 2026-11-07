from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from esteira.cortar import CORTE_MP4, IMAGENS_SUGERIDAS, VIDEO_FINAL, ler_aprovados
from esteira.painel.leitura import (
    NaoEncontrado,
    avisos_post,
    bloco_json,
    listar_episodios,
    resolver_arquivo,
    resolver_episodio,
    resumo_episodio,
)
from esteira.revisao import BlocoRevisao, dados_revisao

roteador = APIRouter(prefix="/api")

EXT_VIDEO = {".mp4", ".mov"}
EXT_IMAGEM = {".jpg", ".jpeg", ".png"}
TIPOS = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _ler_texto(arquivo: Path) -> str:
    try:
        return arquivo.read_text("utf-8") if arquivo.is_file() else ""
    except (OSError, UnicodeDecodeError):
        return ""


def _blocos(pasta: Path) -> list[BlocoRevisao]:
    try:
        return dados_revisao(pasta)
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _bloco_do_corte(pasta: Path, numero: int) -> BlocoRevisao:
    try:
        aprovados = {c.numero for c in ler_aprovados(pasta)}
    except (OSError, ValueError, KeyError, TypeError) as erro:
        raise NaoEncontrado(f"episódio ilegível: {erro}") from erro
    if numero not in aprovados:
        raise NaoEncontrado(f"corte {numero} não está nos aprovados")
    for bloco in _blocos(pasta):
        if bloco.numero == numero:
            return bloco
    raise NaoEncontrado(f"corte {numero} ilegível")


def _bloco_com_avisos(pasta: Path, bloco: BlocoRevisao) -> dict:
    return bloco_json(bloco, avisos_post(pasta / bloco.pasta, bloco.redes))


def _pasta_do_corte(requisicao: Request, ep: str, n: int) -> tuple[Path, BlocoRevisao]:
    pasta = resolver_episodio(requisicao.app.state.cortes, ep)
    return pasta, _bloco_do_corte(pasta, n)


def _arquivo(pasta: Path, nome: str, extensoes: set[str]) -> FileResponse:
    arquivo = resolver_arquivo(pasta, nome, extensoes)
    return FileResponse(arquivo, media_type=TIPOS[arquivo.suffix.lower()])


@roteador.get("/episodios")
def episodios(requisicao: Request) -> list[dict]:
    return listar_episodios(requisicao.app.state.cortes, requisicao.app.state.agora())


@roteador.get("/episodios/{ep}")
def episodio(ep: str, requisicao: Request) -> dict:
    pasta = resolver_episodio(requisicao.app.state.cortes, ep)
    resumo = resumo_episodio(pasta, requisicao.app.state.agora())
    return {"resumo": resumo, "cortes": [_bloco_com_avisos(pasta, b) for b in _blocos(pasta)]}


@roteador.get("/episodios/{ep}/calendario")
def calendario(ep: str, requisicao: Request) -> dict:
    pasta = resolver_episodio(requisicao.app.state.cortes, ep)
    itens = [
        {"numero": b.numero, "titulo": b.titulo, "data": b.data, "redes": b.redes}
        for b in _blocos(pasta)
    ]
    itens.sort(key=lambda i: (not i["data"], i["data"], i["numero"]))
    return {"itens": itens, "texto": _ler_texto(pasta / "calendario.md")}


@roteador.get("/episodios/{ep}/descartados")
def descartados(ep: str, requisicao: Request) -> dict:
    pasta = resolver_episodio(requisicao.app.state.cortes, ep)
    return {"texto": _ler_texto(pasta / "descartados.md")}


@roteador.get("/episodios/{ep}/cortes/{n}")
def corte(ep: str, n: int, requisicao: Request) -> dict:
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    imagens = pasta / bloco.pasta / IMAGENS_SUGERIDAS
    nomes = []
    if imagens.is_dir():
        nomes = sorted(
            (a.name for a in imagens.iterdir() if a.is_file() and a.suffix.lower() in EXT_IMAGEM),
            key=str.lower,
        )
    guia = imagens / "guia.md"
    return {
        "bloco": _bloco_com_avisos(pasta, bloco),
        "guia": _ler_texto(guia) if guia.is_file() else None,
        "imagens": nomes,
    }


@roteador.get("/episodios/{ep}/cortes/{n}/video")
def video(ep: str, n: int, requisicao: Request) -> FileResponse:
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    return _arquivo(pasta / bloco.pasta, CORTE_MP4, EXT_VIDEO)


@roteador.get("/episodios/{ep}/cortes/{n}/video-final/{arquivo}")
def video_final(ep: str, n: int, arquivo: str, requisicao: Request) -> FileResponse:
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    return _arquivo(pasta / bloco.pasta / VIDEO_FINAL, arquivo, EXT_VIDEO)


@roteador.get("/episodios/{ep}/cortes/{n}/imagens/{arquivo}")
def imagem(ep: str, n: int, arquivo: str, requisicao: Request) -> FileResponse:
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    return _arquivo(pasta / bloco.pasta / IMAGENS_SUGERIDAS, arquivo, EXT_IMAGEM)
