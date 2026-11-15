"""Acompanhamento suave: dentro de um plano, o centro do recorte segue o rosto de quem fala.

Lógica pura (sem modelos nem ffmpeg). Entram as amostras do rosto que o `planos` já detecta
(uma a cada 0,5 s) e sai o trajeto do centro do recorte, em poucos pontos-chave:

1. descarta detecções espúrias (tamanho fora do normal ou salto isolado);
2. zona morta: o recorte só se move quando o rosto sai dela, e então volta a centralizar;
3. mola criticamente amortecida com limite de velocidade (sem tranco e sem passar do ponto);
4. o recorte nunca sai do quadro;
5. reduz o trajeto a pontos-chave: a reta entre dois pontos fica a menos de TOLERANCIA do trajeto.
"""

from dataclasses import dataclass, replace
from statistics import median

from esteira.enquadrar import Cena, Rosto
from esteira.planos import PROPORCAO_FAIXA, PROPORCAO_PAINEL, Plano

PASSO_MOLA = 1 / 30  # s, um quadro
PASSO_TRAJETO = 0.1  # s entre os pontos antes da redução
ZONA_MORTA = 0.08  # fração do recorte que o rosto anda sem mover o recorte
ASSENTAR = 0.25  # fração da zona morta: perto assim do rosto, o recorte para de perseguir
TEMPO_DA_MOLA = 0.5  # s; quanto maior, mais lento e macio
VELOCIDADE_MAXIMA = 0.6  # larguras (ou alturas) do recorte por segundo
ANTECIPACAO = 0.2  # s; a mola olha o rosto um pouco à frente, para não chegar atrasada
SALTO_ESPURIO = 0.25  # fração do recorte: amostra tão longe da mediana dos vizinhos é descartada
VARIACAO_DE_ALTURA = 0.4  # rosto com altura fora de ±40% da mediana do plano é descartado
VIZINHOS = 2  # de cada lado
AMOSTRAS_MINIMAS = 3
COBERTURA_MINIMA = 0.5  # fração das amostras esperadas no plano (uma a cada PASSO_AMOSTRA)
PASSO_AMOSTRA = 0.5  # s, o passo da detecção de rostos (rostos.PASSO)
MOVIMENTO_MINIMO = 0.003  # fração do quadro; trajeto que anda menos que isso fica parado
TOLERANCIA = 0.0015  # fração do quadro
PONTOS_POR_SEGUNDO = 2.5  # teto de pontos-chave; acima disso a tolerância cresce
TOLERANCIA_CAIXA = 0.05  # distância horizontal máxima entre o plano e o rosto que ele enquadra


@dataclass
class Amostra:  # rosto detectado; coordenadas de 0 a 1 no quadro original
    tempo: float
    x: float
    y: float
    altura: float


@dataclass(frozen=True)
class Janela:  # tamanho do recorte, em fração do quadro original
    largura: float
    altura: float


def janela(zoom: float, proporcao_quadro: float, proporcao_recorte: float = PROPORCAO_FAIXA) -> Janela:
    """`proporcao_quadro` é largura/altura do vídeo original (16/9); `proporcao_recorte`, a do recorte."""
    altura = min(1 / max(zoom, 1e-9), 1.0)
    return Janela(min(altura * proporcao_recorte / proporcao_quadro, 1.0), altura)


def descartar_espurias(amostras: list[Amostra], janela_: Janela) -> list[Amostra]:
    """Tira rosto de tamanho muito diferente do normal (outro rosto, detecção ruim) e salto isolado
    (uma amostra longe da mediana das vizinhas). Um movimento de verdade fica: as vizinhas acompanham."""
    if len(amostras) < AMOSTRAS_MINIMAS:
        return list(amostras)
    ordenadas = sorted(amostras, key=lambda a: a.tempo)
    centro_x = median(a.x for a in ordenadas)
    por_tempo: dict[float, Amostra] = {}
    for amostra in ordenadas:  # duas detecções no mesmo instante: fica a mais perto do centro
        atual = por_tempo.get(amostra.tempo)
        if atual is None or abs(amostra.x - centro_x) < abs(atual.x - centro_x):
            por_tempo[amostra.tempo] = amostra
    unicas = list(por_tempo.values())
    altura_tipica = median(a.altura for a in unicas)
    boas = [a for a in unicas if abs(a.altura - altura_tipica) <= VARIACAO_DE_ALTURA * altura_tipica]
    resultado = []
    for i, amostra in enumerate(boas):
        vizinhas = boas[max(0, i - VIZINHOS):i] + boas[i + 1:i + 1 + VIZINHOS]
        if len(vizinhas) >= 2:
            longe_x = abs(amostra.x - median(v.x for v in vizinhas)) > SALTO_ESPURIO * janela_.largura
            longe_y = abs(amostra.y - median(v.y for v in vizinhas)) > SALTO_ESPURIO * janela_.altura
            if longe_x or longe_y:
                continue
        resultado.append(amostra)
    return resultado


