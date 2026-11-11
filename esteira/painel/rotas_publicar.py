"""Agendar a publicação e editar a legenda pelo painel.

Publicar: o painel mostra o mesmo resumo do `publicar agendar` e só confirma o resumo exato que o dono viu (a
marca do texto vai junto com o clique). Assim o sim é dado por uma pessoa na tela, e não por quem tem um
terminal (o Claude Code, por exemplo). O envio roda na fila do painel.

Legenda: troca o texto das telas no montagem.json; o dono monta o corte de novo pelo botão de montar.
"""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from esteira.caminhos import garantir_escrita
from esteira.cortar import TRABALHO
from esteira.legenda import escrever_srt
from esteira.painel.fila import PedidoAtivo
from esteira.painel.rotas import _TRAVA_GRAVACAO, _pasta_do_corte
from esteira.painel.troca_musica import Resultado
from esteira.publicar.agendar import FUSO, REDES, ErroAgendar, confirmar, preparar_pedido, resumo
from esteira.publicar.config import ler_modos
from esteira.publicar.fila import Ocupado, achar, gravar_fila, ler_fila, trava
from esteira.publicar.rodar import TRAVA
from esteira.publicar.post import versao_dos_bytes
from esteira.receita import NOME_ARQUIVO, ler_receita

roteador = APIRouter(prefix="/api")

RESUMO_MUDOU = "O corte, o texto ou a data mudaram desde o resumo. Veja o resumo de novo antes de confirmar."
MAX_CARACTERES_LINHA = 40
MAX_LINHAS = 2


class PedidoResumo(BaseModel):
    data: str
    redes: list[str]


class ConfirmarPublicacao(PedidoResumo):
    marca: str
    confirmado: Literal[True]


class Cancelar(BaseModel):
    redes: list[str]
    confirmado: Literal[True]


