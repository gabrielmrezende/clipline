import pytest

from esteira.enquadrar import (
    Cena,
    Rosto,
    TrechoVoz,
    enquadrar_cena,
    enquadrar_rosto,
    falante_em,
    nivel_zoom,
)

P1 = Rosto("P1", x=0.3, y=0.4, largura=0.1, altura=0.2)
P2 = Rosto("P2", x=0.7, y=0.45, largura=0.1, altura=0.2)
LIGACAO = {"V1": "P1", "V2": "P2", "V3": "P3"}


def _plano_em(planos, t):
    return next(p for p in planos if p.inicio <= t < p.fim)


def _sem_buracos(planos, inicio, fim):
    assert planos[0].inicio == inicio
    assert planos[-1].fim == fim
    for a, b in zip(planos, planos[1:]):
        assert a.fim == b.inicio


def test_nivel_zoom():
    assert nivel_zoom(0.28) == 1.0
    assert nivel_zoom(0.20) == 1.35
    assert nivel_zoom(0.165) == 1.7
    assert nivel_zoom(0.10) == 2.0
    assert nivel_zoom(0.0) == 1.0


def test_close_nao_da_zoom():
    plano = enquadrar_rosto(Rosto("P1", x=0.5, y=0.5, largura=0.3, altura=0.45))
    assert plano.zoom == 1.0


def test_enquadrar_rosto_poe_olhos_no_terco_superior():
    plano = enquadrar_rosto(P1)
    assert plano.x == P1.x
    assert plano.zoom == 1.35
    olhos = P1.y - P1.altura * 0.1
    assert plano.y == pytest.approx(olhos + 1 / (6 * 1.35))


def test_falante_em():
    vozes = [TrechoVoz(0, 5, "V1"), TrechoVoz(4, 12, "V2")]
    assert falante_em(vozes, 0, 10) == "V2"
    assert falante_em(vozes, 0, 4) == "V1"
    assert falante_em(vozes, 20, 30) is None


def test_divide_na_troca_de_voz():
    cena = Cena(0, 20, [P1, P2])
    vozes = [TrechoVoz(0, 8, "V1"), TrechoVoz(8, 20, "V2")]
    planos, alertas = enquadrar_cena(cena, vozes, LIGACAO)
    assert len(planos) == 2
    assert planos[0].fim == 8.0 and planos[1].inicio == 8.0
    assert planos[0].x == P1.x
    assert planos[1].x == P2.x
    _sem_buracos(planos, 0, 20)
    assert alertas == []


def test_tempos_absolutos_do_episodio():
    cena = Cena(100, 120, [P1, P2])
    vozes = [TrechoVoz(90, 108, "V1"), TrechoVoz(108, 130, "V2")]
    planos, _ = enquadrar_cena(cena, vozes, LIGACAO)
    assert [(p.inicio, p.fim) for p in planos] == [(100, 108), (108, 120)]


def test_turno_curto_nao_divide():
    cena = Cena(0, 20, [P1, P2])
    vozes = [TrechoVoz(0, 8, "V1"), TrechoVoz(8.0, 9.5, "V2"), TrechoVoz(9.5, 20, "V1")]
    planos, _ = enquadrar_cena(cena, vozes, LIGACAO)
    assert len(planos) == 1
    assert planos[0].x == P1.x
    _sem_buracos(planos, 0, 20)


def test_trecho_minimo():
    cena = Cena(0, 20, [P1, P2])
    vozes = [TrechoVoz(0, 19, "V1"), TrechoVoz(19, 22, "V2")]
    planos, _ = enquadrar_cena(cena, vozes, LIGACAO)
    assert all(p.fim - p.inicio >= 2.0 for p in planos)
    _sem_buracos(planos, 0, 20)


def test_falante_fora_da_tela_um_rosto():
    cena = Cena(0, 10, [P1])
    planos, _ = enquadrar_cena(cena, [TrechoVoz(0, 10, "V2")], LIGACAO)
    assert len(planos) == 1
    assert planos[0].x == P1.x
    assert planos[0].zoom == enquadrar_rosto(P1).zoom


def test_falante_fora_da_tela_varios_rostos():
    cena = Cena(0, 10, [P1, P2])
    planos, _ = enquadrar_cena(cena, [TrechoVoz(0, 10, "V3")], LIGACAO)
    assert len(planos) == 1
    assert planos[0].zoom == 1.0
    assert planos[0].x == pytest.approx((P1.x + P2.x) / 2)
    assert planos[0].y == 0.5


def test_sem_rosto_alerta():
    cena = Cena(0, 10, [])
    planos, alertas = enquadrar_cena(cena, [TrechoVoz(0, 10, "V1")], LIGACAO)
    assert len(planos) == 1
    p = planos[0]
    assert (p.inicio, p.fim, p.x, p.y, p.zoom) == (0, 10, 0.5, 0.5, 1.0)
    assert any("sem rosto" in a for a in alertas)


def test_fala_sobreposta():
    cena = Cena(0, 20, [P1, P2])
    vozes = [TrechoVoz(0, 10, "V1"), TrechoVoz(8.5, 20, "V2")]
    planos, alertas = enquadrar_cena(cena, vozes, LIGACAO)
    assert _plano_em(planos, 9.0).x == P1.x
    assert _plano_em(planos, 15.0).x == P2.x
    assert "00:08 fala sobreposta" in alertas
    _sem_buracos(planos, 0, 20)


def test_fala_sobreposta_longa_repete_plano_anterior():
    cena = Cena(0, 20, [P1, P2])
    vozes = [TrechoVoz(0, 11, "V1"), TrechoVoz(6, 20, "V2")]
    planos, alertas = enquadrar_cena(cena, vozes, LIGACAO)
    assert _plano_em(planos, 8.0).x == P1.x
    assert _plano_em(planos, 15.0).x == P2.x
    assert "00:06 fala sobreposta" in alertas
    _sem_buracos(planos, 0, 20)


def test_sobreposicao_curta_nao_alerta():
    cena = Cena(0, 20, [P1, P2])
    vozes = [TrechoVoz(0, 10, "V1"), TrechoVoz(9.5, 20, "V2")]
    _, alertas = enquadrar_cena(cena, vozes, LIGACAO)
    assert not any("fala sobreposta" in a for a in alertas)


def test_voz_sem_pessoa():
    cena = Cena(0, 10, [P1])
    planos, alertas = enquadrar_cena(cena, [TrechoVoz(0, 10, "V3")], {"V1": "P1"})
    assert planos[0].x == P1.x
    assert any("voz V3 sem pessoa" in a for a in alertas)
