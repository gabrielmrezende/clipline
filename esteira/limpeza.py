import re
from collections.abc import Callable

from esteira.modelos import Edicao, Palavra

PAUSA_LONGA = 0.5
PAUSA_MANTIDA = 0.15
MARGEM = 0.05
PROTEGIDAS = {"né", "tá", "não", "muito", "nunca", "sim", "isso"}
SILENCIO_SUFICIENTE = 0.7  # fração da pausa que precisa estar em silêncio no áudio para ser cortada
PAUSA_COM_SOM = "pausa com som mantida"

TemSom = Callable[[float, float], bool]


def cobertura(de: float, ate: float, intervalos: list[tuple[float, float]]) -> float:
    """Fração de [de, ate] coberta pelos intervalos."""
    if ate <= de:
        return 1.0
    coberto = sum(max(0.0, min(ate, b) - max(de, a)) for a, b in intervalos)
    return min(1.0, coberto / (ate - de))


def tem_som_pelos_silencios(silencios: list[tuple[float, float]], vozes: list[tuple[float, float]] = ()) -> TemSom:
    """Uma pausa tem som se o áudio não está em silêncio na maior parte dela, ou se alguém fala nela (diarização).

    É o que impede a limpeza de cortar fala que a transcrição perdeu: riso, "uhum", fala sobreposta."""
    def tem_som(de: float, ate: float) -> bool:
        if cobertura(de, ate, silencios) < SILENCIO_SUFICIENTE:
            return True
        return any(min(ate, b) - max(de, a) > 0.3 for a, b in vozes)
    return tem_som
HESITACOES = {"hum", "hã", "ahn", "éé", "hmm", "ãh", "eh"}


def _normalizar(texto: str) -> str:
    return re.sub(r"[^\w-]", "", texto).lower()


def _motivo_remocao(palavras: list[Palavra], indice: int) -> str | None:
    atual = _normalizar(palavras[indice].texto)
    if atual in HESITACOES:
        return "hesitação"
    texto = palavras[indice].texto
    fecha_frase = texto.endswith((".", "?", "!")) and not texto.endswith("...")
    enfase = texto.endswith((",", ";", "!", "…"))  # "muito, muito grave": repetição de propósito
    if indice + 1 < len(palavras) and atual not in PROTEGIDAS and not fecha_frase and not enfase:
        seguinte = palavras[indice + 1]
        if atual == _normalizar(seguinte.texto) and seguinte.inicio - palavras[indice].fim < PAUSA_LONGA:
            return "repetição"
    return None


def planejar_limpeza(
    palavras: list[Palavra], inicio: float, fim: float, tem_som: TemSom | None = None
) -> tuple[list[tuple[float, float]], list[Edicao]]:
    """Faixas mantidas e edições. Com `tem_som`, uma pausa só é cortada se o áudio confirmar o silêncio."""
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
                if tem_som is not None and tem_som(anterior.fim + folga, palavra.inicio - folga):
                    edicoes.append(Edicao(anterior.fim, palavra.inicio, PAUSA_COM_SOM, ""))
                else:
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
