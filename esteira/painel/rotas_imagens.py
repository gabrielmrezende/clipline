import os
import re
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictInt

from esteira.caminhos import garantir_escrita
from esteira.cortar import IMAGENS_SUGERIDAS, TRABALHO
from esteira.fluxo_imagens import _arquivos, _ler_sugeridas, chave_momento, ler_ia
from esteira.painel.leitura import NaoEncontrado
from esteira.painel.rotas import _TRAVA_GRAVACAO, _pasta_do_corte
from esteira.pedidos import ARQUIVO, MAXIMO_ESCOLHAS, Momento, _pessoa_citada, pedidos_dos_bytes, texto_dos_pedidos
from esteira.publicar.post import versao_dos_bytes

roteador = APIRouter(prefix="/api")

LARGURA_MAXIMA_MINIATURA = 640
FOTOS_EM_ANDAMENTO = "Espere o download das fotos terminar."
TIPOS_TROCAVEIS = ("foto", "ia")
_MINIATURA = re.compile(r"/(\d+)px-([^/]*)$")


class AlteracaoMomento(BaseModel):
    versao: str
    tipo: str | None = None
    escolhas: list[StrictInt] | None = None
    prompt: str | None = None
    aprovado: bool | None = None
    descartar: bool | None = None


class PedidoBusca(BaseModel):
    busca: str


def _miniatura(url: str) -> str:
    achado = _MINIATURA.search(url)
    if achado and int(achado.group(1)) > LARGURA_MAXIMA_MINIATURA:
        return _MINIATURA.sub(f"/{LARGURA_MAXIMA_MINIATURA}px-\\2", url)
    return url


def _candidata(c: dict) -> dict:
    campos = ("titulo", "miniatura", "autor", "licenca", "pagina", "largura", "altura")
    saida = {campo: c.get(campo) for campo in campos}
    saida["miniatura"] = _miniatura(str(c.get("miniatura") or ""))
    return saida


def _fotos_prontas(m: Momento, imagens: Path, sugeridas: set[str]) -> list[str]:
    nomes = _arquivos(m)
    if m.tipo == "foto":
        return [
            nome for k, nome in enumerate(nomes, 1)
            if nome in sugeridas and (imagens / nome).is_file()
            and k <= len(m.resumidas) and m.resumidas[k - 1] == m.escolhas[k - 1]
        ]
    return [nome for nome in nomes if nome in sugeridas and (imagens / nome).is_file()]


def _ia_do_momento(m: Momento, imagens: Path, ia: list[dict]) -> list[dict]:
    chave = chave_momento(m)
    itens = [
        i for i in ia
        if i.get("momento") == chave and isinstance(i.get("arquivo"), str)
        and Path(i["arquivo"]).name == i["arquivo"] and (imagens / i["arquivo"]).is_file()
    ]
    itens.sort(key=lambda i: i["versao"] if isinstance(i.get("versao"), int) else 0)
    return [
        {"arquivo": i["arquivo"], "versao": i.get("versao"), "provedor": i.get("provedor", ""), "data": i.get("data", "")}
        for i in itens
    ]


def _json_do_momento(m: Momento, destino: Path, pessoas: list[str]) -> dict:
    imagens = destino / IMAGENS_SUGERIDAS
    sugeridas = set(_ler_sugeridas(destino / TRABALHO))
    return {
        "chave": chave_momento(m),
        "inicio": m.inicio, "fim": m.fim, "fala": m.fala, "tipo": m.tipo, "nome": m.nome,
        "busca": m.busca, "titulo": m.titulo, "veiculo": m.veiculo, "data": m.data,
        "prompt": m.prompt, "aprovado": m.aprovado, "descartar": m.descartar, "motivo": m.motivo,
        "candidatas": [_candidata(c) for c in m.candidatas],
        "escolhas": list(m.escolhas),
        "fotos_prontas": _fotos_prontas(m, imagens, sugeridas),
        "ia": _ia_do_momento(m, imagens, ler_ia(destino / TRABALHO)),
        "pessoa_citada": _pessoa_citada(m.prompt, pessoas) if m.prompt else None,
    }


