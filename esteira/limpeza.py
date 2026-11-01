import re

from esteira.modelos import Edicao, Palavra

PAUSA_LONGA = 0.5
PAUSA_MANTIDA = 0.15
MARGEM = 0.05
PROTEGIDAS = {"né", "tá", "não"}
HESITACOES = {"hum", "hã", "ahn", "éé", "hmm", "ãh", "eh"}


def _normalizar(texto: str) -> str:
    return re.sub(r"[^\w-]", "", texto).lower()


def _motivo_remocao(palavras: list[Palavra], indice: int) -> str | None:
    atual = _normalizar(palavras[indice].texto)
    if atual in HESITACOES:
        return "hesitação"
    if indice + 1 < len(palavras) and atual not in PROTEGIDAS:
        seguinte = palavras[indice + 1]
        if atual == _normalizar(seguinte.texto) and seguinte.inicio - palavras[indice].fim < PAUSA_LONGA:
            return "repetição"
    return None


def planejar_limpeza(
    palavras: list[Palavra], inicio: float, fim: float
) -> tuple[list[tuple[float, float]], list[Edicao]]:
    trecho = [p for p in palavras if p.inicio >= inicio - 0.01 and p.fim <= fim + 0.01]
    edicoes: list[Edicao] = []
    mantidas: list[Palavra] = []
    entre: list[Palavra] = []
    cortes: list[tuple[float, float]] = []
    for indice, palavra in enumerate(trecho):
        motivo = _motivo_remocao(trecho, indice)
        if motivo:
            edicoes.append(Edicao(palavra.inicio, palavra.fim, motivo, palavra.texto))
            entre.append(palavra)
            continue
        if mantidas:
            anterior = mantidas[-1]
            pausa = palavra.inicio - anterior.fim
            if entre:
                cortes.append((anterior.fim + MARGEM, palavra.inicio - MARGEM))
            elif pausa > PAUSA_LONGA:
                folga = PAUSA_MANTIDA / 2
                cortes.append((anterior.fim + folga, palavra.inicio - folga))
                edicoes.append(Edicao(anterior.fim, palavra.inicio, "pausa", ""))
        elif entre:
            inicio = palavra.inicio - MARGEM
        mantidas.append(palavra)
        entre = []

    faixas: list[tuple[float, float]] = []
    cursor = inicio
    for de, ate in cortes:
        if ate > de:
            faixas.append((cursor, de))
            cursor = ate
    faixas.append((cursor, fim))
    return faixas, edicoes


def remapear(t: float, faixas: list[tuple[float, float]]) -> float | None:
    acumulado = 0.0
    for de, ate in faixas:
        if de <= t <= ate:
            return acumulado + t - de
        acumulado += ate - de
    return None
