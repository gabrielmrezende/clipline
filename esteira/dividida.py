"""Tela dividida: quando duas pessoas visíveis na mesma cena trocam a fala rápido, o trecho sai
empilhado (uma pessoa em cima, a outra embaixo, cada uma recortada no rosto).

Lógica pura (sem modelos nem ffmpeg). A decisão tem histerese, para não piscar entre layouts:
entra com TURNOS_PARA_ENTRAR turnos curtos seguidos (< TURNO_CURTO) alternando as duas vozes; sai
só com um turno longo (>= TURNO_LONGO) ou uma pausa longa. Turnos entre os dois limites mantêm o
layout que já está. Depois, trechos curtos somem e telas cheias curtas entre duas divididas viram
dividida.
"""

import re
from dataclasses import replace

from esteira.enquadrar import TRECHO_MINIMO, Cena, Rosto, TrechoVoz, nivel_zoom
from esteira.modelos import Cue
from esteira.planos import Plano

TURNO_IGNORADO = 0.6  # s; "é", "uhum": fala mais curta que isso não conta como turno
PAUSA_QUEBRA = 1.5  # s; a mesma voz depois de pausa menor é o mesmo turno; pausa maior quebra a sequência
TURNO_CURTO = 4.0  # s; turno abaixo disso conta para entrar na tela dividida
TURNO_LONGO = 7.0  # s; turno a partir disso tira da tela dividida
TURNOS_PARA_ENTRAR = 3  # turnos curtos seguidos, alternando as duas vozes
DIVIDIDA_MINIMA = 4.0  # s; tela dividida mais curta que isso não entra
SOLO_MINIMO = 3.0  # s; tela cheia mais curta que isso, entre divididas ou na borda da cena, vira dividida
OLHOS_EM_CIMA = 0.36  # altura dos olhos na metade de cima (fração da metade)
OLHOS_EMBAIXO = 0.42  # na metade de baixo, mais para baixo: a legenda fica na emenda
LEGENDA_PICADA = 0.2  # s; pedaço de legenda mais curto que isso na troca de layout some
POSICAO_LEGENDA = r"\an5\pos(540,960)"  # na emenda das duas metades
_EPSILON = 1e-9


def _turnos(vozes: list[TrechoVoz], inicio: float, fim: float) -> list[TrechoVoz]:
    """Turnos das vozes dentro de [inicio, fim], com a mesma voz emendada. Não contam a fala curtíssima
    nem a que cabe inteira dentro da fala de outra voz (o "aham" de quem ouve)."""
    recortados = sorted(
        (TrechoVoz(max(t.inicio, inicio), min(t.fim, fim), t.voz) for t in vozes if t.fim > inicio and t.inicio < fim),
        key=lambda t: (t.inicio, t.fim),
    )
    turnos: list[TrechoVoz] = []
    for turno in recortados:
        if turno.fim - turno.inicio < TURNO_IGNORADO:
            continue
        if any(o.voz != turno.voz and o.inicio <= turno.inicio and o.fim >= turno.fim for o in recortados):
            continue
        anterior = turnos[-1] if turnos else None
        if anterior is not None and anterior.voz == turno.voz and turno.inicio - anterior.fim <= PAUSA_QUEBRA:
            anterior.fim = max(anterior.fim, turno.fim)
        else:
            turnos.append(TrechoVoz(turno.inicio, turno.fim, turno.voz))
    return turnos


def _decidir(turnos: list[TrechoVoz]) -> list[list[float]]:
    trechos: list[list[float]] = []
    aberto: list[float] | None = None
    corrida: list[TrechoVoz] = []
    anterior: TrechoVoz | None = None
    for turno in turnos:
        duracao = turno.fim - turno.inicio
        pausa = turno.inicio - anterior.fim if anterior is not None else 0.0
        if aberto is not None:
            if pausa > PAUSA_QUEBRA:
                trechos.append(aberto)
                aberto = None
            elif duracao >= TURNO_LONGO - _EPSILON:
                aberto[1] = max(aberto[1], turno.inicio)
                trechos.append(aberto)
                aberto = None
            else:
                aberto[1] = max(aberto[1], turno.fim)
                anterior = turno
                continue
        if pausa > PAUSA_QUEBRA or (corrida and corrida[-1].voz == turno.voz):
            corrida = []
        if duracao < TURNO_CURTO:
            corrida.append(turno)
            if len(corrida) >= TURNOS_PARA_ENTRAR:
                aberto = [corrida[0].inicio, turno.fim]
                corrida = []
        else:
            corrida = []
        anterior = turno
    if aberto is not None:
        trechos.append(aberto)
    return trechos