def _pessoas(requisicao: Request) -> list[str]:
    return requisicao.app.state.pessoas()


def _contexto(requisicao: Request, ep: str, n: int) -> tuple[str, Path, Path]:
    """(nome do episódio, pasta do corte, caminho do pedidos.json)."""
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    destino = pasta / bloco.pasta
    return pasta.name, destino, destino / TRABALHO / ARQUIVO


def _ler(caminho: Path) -> tuple[str, list[Momento]] | None:
    """(versão, momentos) dos mesmos bytes; None se não existe; 422 se ilegível."""
    try:
        conteudo = caminho.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as erro:
        raise HTTPException(422, f"pedidos.json ilegível: {erro}") from erro
    try:
        return versao_dos_bytes(conteudo), pedidos_dos_bytes(conteudo)
    except (ValueError, KeyError, TypeError, AttributeError) as erro:  # inclui JSON e UTF-8 inválidos
        raise HTTPException(422, f"pedidos.json ilegível: {erro}") from erro


def _achar(momentos: list[Momento], chave: str) -> Momento:
    """O primeiro momento com a chave (se duas entradas repetem a chave, vale a primeira)."""
    for m in momentos:
        if chave_momento(m) == chave:
            return m
    raise NaoEncontrado("momento não encontrado")


def _gravar(requisicao: Request, caminho: Path, momentos: list[Momento]) -> str:
    destino = garantir_escrita(caminho, base_extra=requisicao.app.state.cortes)
    conteudo = texto_dos_pedidos(momentos).encode("utf-8")
    temporario = destino.with_name(destino.name + ".tmp")
    temporario.write_bytes(conteudo)
    os.replace(temporario, destino)
    return versao_dos_bytes(conteudo)


def _fotos_ativas(requisicao: Request, episodio: str, n: int) -> bool:
    return requisicao.app.state.fila.ativo(episodio, n, "fotos") is not None


def _bloqueio_das_fotos() -> JSONResponse:
    return JSONResponse({"detail": FOTOS_EM_ANDAMENTO}, status_code=409)


def _resposta(requisicao: Request, destino: Path, m: Momento, versao: str) -> dict:
    return {"momento": _json_do_momento(m, destino, _pessoas(requisicao)), "versao": versao}


@roteador.get("/episodios/{ep}/cortes/{n}/momentos")
def momentos(ep: str, n: int, requisicao: Request) -> dict:
    _, destino, caminho = _contexto(requisicao, ep, n)
    lido = _ler(caminho)
    if lido is None:
        return {"versao": "", "momentos": []}
    versao, lista = lido
    pessoas = _pessoas(requisicao)
    return {"versao": versao, "momentos": [_json_do_momento(m, destino, pessoas) for m in lista]}


def _aplicar_tipo(m: Momento, tipo: str) -> None:
    if tipo not in TIPOS_TROCAVEIS:
        raise HTTPException(422, "Tipo inválido.")
    if m.tipo == "noticia":
        raise HTTPException(422, "Notícia não troca de tipo pelo painel.")
    if tipo == m.tipo:
        return
    m.tipo = tipo
    m.aprovado = False
    if tipo == "foto" and not m.busca.strip():
        m.busca = m.nome


def _validar_escolhas(m: Momento, escolhas: list[int]) -> None:
    if len(escolhas) > MAXIMO_ESCOLHAS:
        raise HTTPException(422, f"No máximo {MAXIMO_ESCOLHAS} escolhas.")
    if any(not 1 <= e <= len(m.candidatas) for e in escolhas):
        raise HTTPException(422, "Escolha fora da faixa.")
    if len(set(escolhas)) != len(escolhas):
        raise HTTPException(422, "Escolha repetida.")


