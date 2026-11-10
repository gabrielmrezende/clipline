import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from esteira.cortar import CORTE_MP4, IMAGENS_SUGERIDAS, VIDEO_FINAL, ler_aprovados
from esteira.painel.acesso import COOKIE, DURACAO_SESSAO, CodigoErrado, Travado
from esteira.painel.leitura import (
    NaoEncontrado,
    _credito,
    avisos_post,
    bloco_json,
    listar_episodios,
    mensagem_post,
    resolver_arquivo,
    resolver_episodio,
    resumo_episodio,
)
from esteira.publicar.post import (
    ConflitoPost,
    ErroPost,
    Textos,
    conferir_textos,
    gravar_textos,
    ler_post_completo,
    tem_quebra_de_linha,
)
from esteira.revisao import BlocoRevisao, dados_revisao

roteador = APIRouter(prefix="/api")
_TRAVA_GRAVACAO = threading.Lock()

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
    fila = requisicao.app.state.fila
    return {
        "resumo": resumo,
        "cortes": [
            {**_bloco_com_avisos(pasta, b), "montando": fila.montando_corte(pasta.name, b.numero)}
            for b in _blocos(pasta)
        ],
    }


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
    return {"texto": _ler_texto(pasta / "candidatos.md")}


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


class CamposPost(BaseModel):
    youtube_titulo: str
    youtube_descricao: str
    instagram: str
    tiktok: str


class ConferirPost(BaseModel):
    campos: CamposPost


class GravarPost(BaseModel):
    versao: str
    campos: CamposPost


def _avisos_de_formato(campos: CamposPost) -> list[str]:
    avisos = []
    if tem_quebra_de_linha(campos.youtube_titulo):
        avisos.append("O título do YouTube não pode ter quebra de linha.")
    textos = (campos.youtube_titulo, campos.youtube_descricao, campos.instagram, campos.tiktok)
    if any(linha.startswith("## ") for texto in textos for linha in texto.splitlines()):
        avisos.append("Nenhum texto pode ter linha começando com '## '.")
    return avisos


def _avisos_do_post(campos: CamposPost, pasta_corte: Path, bloco: BlocoRevisao) -> list[str]:
    textos = Textos(**campos.model_dump())
    return _avisos_de_formato(campos) + conferir_textos(
        textos, _credito(pasta_corte), set(bloco.redes)
    )


@roteador.get("/episodios/{ep}/cortes/{n}/post")
def post_do_corte(ep: str, n: int, requisicao: Request) -> dict:
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    pasta_corte = pasta / bloco.pasta
    try:
        lido = ler_post_completo(pasta_corte / "post.md")  # campos e versão dos mesmos bytes
    except (ErroPost, OSError, UnicodeDecodeError) as erro:
        return {
            "campos": None, "somente_leitura": None, "credito": None,
            "redes": None, "versao": None, "avisos": None, "erro": mensagem_post(erro),
        }
    credito = _credito(pasta_corte)
    return {
        "campos": lido.textos.__dict__,
        "somente_leitura": lido.somente_leitura,
        "credito": credito,
        "redes": bloco.redes,
        "versao": lido.versao,
        "avisos": conferir_textos(lido.textos, credito, set(bloco.redes)),
        "erro": None,
    }


@roteador.post("/episodios/{ep}/cortes/{n}/post/conferir")
def conferir_post(ep: str, n: int, corpo: ConferirPost, requisicao: Request) -> dict:
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    return {"avisos": _avisos_do_post(corpo.campos, pasta / bloco.pasta, bloco)}


@roteador.put("/episodios/{ep}/cortes/{n}/post")
def gravar_post(ep: str, n: int, corpo: GravarPost, requisicao: Request):
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    pasta_corte = pasta / bloco.pasta
    caminho = pasta_corte / "post.md"
    if not caminho.is_file():
        raise HTTPException(404, "post.md não encontrado.")
    formato = _avisos_de_formato(corpo.campos)
    if formato:
        raise HTTPException(422, formato[0])
    try:
        with _TRAVA_GRAVACAO:  # dois PUTs não passam juntos pela versão nem dividem o .tmp
            nova = gravar_textos(
                caminho,
                Textos(**corpo.campos.model_dump()),
                base=requisicao.app.state.cortes,
                versao=corpo.versao,
            )
    except ConflitoPost as conflito:
        return JSONResponse(
            {"detail": str(conflito), "versao_atual": conflito.versao_atual}, status_code=409
        )
    except (ErroPost, OSError, UnicodeDecodeError) as erro:
        raise HTTPException(422, mensagem_post(erro)) from erro
    return {"versao": nova, "avisos": _avisos_do_post(corpo.campos, pasta_corte, bloco)}


class Entrar(BaseModel):
    codigo: str


@roteador.post("/entrar")
def entrar(corpo: Entrar, requisicao: Request) -> Response:
    porteiro = requisicao.app.state.porteiro
    if porteiro is None:
        return Response(status_code=204)
    try:
        valor = porteiro.entrar(corpo.codigo)
    except Travado as erro:
        return JSONResponse({"detail": str(erro)}, status_code=429)
    except CodigoErrado:
        return JSONResponse({"detail": "Código errado."}, status_code=401)
    resposta = Response(status_code=204)
    resposta.set_cookie(
        COOKIE, valor, httponly=True, samesite="strict", max_age=DURACAO_SESSAO, path="/"
    )
    return resposta
