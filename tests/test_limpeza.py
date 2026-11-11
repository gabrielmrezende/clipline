import pytest

from esteira.limpeza import planejar_limpeza, remapear
from esteira.modelos import Palavra as P
from esteira.modelos import Palavra


def duracao(faixas):
    return sum(b - a for a, b in faixas)


def test_pausa_de_1s_fica_com_0_15s():
    p = [P("a", 0, 1), P("b", 2, 3)]
    faixas, edicoes = planejar_limpeza(p, 0, 3)
    assert edicoes[0].motivo == "pausa"
    assert duracao(faixas) == pytest.approx(2.15, abs=0.01)


def test_pausa_de_0_3s_fica_intacta():
    p = [P("a", 0, 1), P("b", 1.3, 2)]
    faixas, edicoes = planejar_limpeza(p, 0, 2)
    assert edicoes == [] and faixas == [(0, 2)]


def test_repeticao_remove_a_primeira_ocorrencia():
    p = [P("o", 0, 0.2), P("o", 0.25, 0.45), P("Brasil", 0.5, 1)]
    faixas, edicoes = planejar_limpeza(p, 0, 1)
    assert edicoes[0].motivo == "repetição" and edicoes[0].texto == "o"
    assert remapear(0.1, faixas) is None
    assert remapear(0.3, faixas) is not None


def test_nao_remove_fim_de_frase_igual_ao_inicio_da_seguinte():
    p = [P("começa?", 0, 0.3), P("Começa", 0.35, 0.6), P("cedo.", 0.6, 1)]
    assert planejar_limpeza(p, 0, 1)[1] == []


def test_mantem_ne_ta_e_nao_nao():
    for texto in ("né", "tá", "não"):
        p = [P(texto, 0, 0.2), P(texto, 0.25, 0.45)]
        assert planejar_limpeza(p, 0, 0.45)[1] == []


def test_remove_hesitacao():
    p = [P("então", 0, 0.5), P("hum,", 0.5, 0.8), P("sim", 0.8, 1)]
    faixas, edicoes = planejar_limpeza(p, 0, 1)
    assert [e.motivo for e in edicoes] == ["hesitação"]
    assert remapear(0.65, faixas) is None


def test_remapear_dentro_e_fora():
    faixas = [(0, 1), (2, 3)]
    assert remapear(0.5, faixas) == 0.5
    assert remapear(2.5, faixas) == 1.5
    assert remapear(1.5, faixas) is None


def test_ignora_palavras_fora_do_trecho():
    p = [P("a", 0, 1), P("b", 5, 6), P("c", 6.1, 7), P("d", 20, 21)]
    faixas, _ = planejar_limpeza(p, 5, 7)
    assert faixas == [(5, 7)]


def test_pausa_com_som_nao_e_cortada():
    from esteira.limpeza import PAUSA_COM_SOM

    palavras = [Palavra("um", 0.0, 0.4), Palavra("dois", 2.0, 2.4)]
    faixas, edicoes = planejar_limpeza(palavras, 0.0, 2.4, tem_som=lambda de, ate: True)
    assert faixas == [(0.0, 2.4)]
    assert [e.motivo for e in edicoes] == [PAUSA_COM_SOM]


def test_pausa_em_silencio_e_cortada():
    palavras = [Palavra("um", 0.0, 0.4), Palavra("dois", 2.0, 2.4)]
    faixas, _ = planejar_limpeza(palavras, 0.0, 2.4, tem_som=lambda de, ate: False)
    assert len(faixas) == 2


def test_tem_som_pelos_silencios_e_pelas_vozes():
    from esteira.limpeza import tem_som_pelos_silencios

    assert not tem_som_pelos_silencios([(1.0, 3.0)])(1.2, 2.8)
    assert tem_som_pelos_silencios([(1.0, 1.5)])(1.2, 2.8)  # só um pedaço em silêncio
    assert tem_som_pelos_silencios([(1.0, 3.0)], [(1.5, 2.2)])(1.2, 2.8)  # alguém fala na pausa


def test_repeticao_com_virgula_e_enfase():
    palavras = [Palavra("muito,", 0.0, 0.3), Palavra("muito", 0.35, 0.6), Palavra("grave", 0.65, 1.0)]
    _, edicoes = planejar_limpeza(palavras, 0.0, 1.0)
    assert not [e for e in edicoes if e.motivo == "repetição"]