def _aprovar(m: Momento, pessoas: list[str]) -> None:
    if m.tipo != "ia":
        raise HTTPException(422, "Só momentos de IA têm aprovação.")
    if not m.prompt.strip():
        raise HTTPException(422, "Escreva o prompt antes de aprovar.")
    pessoa = _pessoa_citada(m.prompt, pessoas)
    if pessoa:
        raise HTTPException(422, f"Cita pessoa real ({pessoa}): não pode gerar")
    m.aprovado = True


def _aplicar(m: Momento, corpo: AlteracaoMomento, pessoas: list[str]) -> None:
    if corpo.tipo is not None:
        _aplicar_tipo(m, corpo.tipo)
    if corpo.escolhas is not None:
        _validar_escolhas(m, corpo.escolhas)
        m.escolhas = list(corpo.escolhas)
    if corpo.prompt is not None and corpo.prompt != m.prompt:
        m.prompt = corpo.prompt
        m.aprovado = False
    if corpo.aprovado is True:
        _aprovar(m, pessoas)
    elif corpo.aprovado is False:
        m.aprovado = False
    if corpo.descartar is not None:
        m.descartar = corpo.descartar


@roteador.put("/episodios/{ep}/cortes/{n}/momentos/{chave}")
def alterar_momento(ep: str, n: int, chave: str, corpo: AlteracaoMomento, requisicao: Request):
    episodio, destino, caminho = _contexto(requisicao, ep, n)
    pessoas = _pessoas(requisicao)
    with _TRAVA_GRAVACAO:  # o trabalhador de fotos e o Claude regravam o mesmo arquivo
        if _fotos_ativas(requisicao, episodio, n):
            return _bloqueio_das_fotos()
        lido = _ler(caminho)
        if lido is None:
            raise NaoEncontrado("pedidos.json não encontrado")
        versao, lista = lido
        if corpo.versao != versao:
            return JSONResponse(
                {"detail": "O pedidos.json mudou desde que você abriu.", "versao_atual": versao}, status_code=409
            )
        m = _achar(lista, chave)
        _aplicar(m, corpo, pessoas)
        nova = _gravar(requisicao, caminho, lista)
    return _resposta(requisicao, destino, m, nova)


@roteador.post("/episodios/{ep}/cortes/{n}/momentos/{chave}/buscar")
def buscar(ep: str, n: int, chave: str, corpo: PedidoBusca, requisicao: Request):
    episodio, destino, caminho = _contexto(requisicao, ep, n)
    busca = corpo.busca.strip()
    if not busca:
        raise HTTPException(422, "Escreva o que buscar.")
    if _fotos_ativas(requisicao, episodio, n):
        return _bloqueio_das_fotos()
    lido = _ler(caminho)
    if lido is None:
        raise NaoEncontrado("pedidos.json não encontrado")
    if _achar(lido[1], chave).tipo != "foto":
        raise HTTPException(422, "Só momentos de foto buscam no Wikimedia.")
    try:
        candidatas = requisicao.app.state.buscar_candidatas(busca)  # rede: fora da trava
    except (OSError, ValueError) as erro:
        raise HTTPException(422, f"Não consegui buscar no Wikimedia: {erro}") from erro
    with _TRAVA_GRAVACAO:
        if _fotos_ativas(requisicao, episodio, n):
            return _bloqueio_das_fotos()
        lido = _ler(caminho)  # releitura: o arquivo pode ter mudado durante a busca
        if lido is None:
            raise NaoEncontrado("pedidos.json não encontrado")
        _, lista = lido
        m = _achar(lista, chave)
        m.busca = busca
        m.candidatas = [asdict(c) for c in candidatas]
        m.escolhas, m.url, m.bytes, m.resumidas, m.motivo = [], [], [], [], ""
        nova = _gravar(requisicao, caminho, lista)
    return _resposta(requisicao, destino, m, nova)