def _no_tempo(alvos: list[tuple[float, float]], tempo: float) -> float:
    if tempo <= alvos[0][0]:
        return alvos[0][1]
    for (t0, v0), (t1, v1) in zip(alvos, alvos[1:]):
        if tempo <= t1:
            return v0 + (v1 - v0) * (tempo - t0) / (t1 - t0) if t1 > t0 else v1
    return alvos[-1][1]


def mola(atual: float, velocidade: float, alvo: float, passo: float, maxima: float) -> tuple[float, float]:
    """Um passo de mola criticamente amortecida com velocidade limitada a `maxima` (por segundo).
    Não passa do alvo. Devolve (posição, velocidade)."""
    omega = 2 / TEMPO_DA_MOLA
    x = omega * passo
    fator = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x)
    limite = maxima * TEMPO_DA_MOLA
    diferenca = min(max(atual - alvo, -limite), limite)
    temporario = (velocidade + omega * diferenca) * passo
    velocidade = (velocidade - omega * temporario) * fator
    novo = atual - diferenca + (diferenca + temporario) * fator
    if (alvo - atual > 0) == (novo > alvo):
        return alvo, 0.0
    return novo, velocidade


def seguir(
    alvos: list[tuple[float, float]], tempos: list[float], zona: float, maxima: float, minimo: float, maximo: float
) -> list[float]:
    """Posição do recorte em cada um dos `tempos` (passo constante), seguindo os `alvos` (tempo, valor).
    Começa em cima do alvo e fica parado enquanto o alvo não sai da zona morta. Quando sai, a mola
    persegue o alvo até alcançá-lo (a menos de ASSENTAR da zona) e o recorte volta a parar ali."""

    def preso(valor: float) -> float:
        return min(max(valor, minimo), maximo)

    passo = tempos[1] - tempos[0] if len(tempos) > 1 else PASSO_MOLA
    posicao = ancora = preso(_no_tempo(alvos, tempos[0] + ANTECIPACAO))
    velocidade = 0.0
    movendo = False
    saida = []
    for tempo in tempos:
        alvo = preso(_no_tempo(alvos, tempo + ANTECIPACAO))
        movendo = movendo or abs(alvo - ancora) > zona
        if movendo:
            ancora = alvo
            movendo = abs(alvo - posicao) >= ASSENTAR * zona
        posicao, velocidade = mola(posicao, velocidade, ancora, passo, maxima)
        posicao = preso(posicao)
        saida.append(posicao)
    return saida


def reduzir(pontos: list[tuple[float, float, float]], tolerancia: float) -> list[tuple[float, float, float]]:
    """Douglas-Peucker em (tempo, x, y): só ficam os pontos sem os quais a reta erraria mais que `tolerancia`."""
    if len(pontos) <= 2:
        return list(pontos)
    manter = {0, len(pontos) - 1}
    pilha = [(0, len(pontos) - 1)]
    while pilha:
        a, b = pilha.pop()
        (ta, xa, ya), (tb, xb, yb) = pontos[a], pontos[b]
        pior, indice = 0.0, None
        for i in range(a + 1, b):
            t, x, y = pontos[i]
            fracao = (t - ta) / (tb - ta) if tb > ta else 0.0
            erro = max(abs(x - (xa + (xb - xa) * fracao)), abs(y - (ya + (yb - ya) * fracao)))
            if erro > pior:
                pior, indice = erro, i
        if indice is not None and pior > tolerancia:
            manter.add(indice)
            pilha += [(a, indice), (indice, b)]
    return [pontos[i] for i in sorted(manter)]


