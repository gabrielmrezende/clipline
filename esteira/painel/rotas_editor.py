"""Editor do trecho do corte pela transcrição: ler as palavras ao redor, conferir o que muda e trocar início e fim.

A troca roda na fila do painel (tipo "trecho"): grava o aprovados.json e refaz o corte (ver troca_trecho).
"""

import functools
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from esteira import config, falantes
from esteira import vozes as modulo_vozes
from esteira.caminhos import CONTEXTO
from esteira.contrato import ErroContrato
from esteira.cortar import CORTE_MP4, TRABALHO, ler_aprovados, pasta_do_corte, preparar_episodio
from esteira.modelos import Corte, Palavra
from esteira.painel.fila import PedidoAtivo
from esteira.painel.rotas import _TRAVA_GRAVACAO, _pasta_do_corte
from esteira.painel.troca_trecho import alinhar, pode_iniciar, pode_terminar, prever, trocar_trecho
from esteira.pessoas import ler_pessoas
from esteira.publicar.post import versao_dos_bytes
from esteira.receita import NOME_ARQUIVO
from esteira.transcrever import carregar_glossario, ler_palavras
from esteira.validar import validar_trecho

roteador = APIRouter(prefix="/api")

TIPO = "trecho"
JANELA_PADRAO = 30.0  # segundos de transcrição antes e depois do corte
JANELA_MAXIMA = 600.0
MONTANDO = "Este corte já está sendo montado. Espere terminar."
APROVADOS_MUDOU = "O aprovados.json mudou desde que você abriu o trecho. Recarregue a página."
SEM_MUDANCA = "O trecho novo é igual ao de agora."
FIM_ANTES = "O fim precisa vir depois do início."
TEMPO_INVALIDO = "Início e fim precisam ser números de segundos."


def _preparar_real(pasta: Path, numero: int, nomes: list[str], pasta_musicas: Path) -> str:
    return preparar_episodio(pasta, {numero}, forcar=True, nomes=nomes, pasta_musicas=pasta_musicas).get(
        numero, f"erro: corte {numero} não preparado"
    )


def _nomes_do_glossario() -> list[str]:
    return carregar_glossario(CONTEXTO / "glossario.md")


@dataclass
class Dependencias:
    """O que a troca chama de fora. Os testes põem falsos em `app.state.editor_trecho`."""

    preparar: Callable[[Path, int, list[str], Path], str] = _preparar_real
    nomes: Callable[[], list[str]] = _nomes_do_glossario


def _dependencias(requisicao: Request) -> Dependencias:
    return getattr(requisicao.app.state, "editor_trecho", None) or Dependencias()


@dataclass
class _Contexto:
    pasta: Path
    corte: Corte
    cortes: list[Corte]
    versao: str
    palavras: list[Palavra]
    duracao: float


def _contexto(requisicao: Request, ep: str, n: int) -> _Contexto:
    pasta, _ = _pasta_do_corte(requisicao, ep, n)  # 404 se o corte não está nos aprovados
    try:
        bruto = (pasta / "aprovados.json").read_bytes()
        cortes = ler_aprovados(pasta)
    except (OSError, ErroContrato) as erro:
        raise HTTPException(422, f"aprovados.json ilegível: {erro}") from erro
    try:
        palavras = ler_palavras(pasta)
    except FileNotFoundError:
        raise HTTPException(404, "Transcrição não encontrada (transcricao/palavras.json).") from None
    except (OSError, ValueError, KeyError, TypeError) as erro:
        raise HTTPException(422, f"palavras.json ilegível: {erro}") from erro
    try:
        duracao = float(json.loads((pasta / "episodio.json").read_text("utf-8"))["duracao"])
    except (OSError, ValueError, KeyError, TypeError) as erro:
        raise HTTPException(422, f"episodio.json ilegível: {erro}") from erro
    corte = next(c for c in cortes if c.numero == n)
    return _Contexto(pasta, corte, cortes, versao_dos_bytes(bruto), palavras, duracao)