def _arrumar(trechos: list[list[float]], inicio: float, fim: float) -> list[tuple[float, float]]:
    juntos: list[list[float]] = []
    for a, b in sorted([max(a, inicio), min(b, fim)] for a, b in trechos):
        if juntos and a - juntos[-1][1] < SOLO_MINIMO:
            juntos[-1][1] = max(juntos[-1][1], b)
        else:
            juntos.append([a, b])
    for trecho in juntos:
        if trecho[0] - inicio < SOLO_MINIMO:
            trecho[0] = inicio
        if fim - trecho[1] < SOLO_MINIMO:
            trecho[1] = fim
    return [(a, b) for a, b in juntos if b - a >= DIVIDIDA_MINIMA - _EPSILON]


def trechos_divididos(vozes: list[TrechoVoz], inicio: float, fim: float) -> list[tuple[float, float]]:
    """Intervalos de tela dividida entre `inicio` e `fim` (uma cena), dadas as falas das duas vozes."""
    return _arrumar(_decidir(_turnos(vozes, inicio, fim)), inicio, fim)


def enquadrar_painel(rosto: Rosto, embaixo: bool) -> dict:
    """Recorte de uma metade da tela dividida: o rosto no centro, olhos a OLHOS_EM_CIMA/EMBAIXO da altura."""
    z = nivel_zoom(rosto.altura)
    olhos = rosto.y - rosto.altura * 0.1
    altura_dos_olhos = OLHOS_EMBAIXO if embaixo else OLHOS_EM_CIMA
    return {"pessoa": rosto.pessoa, "x": rosto.x, "y": round(olhos + (0.5 - altura_dos_olhos) / z, 4), "zoom": z}


def _par_visivel(cena: Cena, vozes: list[TrechoVoz], ligacao: dict[str, str]) -> tuple[Rosto, Rosto, list[str]] | None:
    """As duas pessoas na tela, ligadas a uma voz, que mais falam na cena; a da esquerda vai em cima."""
    voz_da_pessoa = {pessoa: voz for voz, pessoa in ligacao.items()}
    candidatos = [r for r in cena.rostos if r.pessoa in voz_da_pessoa]
    if len(candidatos) < 2:
        return None

    def fala(rosto: Rosto) -> float:
        voz = voz_da_pessoa[rosto.pessoa]
        return sum(max(0.0, min(t.fim, cena.fim) - max(t.inicio, cena.inicio)) for t in vozes if t.voz == voz)

    dois = sorted(sorted(candidatos, key=lambda r: (-fala(r), r.pessoa))[:2], key=lambda r: r.x)
    return dois[0], dois[1], [voz_da_pessoa[r.pessoa] for r in dois]


def _plano_dividido(inicio: float, fim: float, cima: Rosto, baixo: Rosto) -> Plano:
    return Plano(
        inicio, fim, x=round((cima.x + baixo.x) / 2, 4), y=0.5, zoom=1.0,
        divisao=[enquadrar_painel(cima, False), enquadrar_painel(baixo, True)],
    )


def _absorver_curtos(planos: list[Plano]) -> list[Plano]:
    """Pedaço de tela cheia com menos de TRECHO_MINIMO colado numa tela dividida entra nela."""
    planos = list(planos)
    mudou = True
    while mudou:
        mudou = False
        for i, plano in enumerate(planos):
            if plano.divisao or plano.fim - plano.inicio >= TRECHO_MINIMO - _EPSILON:
                continue
            antes = planos[i - 1] if i > 0 and planos[i - 1].divisao and planos[i - 1].fim == plano.inicio else None
            depois = (
                planos[i + 1] if i + 1 < len(planos) and planos[i + 1].divisao and planos[i + 1].inicio == plano.fim
                else None
            )
            if antes is None and depois is None:
                continue
            if antes is not None and depois is not None and antes.divisao == depois.divisao:
                planos[i - 1:i + 2] = [replace(antes, fim=depois.fim)]
            elif antes is not None:
                planos[i - 1:i + 1] = [replace(antes, fim=plano.fim)]
            else:
                planos[i:i + 2] = [replace(depois, inicio=plano.inicio)]
            mudou = True
            break
    return planos


