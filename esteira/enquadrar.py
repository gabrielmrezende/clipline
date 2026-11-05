"""Enquadramento por quem fala: decide os planos de recorte de uma cena de câmera
a partir das vozes (quem fala e quando) e dos rostos visíveis (onde cada pessoa está).

Lógica pura: não usa modelos nem ffmpeg.
"""

from dataclasses import dataclass

from esteira.planos import Plano

NIVEIS = (1.0, 1.35, 1.7, 2.0)
META_ROSTO = 0.28
TURNO_MINIMO = 2.0
TRECHO_MINIMO = 2.0
SOBREPOSICAO_MAXIMA = 1.0

_EPSILON = 1e-9
_SOBREPOSTA = object()  # rótulo de trecho com duas vozes ao mesmo tempo


@dataclass
class TrechoVoz:  # inicio, fim em segundos do episódio
    inicio: float
    fim: float
    voz: str


@dataclass
class Rosto:  # coordenadas de 0 a 1 no quadro original
    pessoa: str
    x: float
    y: float
    largura: float
    altura: float


@dataclass
class Cena:  # plano de câmera com rostos médios visíveis
    inicio: float
    fim: float
    rostos: list[Rosto]


def nivel_zoom(altura_rosto: float) -> float:
    if altura_rosto <= 0:
        return 1.0
    z = min(META_ROSTO / altura_rosto, NIVEIS[-1])
    return min(NIVEIS, key=lambda nivel: abs(nivel - z))


def enquadrar_rosto(rosto: Rosto) -> Plano:
    z = nivel_zoom(rosto.altura)
    olhos = rosto.y - rosto.altura * 0.1
    return Plano(0.0, 0.0, x=rosto.x, y=olhos + 1 / (6 * z), zoom=z)


def falante_em(vozes: list[TrechoVoz], inicio: float, fim: float) -> str | None:
    tempos: dict[str, float] = {}
    for trecho in vozes:
        dentro = min(fim, trecho.fim) - max(inicio, trecho.inicio)
        if dentro > 0:
            tempos[trecho.voz] = tempos.get(trecho.voz, 0.0) + dentro
    if not tempos:
        return None
    return max(tempos, key=tempos.get)


def _mmss(segundos: float) -> str:
    total = int(max(segundos, 0))
    return f"{total // 60:02d}:{total % 60:02d}"


def _turnos_da_cena(cena: Cena, vozes: list[TrechoVoz]) -> list[TrechoVoz]:
    turnos = []
    for trecho in vozes:
        inicio, fim = max(trecho.inicio, cena.inicio), min(trecho.fim, cena.fim)
        if fim - inicio >= TURNO_MINIMO - _EPSILON:
            turnos.append(TrechoVoz(inicio, fim, trecho.voz))
    return turnos


def _rotular(cena: Cena, turnos: list[TrechoVoz], alertas: list[str]) -> list[list]:
    """Divide a cena nos pontos de troca de voz. Devolve [inicio, fim, rotulo]."""
    pontos = sorted({cena.inicio, cena.fim, *(t.inicio for t in turnos), *(t.fim for t in turnos)})
    pedacos = []
    for a, b in zip(pontos, pontos[1:]):
        ativas = {t.voz for t in turnos if t.inicio < b and t.fim > a}
        pedacos.append([a, b, ativas])

    rotulados: list[list] = []
    i = 0
    while i < len(pedacos):
        a, b, ativas = pedacos[i]
        if len(ativas) < 2:
            rotulados.append([a, b, next(iter(ativas)) if ativas else None])
            i += 1
            continue
        j = i
        while j < len(pedacos) and len(pedacos[j][2]) >= 2:
            j += 1
        fim = pedacos[j - 1][1]
        if fim - a > SOBREPOSICAO_MAXIMA + _EPSILON:
            alertas.append(f"{_mmss(a - cena.inicio)} fala sobreposta")
            rotulo = _SOBREPOSTA
        elif rotulados and rotulados[-1][2] is not None:
            rotulo = rotulados[-1][2]
        else:
            rotulo = falante_em(turnos, a, fim)
        rotulados.append([a, fim, rotulo])
        i = j

    # Silêncio continua com quem falava antes (no começo, com quem fala depois).
    for k in range(1, len(rotulados)):
        if rotulados[k][2] is None:
            rotulados[k][2] = rotulados[k - 1][2]
    for k in range(len(rotulados) - 2, -1, -1):
        if rotulados[k][2] is None:
            rotulados[k][2] = rotulados[k + 1][2]
    return _fundir_iguais(rotulados)


