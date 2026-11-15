import pytest

from esteira import acompanhar
from esteira.acompanhar import (
    Amostra,
    Janela,
    acompanhar_planos,
    descartar_espurias,
    janela,
    mola,
    reduzir,
    rosto_do_plano,
    trajeto,
)
from esteira.enquadrar import Cena, Rosto, enquadrar_rosto
from esteira.planos import PROPORCAO_FAIXA, PROPORCAO_PAINEL, Plano

JANELA = janela(1.35, 16 / 9)


def _amostras(posicao, inicio=0.0, fim=10.0, passo=0.5, altura=0.2):
    """Uma amostra a cada `passo`; `posicao(t)` devolve x (y fica em 0.4) ou (x, y)."""
    resultado = []
    t = inicio
    while t <= fim + 1e-9:
        valor = posicao(t)
        x, y = valor if isinstance(valor, tuple) else (valor, 0.4)
        resultado.append(Amostra(round(t, 3), x, y, altura))
        t += passo
    return resultado


def _xs(caminho):
    return [x for _, x, _ in caminho]


def test_janela_do_recorte():
    j = janela(2.0, 16 / 9)
    assert j.altura == pytest.approx(0.5)
    assert j.largura == pytest.approx(0.5 * PROPORCAO_FAIXA * 9 / 16)
    assert janela(1.0, 16 / 9, PROPORCAO_PAINEL).largura == pytest.approx(PROPORCAO_PAINEL * 9 / 16)
    assert janela(1.0, 0.5).largura == 1.0  # nunca maior que o quadro


def test_rosto_parado_nao_tem_trajeto():
    ruido = [0.0, 0.004, -0.003, 0.002, -0.004]
    amostras = _amostras(lambda t: 0.4 + ruido[int(t * 2) % len(ruido)])
    assert trajeto(amostras, 0, 10, JANELA) is None


def test_movimento_dentro_da_zona_morta_nao_move():
    zona = acompanhar.ZONA_MORTA * JANELA.largura
    amostras = _amostras(lambda t: 0.4 + 0.8 * zona * min(t / 10, 1))
    assert trajeto(amostras, 0, 10, JANELA) is None


def test_degrau_segue_suave_sem_passar_do_ponto():
    amostras = _amostras(lambda t: 0.4 if t < 3 else 0.6)
    caminho = trajeto(amostras, 0, 10, JANELA)
    xs = _xs(caminho)
    assert xs[0] == pytest.approx(0.4, abs=0.002)
    assert xs[-1] == pytest.approx(0.6, abs=0.002)
    assert all(b >= a - 1e-9 for a, b in zip(xs, xs[1:]))  # só anda para um lado
    assert max(xs) <= 0.6 + 1e-6
    maxima = acompanhar.VELOCIDADE_MAXIMA * JANELA.largura
    for (t0, x0, _), (t1, x1, _) in zip(caminho, caminho[1:]):
        assert abs(x1 - x0) / (t1 - t0) <= maxima * 1.02


def test_degrau_chega_em_menos_de_dois_segundos():
    caminho = trajeto(_amostras(lambda t: 0.4 if t < 3 else 0.6), 0, 10, JANELA)
    from esteira.planos import centro_em

    plano = Plano(0, 10, trajeto=caminho)
    assert centro_em(plano, 2.5)[0] == pytest.approx(0.4, abs=0.01)
    assert centro_em(plano, 5.0)[0] == pytest.approx(0.6, abs=0.01)


def test_tempo_do_trajeto_cobre_o_plano():
    caminho = trajeto(_amostras(lambda t: 0.3 + 0.03 * (t - 20), 20, 30), 20, 30, JANELA)
    assert caminho[0][0] == 20 and caminho[-1][0] == 30
    assert all(a[0] < b[0] for a, b in zip(caminho, caminho[1:]))


def test_salto_isolado_e_descartado():
    amostras = _amostras(lambda t: 0.8 if t == 4.0 else 0.4)
    assert trajeto(amostras, 0, 10, JANELA) is None
    assert all(a.x == 0.4 for a in descartar_espurias(amostras, JANELA))


def test_rosto_de_tamanho_estranho_e_descartado():
    amostras = _amostras(lambda t: 0.4)
    amostras[6] = Amostra(amostras[6].tempo, 0.7, 0.4, 0.6)
    assert amostras[6] not in descartar_espurias(amostras, JANELA)
    assert trajeto(amostras, 0, 10, JANELA) is None


def test_duas_deteccoes_no_mesmo_instante_fica_a_do_rosto():
    amostras = _amostras(lambda t: 0.4) + [Amostra(5.0, 0.9, 0.4, 0.2)]
    boas = descartar_espurias(amostras, JANELA)
    assert [a.x for a in boas if a.tempo == 5.0] == [0.4]


def test_recorte_nunca_sai_do_quadro():
    caminho = trajeto(_amostras(lambda t: (0.5 + 0.05 * t, 0.4 + 0.06 * t)), 0, 10, JANELA)
    for _, x, y in caminho:
        assert JANELA.largura / 2 - 1e-6 <= x <= 1 - JANELA.largura / 2 + 1e-6
        assert JANELA.altura / 2 - 1e-6 <= y <= 1 - JANELA.altura / 2 + 1e-6
    assert caminho[-1][1] == pytest.approx(1 - JANELA.largura / 2, abs=1e-4)