def trajeto(
    amostras: list[Amostra], inicio: float, fim: float, janela_: Janela, deslocamento: tuple[float, float] = (0.0, 0.0)
) -> list[list[float]] | None:
    """[[tempo, x, y], ...] do centro do recorte de `inicio` a `fim`, ou None: poucas amostras boas
    ou rosto parado (o plano fica fixo, como sempre). `deslocamento` vai do rosto ao centro do recorte
    (o enquadramento põe os olhos no terço de cima)."""
    if fim - inicio < 2 * PASSO_TRAJETO:
        return None
    perto = [a for a in amostras if inicio - PASSO_AMOSTRA <= a.tempo <= fim + PASSO_AMOSTRA]
    boas = sorted(descartar_espurias(perto, janela_), key=lambda a: a.tempo)
    dentro = [a for a in boas if inicio <= a.tempo <= fim]
    esperadas = (fim - inicio) / PASSO_AMOSTRA
    if len(dentro) < AMOSTRAS_MINIMAS or len(dentro) < COBERTURA_MINIMA * esperadas:
        return None
    dx, dy = deslocamento
    quadros = max(2, round((fim - inicio) / PASSO_MOLA) + 1)
    tempos = [inicio + (fim - inicio) * i / (quadros - 1) for i in range(quadros)]
    xs = seguir([(a.tempo, a.x + dx) for a in boas], tempos, ZONA_MORTA * janela_.largura,
                VELOCIDADE_MAXIMA * janela_.largura, janela_.largura / 2, 1 - janela_.largura / 2)
    ys = seguir([(a.tempo, a.y + dy) for a in boas], tempos, ZONA_MORTA * janela_.altura,
                VELOCIDADE_MAXIMA * janela_.altura, janela_.altura / 2, 1 - janela_.altura / 2)
    if max(xs) - min(xs) < MOVIMENTO_MINIMO and max(ys) - min(ys) < MOVIMENTO_MINIMO:
        return None
    a_cada = max(1, round(PASSO_TRAJETO / PASSO_MOLA))
    indices = sorted({*range(0, quadros, a_cada), quadros - 1})
    pontos = [(tempos[i], xs[i], ys[i]) for i in indices]
    teto = max(2, int((fim - inicio) * PONTOS_POR_SEGUNDO) + 2)
    tolerancia = TOLERANCIA
    chaves = reduzir(pontos, tolerancia)
    while len(chaves) > teto:
        tolerancia *= 1.5
        chaves = reduzir(pontos, tolerancia)
    return [[round(t, 3), round(x, 4), round(y, 4)] for t, x, y in chaves]


def rosto_do_plano(plano: Plano, cena: Cena) -> Rosto | None:
    """O rosto que o plano enquadra: o mais perto do centro do plano. Plano aberto de grupo não tem."""
    if not cena.rostos or plano.zoom <= 1.0 and len(cena.rostos) > 1:
        return None
    rosto = min(cena.rostos, key=lambda r: abs(r.x - plano.x))
    return rosto if abs(rosto.x - plano.x) <= TOLERANCIA_CAIXA else None


def _cena_de(plano: Plano, cenas: list[Cena]) -> Cena | None:
    meio = (plano.inicio + plano.fim) / 2
    return next((c for c in cenas if c.inicio <= meio < c.fim), None)


def _da_cena(amostras: list[Amostra], cena: Cena) -> list[Amostra]:
    return [a for a in amostras if cena.inicio <= a.tempo < cena.fim]


def _painel_suave(
    painel: dict, plano: Plano, cena: Cena, amostras: dict[str, list[Amostra]], proporcao_quadro: float
) -> dict:
    rosto = next((r for r in cena.rostos if r.pessoa == painel.get("pessoa")), None)
    if rosto is None:
        return painel
    caminho = trajeto(
        _da_cena(amostras.get(rosto.pessoa, []), cena), plano.inicio, plano.fim,
        janela(painel["zoom"], proporcao_quadro, PROPORCAO_PAINEL), (painel["x"] - rosto.x, painel["y"] - rosto.y),
    )
    return {**painel, "trajeto": caminho} if caminho else painel


def acompanhar_planos(
    planos: list[Plano], cenas: list[Cena], amostras: dict[str, list[Amostra]], proporcao_quadro: float
) -> list[Plano]:
    """Põe trajeto nos planos (e nas metades da tela dividida) em que o rosto enquadrado se move.
    `amostras`: por pessoa, as detecções do rosto. Plano sem rosto, de grupo ou parado fica como está."""
    resultado = []
    for plano in planos:
        cena = _cena_de(plano, cenas)
        if cena is None:
            resultado.append(plano)
        elif plano.divisao:
            divisao = [_painel_suave(p, plano, cena, amostras, proporcao_quadro) for p in plano.divisao]
            resultado.append(replace(plano, divisao=divisao))
        else:
            resultado.append(_plano_suave(plano, cena, amostras, proporcao_quadro))
    return resultado


def _plano_suave(plano: Plano, cena: Cena, amostras: dict[str, list[Amostra]], proporcao_quadro: float) -> Plano:
    rosto = rosto_do_plano(plano, cena)
    if rosto is None:
        return plano
    caminho = trajeto(
        _da_cena(amostras.get(rosto.pessoa, []), cena), plano.inicio, plano.fim,
        janela(plano.zoom, proporcao_quadro), (plano.x - rosto.x, plano.y - rosto.y),
    )
    return replace(plano, trajeto=caminho) if caminho else plano