def _fundir_iguais(trechos: list[list]) -> list[list]:
    fundidos: list[list] = []
    for trecho in trechos:
        if fundidos and fundidos[-1][2] == trecho[2]:
            fundidos[-1][1] = trecho[1]
        else:
            fundidos.append(list(trecho))
    return fundidos


def _juntar_curtos(trechos: list[list]) -> list[list]:
    while len(trechos) > 1:
        curto = next(
            (k for k, t in enumerate(trechos) if t[1] - t[0] < TRECHO_MINIMO - _EPSILON), None
        )
        if curto is None:
            break
        if curto == 0:
            trechos[1][0] = trechos[0][0]
        else:
            trechos[curto - 1][1] = trechos[curto][1]
        del trechos[curto]
        trechos = _fundir_iguais(trechos)
    return trechos


def _enquadrar_voz(
    cena: Cena, voz: str | None, ligacao: dict[str, str], convidado: str | None = None
) -> Plano:
    pessoa = ligacao.get(voz) if voz is not None else None
    for rosto in cena.rostos:
        if pessoa is not None and rosto.pessoa == pessoa:
            return enquadrar_rosto(rosto)
    if len(cena.rostos) == 1:
        return enquadrar_rosto(cena.rostos[0])
    # Quem fala está fora da tela: mostra a reação do convidado, se ele aparece.
    for rosto in cena.rostos:
        if convidado is not None and rosto.pessoa == convidado:
            return enquadrar_rosto(rosto)
    if len(cena.rostos) >= 2:
        media = sum(r.x for r in cena.rostos) / len(cena.rostos)
        return Plano(0.0, 0.0, x=media, y=0.5, zoom=1.0)
    return Plano(0.0, 0.0)


def enquadrar_cena(
    cena: Cena, vozes: list[TrechoVoz], ligacao: dict[str, str], convidado: str | None = None
) -> tuple[list[Plano], list[str]]:
    alertas: list[str] = []
    if not cena.rostos:
        alertas.append(f"{_mmss(0)} sem rosto")
    turnos = _turnos_da_cena(cena, vozes)
    trechos = _juntar_curtos(_rotular(cena, turnos, alertas))

    planos: list[Plano] = []
    sem_pessoa: set[str] = set()
    for inicio, fim, rotulo in trechos:
        if rotulo is _SOBREPOSTA and planos:
            anterior = planos[-1]
            enquadrado = Plano(inicio, fim, anterior.x, anterior.y, anterior.zoom)
        else:
            voz = falante_em(turnos, inicio, fim) if rotulo is _SOBREPOSTA else rotulo
            if voz is not None and voz not in ligacao and voz not in sem_pessoa:
                sem_pessoa.add(voz)
                alertas.append(f"{_mmss(inicio - cena.inicio)} voz {voz} sem pessoa")
            base = _enquadrar_voz(cena, voz, ligacao, convidado)
            enquadrado = Plano(inicio, fim, base.x, base.y, base.zoom)
        if planos and (planos[-1].x, planos[-1].y, planos[-1].zoom) == (
            enquadrado.x, enquadrado.y, enquadrado.zoom
        ):
            planos[-1].fim = fim
        else:
            planos.append(enquadrado)
    return planos, alertas