def _limites() -> tuple[float, float]:
    try:
        atual = config.atual()
    except config.ErroConfig as erro:
        raise HTTPException(422, str(erro)) from erro
    return atual.duracao_minima, atual.duracao_maxima


def _janela(valor: float) -> float:
    if not math.isfinite(valor):
        return JANELA_PADRAO
    return min(max(valor, 0.0), JANELA_MAXIMA)


def _ligacao_e_nomes(pasta: Path) -> tuple[dict, dict]:
    try:
        lidas = ler_pessoas(pasta)
    except (OSError, ValueError, KeyError, TypeError):
        return {}, {}
    if lidas is None:
        return {}, {}
    ligacao, _, nomes = lidas
    return dict(ligacao or {}), dict(nomes or {})


def _palavras_com_falantes(ctx: _Contexto, de: float, ate: float) -> list[dict]:
    """As palavras do intervalo com quem fala, como o `esteira trecho` faz."""
    try:
        trechos = modulo_vozes.ler_vozes(ctx.pasta)
    except (modulo_vozes.ErroVozes, OSError, ValueError, KeyError, TypeError):
        trechos = []
    ligacao, nomes = _ligacao_e_nomes(ctx.pasta)
    intervalo = falantes.palavras_do_intervalo(ctx.palavras, de, ate)
    rotulos = falantes.rotular([p for _, p in intervalo], trechos) if trechos else [None] * len(intervalo)
    return [
        {
            "texto": p.texto,
            "inicio": round(p.inicio, 3),
            "fim": round(p.fim, 3),
            "voz": voz,
            "falante": falantes.nome_da_voz(voz, ligacao, nomes) if trechos else None,
            "pode_iniciar": pode_iniciar(ctx.palavras, i),
            "pode_terminar": pode_terminar(ctx.palavras, i),
        }
        for (i, p), voz in zip(intervalo, rotulos)
    ]


def _ultimo_pedido(requisicao: Request, episodio: str, n: int) -> dict | None:
    fila = requisicao.app.state.fila
    pedido = fila.ativo(episodio, n, TIPO) or next(
        (p for p in fila.pedidos() if p.episodio == episodio and p.numero == n and p.tipo == TIPO), None
    )
    return pedido.como_dict() if pedido else None


@roteador.get("/episodios/{ep}/cortes/{n}/trecho")
def ler_trecho(
    ep: str, n: int, requisicao: Request, antes: float = Query(JANELA_PADRAO), depois: float = Query(JANELA_PADRAO)
) -> dict:
    ctx = _contexto(requisicao, ep, n)
    minima, maxima = _limites()
    corte = ctx.corte
    de = max(0.0, corte.inicio - _janela(antes))
    ate = min(ctx.duracao, corte.fim + _janela(depois))
    destino = pasta_do_corte(ctx.pasta, corte)
    return {
        "versao": ctx.versao,
        "inicio": corte.inicio,
        "fim": corte.fim,
        "duracao_episodio": ctx.duracao,
        "minima": minima,
        "maxima": maxima,
        "de": round(de, 3),
        "ate": round(ate, 3),
        "palavras": _palavras_com_falantes(ctx, de, ate),
        "outros": [
            {"numero": c.numero, "titulo": c.titulo, "inicio": c.inicio, "fim": c.fim}
            for c in ctx.cortes
            if c.numero != n and c.fim > de and c.inicio < ate
        ],
        "preparado": (destino / TRABALHO / NOME_ARQUIVO).is_file(),
        "montado": (destino / CORTE_MP4).is_file(),
        "problemas": validar_trecho(ctx.palavras, corte, ctx.duracao),
        "pedido": _ultimo_pedido(requisicao, ctx.pasta.name, n),
    }


class TrechoPedido(BaseModel):
    inicio: float
    fim: float


class NovoTrecho(TrechoPedido):
    """Corpo JSON obrigatório, com a versão do aprovados.json que o dono viu e a confirmação."""

    versao: str
    confirmado: Literal[True]