def _marca(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _agora(requisicao: Request) -> datetime:
    agora = getattr(requisicao.app.state, "agora_publicar", None)
    return agora() if agora else datetime.now(FUSO)


def _modos(requisicao: Request) -> dict:
    ler = getattr(requisicao.app.state, "modos_publicar", None)
    try:
        return ler() if ler else ler_modos()
    except (OSError, ValueError) as erro:
        raise HTTPException(422, f"publicacao.json ilegível: {erro}") from erro


def _preparar(requisicao: Request, ep: str, n: int, corpo: PedidoResumo):
    pasta, _ = _pasta_do_corte(requisicao, ep, n)
    redes = [r for r in corpo.redes if r]
    if not redes:
        raise HTTPException(422, "Escolha ao menos uma rede.")
    try:
        pedido = preparar_pedido(pasta, n, corpo.data.replace("T", " "), redes, _agora(requisicao))
    except ErroAgendar as erro:
        return pasta, None, JSONResponse({"detail": "Não dá para agendar ainda.", "problemas": str(erro).splitlines()},
                                         status_code=422)
    return pasta, pedido, None


def _itens(pasta: Path, n: int) -> list[dict]:
    try:
        itens = ler_fila(pasta)
    except (OSError, ValueError, KeyError, TypeError):
        return []
    campos = ("rede", "data", "estado", "link", "erro", "tentativas")
    return [{c: getattr(i, c) for c in campos} for i in itens if i.numero == n and i.estado != "cancelado"]


@roteador.get("/episodios/{ep}/cortes/{n}/publicacao")
def publicacao(ep: str, n: int, requisicao: Request) -> dict:
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    return {"itens": _itens(pasta, n), "redes": bloco.redes, "data": bloco.data, "modos": _modos(requisicao)}


@roteador.post("/episodios/{ep}/cortes/{n}/publicacao/resumo")
def resumo_da_publicacao(ep: str, n: int, corpo: PedidoResumo, requisicao: Request):
    _, pedido, recusa = _preparar(requisicao, ep, n, corpo)
    if recusa:
        return recusa
    texto = resumo(pedido, _modos(requisicao))
    return {"resumo": texto, "marca": _marca(texto), "ia": pedido.ia}


def _redes_api(requisicao: Request) -> dict:
    fabrica = getattr(requisicao.app.state, "redes_publicar", None)
    if fabrica is not None:
        return fabrica()
    from esteira.publicar.rodar import _redes_reais

    return _redes_reais()


@roteador.post("/episodios/{ep}/cortes/{n}/publicacao", status_code=202)
def confirmar_publicacao(ep: str, n: int, corpo: ConfirmarPublicacao, requisicao: Request):
    pasta, pedido, recusa = _preparar(requisicao, ep, n, corpo)
    if recusa:
        return recusa
    modos = _modos(requisicao)
    if _marca(resumo(pedido, modos)) != corpo.marca:
        return JSONResponse({"detail": RESUMO_MUDOU}, status_code=409)
    estado = requisicao.app.state

    def executar(progresso):
        progresso("Agendando…")
        try:
            with trava(getattr(estado, "trava_publicar", TRAVA)):
                itens = confirmar(pedido, modos, _redes_api(requisicao), base=estado.cortes)
        except Ocupado:
            return Resultado("erro", "outra publicação em andamento; tente em alguns minutos", [], None)
        falhas = [f"{i.rede}: {i.erro}" for i in itens if i.estado == "erro"]
        partes = [f"{i.rede}: {i.estado}" for i in itens]
        if falhas:
            return Resultado("erro", "; ".join(falhas), partes, None)
        return Resultado("pronto", "; ".join(partes), [], None)

    try:
        tarefa = estado.fila.pedir_tarefa("publicar", pasta, [n], executar)
    except PedidoAtivo:
        return JSONResponse({"detail": "Já há um agendamento deste corte em andamento."}, status_code=409)
    return tarefa.como_dict()


@roteador.post("/episodios/{ep}/cortes/{n}/publicacao/cancelar")
def cancelar_publicacao(ep: str, n: int, corpo: Cancelar, requisicao: Request) -> dict:
    """Cancela o que ainda está agendado. O que já saiu, o dono apaga no app da rede."""
    pasta, _ = _pasta_do_corte(requisicao, ep, n)
    estado = requisicao.app.state
    mensagens = []
    try:
        with trava(getattr(estado, "trava_publicar", TRAVA)):
            itens = ler_fila(pasta)
            for rede in corpo.redes:
                if rede not in REDES:
                    continue
                item = achar(itens, n, rede)
                if item is None:
                    continue
                if item.estado == "agendado":
                    item.estado = "cancelado"
                    mensagens.append(f"{rede}: cancelado")
                else:
                    mensagens.append(f"{rede}: está em {item.estado}; confira no app")
            gravar_fila(pasta, itens, base=estado.cortes)
    except Ocupado:
        raise HTTPException(409, "Outra publicação em andamento; tente em alguns minutos.") from None
    return {"mensagens": mensagens, "itens": _itens(pasta, n)}


# --- legenda ---------------------------------------------------------------------------------------------


class Tela(BaseModel):
    indice: int
    linhas: list[str]


class GravarLegenda(BaseModel):
    versao: str
    telas: list[Tela]


def _montagem(destino: Path) -> Path:
    return destino / TRABALHO / NOME_ARQUIVO


@roteador.get("/episodios/{ep}/cortes/{n}/legenda")
def legenda(ep: str, n: int, requisicao: Request) -> dict:
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    destino = pasta / bloco.pasta
    try:
        bruto = _montagem(destino).read_bytes()
        receita = ler_receita(destino / TRABALHO)
    except FileNotFoundError:
        raise HTTPException(404, "Corte sem montagem.json: rode preparar.") from None
    except (OSError, ValueError, KeyError, TypeError) as erro:
        raise HTTPException(422, f"montagem.json ilegível: {erro}") from erro
    telas = [{"indice": i, "inicio": c.inicio, "fim": c.fim, "linhas": c.linhas} for i, c in enumerate(receita.legenda)]
    return {"versao": versao_dos_bytes(bruto), "telas": telas, "max_caracteres": MAX_CARACTERES_LINHA}


def _conferir_tela(tela: Tela) -> list[str]:
    linhas = [" ".join(l.split()) for l in tela.linhas]
    if not linhas or not any(linhas):
        raise HTTPException(422, f"Tela {tela.indice + 1}: não pode ficar vazia.")
    if len(linhas) > MAX_LINHAS:
        raise HTTPException(422, f"Tela {tela.indice + 1}: no máximo {MAX_LINHAS} linhas.")
    for linha in linhas:
        if len(linha) > MAX_CARACTERES_LINHA:
            raise HTTPException(422, f"Tela {tela.indice + 1}: linha com mais de {MAX_CARACTERES_LINHA} caracteres.")
    return [l for l in linhas if l]


@roteador.put("/episodios/{ep}/cortes/{n}/legenda")
def gravar_legenda(ep: str, n: int, corpo: GravarLegenda, requisicao: Request):
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    destino = pasta / bloco.pasta
    estado = requisicao.app.state
    if estado.fila.montando_corte(pasta.name, n):
        return JSONResponse({"detail": "O corte está sendo montado. Espere terminar."}, status_code=409)
    with _TRAVA_GRAVACAO:
        arquivo = garantir_escrita(_montagem(destino), base_extra=estado.cortes)
        try:
            bruto = arquivo.read_bytes()
            receita = ler_receita(destino / TRABALHO)
        except (OSError, ValueError, KeyError, TypeError) as erro:
            raise HTTPException(422, f"montagem.json ilegível: {erro}") from erro
        if versao_dos_bytes(bruto) != corpo.versao:
            return JSONResponse({"detail": "A legenda mudou desde que você abriu. Recarregue."}, status_code=409)
        for tela in corpo.telas:
            if not 0 <= tela.indice < len(receita.legenda):
                raise HTTPException(422, f"Tela {tela.indice + 1} não existe.")
            linhas = _conferir_tela(tela)
            cue = receita.legenda[tela.indice]
            if linhas != cue.linhas:
                palavras_antes = sum(len(l.split()) for l in cue.linhas)
                cue.linhas = linhas
                if sum(len(l.split()) for l in linhas) != palavras_antes:
                    cue.palavras = None  # o tempo por palavra não vale mais: essa tela volta ao estilo fixo
        from esteira.receita import gravar_receita

        gravar_receita(destino / TRABALHO, receita)
        escrever_srt(receita.legenda, garantir_escrita(destino / TRABALHO / "legenda.srt", base_extra=estado.cortes))
        nova = versao_dos_bytes(arquivo.read_bytes())
    return {"versao": nova, "remontar": True}