def test_poucas_amostras_fica_fixo():
    assert trajeto(_amostras(lambda t: 0.3 + 0.1 * t, 0, 1.0), 0, 10, JANELA) is None
    assert trajeto([], 0, 10, JANELA) is None


def test_deslocamento_do_rosto_ao_centro():
    caminho = trajeto(_amostras(lambda t: 0.4 if t < 3 else 0.6), 0, 10, JANELA, deslocamento=(0.0, 0.05))
    assert caminho[0][2] == pytest.approx(0.45, abs=0.002)


def test_mola_nao_passa_do_alvo_e_respeita_velocidade():
    posicao, velocidade, passo = 0.0, 0.0, 1 / 30
    posicoes = []
    for _ in range(120):
        posicao, velocidade = mola(posicao, velocidade, 1.0, passo, 0.5)
        posicoes.append(posicao)
    assert max(posicoes) <= 1.0
    assert all(b - a <= 0.5 * passo * 1.01 for a, b in zip([0.0] + posicoes, posicoes))
    assert posicoes[-1] > 0.9


def test_reduzir_reta_fica_com_as_pontas():
    pontos = [(t / 10, 0.3 + t / 100, 0.5) for t in range(50)]
    assert reduzir(pontos, 0.001) == [pontos[0], pontos[-1]]


def test_reduzir_guarda_a_curva():
    pontos = [(t / 10, 0.3 + abs(t - 25) / 100, 0.5) for t in range(51)]
    assert [p[0] for p in reduzir(pontos, 0.001)] == [0.0, 2.5, 5.0]


def test_trajeto_longo_tem_poucos_pontos():
    caminho = trajeto(_amostras(lambda t: 0.5 + 0.15 * ((t // 4) % 2), 0, 60), 0, 60, JANELA)
    assert len(caminho) <= 60 * acompanhar.PONTOS_POR_SEGUNDO + 2


P1 = Rosto("P1", 0.3, 0.4, 0.1, 0.2)
P2 = Rosto("P2", 0.7, 0.4, 0.1, 0.2)


def _plano_de(rosto, inicio=0.0, fim=10.0):
    base = enquadrar_rosto(rosto)
    return Plano(inicio, fim, base.x, base.y, base.zoom)


def test_rosto_do_plano():
    cena = Cena(0, 10, [P1, P2])
    assert rosto_do_plano(_plano_de(P2), cena) == P2
    assert rosto_do_plano(Plano(0, 10, x=0.5, zoom=1.0), cena) is None  # grupo
    assert rosto_do_plano(Plano(0, 10, x=0.5, zoom=1.35), cena) is None  # longe de todos


def test_acompanhar_planos_so_mexe_no_rosto_que_anda():
    cena = Cena(0, 10, [P1, P2])
    amostras = {
        "P1": _amostras(lambda t: 0.3 if t < 4 else 0.38),
        "P2": _amostras(lambda t: 0.7),
    }
    planos = [_plano_de(P1, 0, 5), _plano_de(P2, 5, 10)]
    novos = acompanhar_planos(planos, [cena], amostras, 16 / 9)
    assert novos[0].trajeto is not None and novos[1].trajeto is None
    assert (novos[0].x, novos[0].y, novos[0].zoom) == (planos[0].x, planos[0].y, planos[0].zoom)
    assert novos[0].trajeto[0][2] == pytest.approx(planos[0].y, abs=0.002)  # mesmo deslocamento rosto -> centro
    assert novos[1] == planos[1]


def test_acompanhar_usa_so_amostras_da_cena():
    cenas = [Cena(0, 5, [P1]), Cena(5, 10, [P1])]
    amostras = {"P1": _amostras(lambda t: 0.3 if t < 5 else 0.6)}  # outra câmera depois do corte
    novos = acompanhar_planos([_plano_de(P1, 0, 5)], cenas, amostras, 16 / 9)
    assert novos[0].trajeto is None


def test_acompanhar_metades_da_tela_dividida():
    cena = Cena(0, 10, [P1, P2])
    divisao = [
        {"pessoa": "P1", "x": 0.3, "y": 0.45, "zoom": 1.35},
        {"pessoa": "P2", "x": 0.7, "y": 0.42, "zoom": 1.35},
    ]
    plano = Plano(0, 10, x=0.5, zoom=1.0, divisao=divisao)
    amostras = {"P1": _amostras(lambda t: 0.3), "P2": _amostras(lambda t: 0.7 if t < 4 else 0.62)}
    novo = acompanhar_planos([plano], [cena], amostras, 16 / 9)[0]
    assert "trajeto" not in novo.divisao[0]
    assert novo.divisao[1]["trajeto"][-1][1] == pytest.approx(0.62, abs=0.002)
    assert plano.divisao[1].get("trajeto") is None  # o original não muda


def test_plano_fora_das_cenas_fica_igual():
    plano = Plano(20, 30, x=0.3, zoom=1.35)
    assert acompanhar_planos([plano], [Cena(0, 10, [P1])], {}, 16 / 9) == [plano]


def test_janela_e_imutavel():
    with pytest.raises(AttributeError):
        Janela(0.5, 0.5).largura = 1