def _alinhado(ctx: _Contexto, corpo: TrechoPedido) -> tuple[float, float, list[str]]:
    """(início, fim, problemas): o trecho pedido nas fronteiras das palavras e o que o `validar` diria dele."""
    if not (math.isfinite(corpo.inicio) and math.isfinite(corpo.fim)):
        raise HTTPException(422, TEMPO_INVALIDO)
    try:
        inicio, fim = alinhar(ctx.palavras, corpo.inicio, corpo.fim)
    except ValueError as erro:
        raise HTTPException(422, f"Não dá para alinhar: {erro}.") from erro
    if fim <= inicio:
        return inicio, fim, [FIM_ANTES]
    _limites()  # clipline.toml ilegível vira 422 antes do validar
    novo = Corte(ctx.corte.numero, ctx.corte.titulo, inicio, fim, ctx.corte.clima)
    return inicio, fim, validar_trecho(ctx.palavras, novo, ctx.duracao)


def _nomes_ou_nada(requisicao: Request) -> list[str] | None:
    try:
        return _dependencias(requisicao).nomes()
    except (OSError, UnicodeDecodeError):
        return None


@roteador.post("/episodios/{ep}/cortes/{n}/trecho/conferir")
def conferir_trecho(ep: str, n: int, corpo: TrechoPedido, requisicao: Request) -> dict:
    """O trecho alinhado, os problemas (que impedem a troca), os avisos e o que muda ou se perde. Não grava nada."""
    ctx = _contexto(requisicao, ep, n)
    inicio, fim, problemas = _alinhado(ctx, corpo)
    mudou = (inicio, fim) != (ctx.corte.inicio, ctx.corte.fim)
    resposta = {
        "inicio": inicio,
        "fim": fim,
        "duracao": round(fim - inicio, 3),
        "mudou": mudou,
        "problemas": problemas,
        "avisos": [],
        "resumo": [],
        "perdas": [],
    }
    if mudou and not problemas:
        previsao = prever(ctx.pasta, ctx.corte, ctx.cortes, inicio, fim, ctx.palavras, _nomes_ou_nada(requisicao))
        resposta.update(avisos=previsao.avisos, resumo=previsao.resumo, perdas=previsao.perdas)
    return resposta


@roteador.post("/episodios/{ep}/cortes/{n}/trecho", status_code=202)
def trocar(ep: str, n: int, corpo: NovoTrecho, requisicao: Request):
    ctx = _contexto(requisicao, ep, n)
    estado = requisicao.app.state
    if estado.fila.montando_corte(ctx.pasta.name, n):
        return JSONResponse({"detail": MONTANDO}, status_code=409)
    if corpo.versao != ctx.versao:
        return JSONResponse({"detail": APROVADOS_MUDOU, "versao_atual": ctx.versao}, status_code=409)
    inicio, fim, problemas = _alinhado(ctx, corpo)
    if problemas:
        raise HTTPException(422, "; ".join(problemas))
    if (inicio, fim) == (ctx.corte.inicio, ctx.corte.fim):
        raise HTTPException(422, SEM_MUDANCA)
    dependencias = _dependencias(requisicao)
    preparar = functools.partial(_com_musicas, dependencias.preparar, estado.pasta_musicas)

    def executar(progresso):
        return trocar_trecho(
            ctx.pasta, n, inicio, fim, ctx.versao, preparar, estado.montar, dependencias.nomes,
            base=estado.cortes, pasta_musicas=estado.pasta_musicas, trava=_TRAVA_GRAVACAO, progresso=progresso,
        )

    try:
        pedido = estado.fila.pedir_tarefa(TIPO, ctx.pasta, [n], executar)
    except PedidoAtivo:
        return JSONResponse({"detail": MONTANDO}, status_code=409)
    return pedido.como_dict()


def _com_musicas(preparar, pasta_musicas: Path, pasta: Path, numero: int, nomes: list[str]) -> str:
    return preparar(pasta, numero, nomes, pasta_musicas)