def _dividir_cena(planos: list[Plano], cena: Cena, vozes: list[TrechoVoz], ligacao: dict[str, str]) -> list[Plano]:
    par = _par_visivel(cena, vozes, ligacao)
    if par is None:
        return planos
    cima, baixo, vozes_do_par = par
    trechos = trechos_divididos([t for t in vozes if t.voz in vozes_do_par], cena.inicio, cena.fim)
    if not trechos:
        return planos
    resultado = [_plano_dividido(a, b, cima, baixo) for a, b in trechos]
    for plano in planos:
        cursor = plano.inicio
        for a, b in trechos:
            if b <= cursor or a >= plano.fim:
                continue
            if a > cursor:
                resultado.append(replace(plano, inicio=cursor, fim=a))
            cursor = min(b, plano.fim)
        if cursor < plano.fim:
            resultado.append(replace(plano, inicio=cursor, fim=plano.fim))
    return _absorver_curtos(sorted(resultado, key=lambda p: p.inicio))


def dividir_planos(
    planos: list[Plano], cenas: list[Cena], vozes: list[TrechoVoz], ligacao: dict[str, str]
) -> list[Plano]:
    """Troca por tela dividida os trechos de diálogo rápido entre duas pessoas visíveis na mesma cena."""
    resultado: list[Plano] = []
    restantes = sorted(planos, key=lambda p: p.inicio)
    for cena in cenas:
        da_cena = [p for p in restantes if cena.inicio <= (p.inicio + p.fim) / 2 < cena.fim]
        restantes = [p for p in restantes if p not in da_cena]
        resultado += _dividir_cena(da_cena, cena, vozes, ligacao)
    return sorted(resultado + restantes, key=lambda p: p.inicio)


# Na montagem: a legenda dos trechos de tela dividida vai para a emenda das duas metades.


def intervalos_na_saida(segmentos: list[tuple[float, float, Plano]]) -> list[tuple[float, float]]:
    """Trechos de tela dividida no tempo do corte montado (os segmentos são emendados um atrás do outro)."""
    intervalos: list[list[float]] = []
    tempo = 0.0
    for de, ate, plano in segmentos:
        if plano.divisao:
            if intervalos and abs(intervalos[-1][1] - tempo) < _EPSILON:
                intervalos[-1][1] = tempo + ate - de
            else:
                intervalos.append([tempo, tempo + ate - de])
        tempo += ate - de
    return [(a, b) for a, b in intervalos]


def partir_legenda(cues: list[Cue], intervalos: list[tuple[float, float]]) -> list[Cue]:
    """Corta as telas de legenda nas trocas de layout, para cada pedaço ficar no lugar certo.
    Pedaço com menos de LEGENDA_PICADA some (só piscaria)."""
    pontos = sorted({p for intervalo in intervalos for p in intervalo})
    resultado = []
    for cue in cues:
        cortes = [cue.inicio, *(p for p in pontos if cue.inicio < p < cue.fim), cue.fim]
        if len(cortes) == 2:
            resultado.append(cue)
            continue
        for a, b in zip(cortes, cortes[1:]):
            if b - a >= LEGENDA_PICADA:
                resultado.append(replace(cue, inicio=a, fim=b))
    return resultado


def _segundos_ass(texto: str) -> float:
    horas, minutos, segundos = texto.split(":")
    return int(horas) * 3600 + int(minutos) * 60 + float(segundos)


def legenda_no_meio(texto_ass: str, intervalos: list[tuple[float, float]]) -> str:
    """Muda a posição dos eventos do .ass que caem num trecho de tela dividida para POSICAO_LEGENDA."""
    linhas = []
    for linha in texto_ass.split("\n"):
        if linha.startswith("Dialogue:"):
            campos = linha.split(",", 3)
            meio = (_segundos_ass(campos[1]) + _segundos_ass(campos[2])) / 2
            if any(a <= meio < b for a, b in intervalos):
                linha = re.sub(r"\\an\d\\pos\([^)]*\)", lambda _: POSICAO_LEGENDA, linha, count=1)
        linhas.append(linha)
    return "\n".join(linhas)
