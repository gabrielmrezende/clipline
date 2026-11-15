"""Rotas de apoio à revisão do corte no painel (só leitura).

`GET /api/episodios/{ep}/cortes/{n}/remocoes`: o que a limpeza tirou do corte (pausas, hesitações, repetições),
no tempo do corte.mp4, para marcar na linha do corte. Junta os cortes de verdade (`faixas` do montagem.json)
com os motivos do `edicoes.md`. Não grava nada.
"""

import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import APIRouter, Request

from esteira.cortar import TRABALHO
from esteira.limpeza import PAUSA_COM_SOM
from esteira.modelos import Edicao
from esteira.painel.rotas import _pasta_do_corte
from esteira.receita import NOME_ARQUIVO, ler_receita

roteador = APIRouter(prefix="/api")

EDICOES = "edicoes.md"
TRECHO_REMOVIDO = "trecho removido"
SEM_MONTAGEM = f"sem {NOME_ARQUIVO}: rode preparar"
MONTAGEM_ILEGIVEL = f"{NOME_ARQUIVO} ilegível"
SEM_EDICOES = f"sem {EDICOES}: os motivos das remoções não aparecem"
EDICOES_ILEGIVEL = f"{EDICOES} ilegível: os motivos das remoções não aparecem"

# Do mais longo para o mais curto: "pausa com som mantida" antes de "pausa".
_MOTIVOS = (PAUSA_COM_SOM, "hesitação", "repetição", "pausa")
_LINHA = re.compile(r"^- (\d+(?:\.\d+)?)s a (\d+(?:\.\d+)?)s: (.+?)\s*$")
_SOBRA = 0.001  # sobreposição mínima (s) para uma edição contar como dentro de um corte


@dataclass(frozen=True)
class Remocao:
    """Um ponto do corte.mp4 onde a limpeza tirou alguma coisa."""

    tempo: float  # no corte.mp4 (s)
    duracao: float  # quanto foi tirado (s)
    motivo: str  # "pausa", "hesitação", "repetição", "hesitação e repetição"... ou "trecho removido"
    texto: str  # as palavras tiradas, se houver
    episodio: float  # onde começa o trecho tirado, no tempo do episódio (s)


def ler_edicoes(texto: str) -> list[Edicao]:
    """As edições do edicoes.md que o `preparar` grava. Linhas fora do formato são ignoradas."""
    edicoes: list[Edicao] = []
    for linha in texto.splitlines():
        achado = _LINHA.match(linha.strip())
        if achado is None:
            continue
        inicio, fim, resto = float(achado[1]), float(achado[2]), achado[3]
        motivo = next((m for m in _MOTIVOS if resto == m or resto.startswith(m + " ")), resto)
        edicoes.append(Edicao(inicio, fim, motivo, resto[len(motivo) :].strip()))
    return edicoes


def _faixas_validas(faixas) -> list[tuple[float, float]]:
    validas = []
    for faixa in faixas:
        try:
            de, ate = (float(v) for v in faixa)
        except (TypeError, ValueError):
            continue
        if math.isfinite(de) and math.isfinite(ate) and ate > de:
            validas.append((de, ate))
    return sorted(validas)


def _juntar(edicoes: list[Edicao]) -> tuple[str, str]:
    motivos = list(dict.fromkeys(e.motivo for e in edicoes))
    motivo = " e ".join([", ".join(motivos[:-1]), motivos[-1]]) if len(motivos) > 1 else motivos[0]
    return motivo, " ".join(e.texto for e in edicoes if e.texto)


def remocoes_no_corte(faixas, edicoes: list[Edicao]) -> list[Remocao]:
    """Uma remoção por corte entre as faixas mantidas (episódio), no tempo do corte.mp4 (a conta do `remapear`).

    O motivo vem das edições que caem no corte; sem nenhuma, é "trecho removido". Edições que não caem em
    corte nenhum (pausa com som mantida, hesitação no fim da fala) não foram tiradas e ficam de fora."""
    faixas = _faixas_validas(faixas)
    if not faixas:
        return []
    # Os cortes no tempo do episódio: antes da primeira faixa, entre as faixas e depois da última.
    vaos = [(-math.inf, faixas[0][0])]
    vaos += [(faixas[i][1], faixas[i + 1][0]) for i in range(len(faixas) - 1)]
    vaos.append((faixas[-1][1], math.inf))
    no_vao: list[list[Edicao]] = [[] for _ in vaos]
    for edicao in edicoes:
        if edicao.motivo == PAUSA_COM_SOM:
            continue
        sobras = [min(edicao.fim, ate) - max(edicao.inicio, de) for de, ate in vaos]
        melhor = max(range(len(vaos)), key=lambda i: sobras[i])
        if sobras[melhor] > _SOBRA:
            no_vao[melhor].append(edicao)

    remocoes: list[Remocao] = []
    tempo = 0.0
    for indice, ((de, ate), dentro) in enumerate(zip(vaos, no_vao, strict=True)):
        if indice > 0:
            tempo += faixas[indice - 1][1] - faixas[indice - 1][0]
        primeiro, ultimo = indice == 0, indice == len(vaos) - 1
        if (primeiro or ultimo) and not dentro:
            continue
        if primeiro:
            de = min(e.inicio for e in dentro)
        if ultimo:
            ate = max(e.fim for e in dentro)
        motivo, texto = _juntar(dentro) if dentro else (TRECHO_REMOVIDO, "")
        remocoes.append(Remocao(round(tempo, 2), round(ate - de, 2), motivo, texto, round(de, 2)))
    return remocoes


def ler_remocoes(trabalho: Path) -> dict:
    """O que a rota devolve: remoções, total tirado e avisos. Arquivo faltando ou ilegível vira aviso, não erro."""
    if not (trabalho / NOME_ARQUIVO).is_file():
        return {"remocoes": [], "removido": 0.0, "avisos": [SEM_MONTAGEM]}
    try:
        faixas = ler_receita(trabalho).faixas
    except (OSError, ValueError, KeyError, TypeError):
        return {"remocoes": [], "removido": 0.0, "avisos": [MONTAGEM_ILEGIVEL]}
    avisos: list[str] = []
    try:
        edicoes = ler_edicoes((trabalho / EDICOES).read_text("utf-8"))
    except FileNotFoundError:
        edicoes, avisos = [], [SEM_EDICOES]
    except (OSError, ValueError):
        edicoes, avisos = [], [EDICOES_ILEGIVEL]
    remocoes = remocoes_no_corte(faixas, edicoes)
    return {
        "remocoes": [asdict(r) for r in remocoes],
        "removido": round(sum(r.duracao for r in remocoes), 2),
        "avisos": avisos,
    }


@roteador.get("/episodios/{ep}/cortes/{n}/remocoes")
def remocoes(ep: str, n: int, requisicao: Request) -> dict:
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    return ler_remocoes(pasta / bloco.pasta / TRABALHO)
