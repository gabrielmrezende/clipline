import pytest

from esteira.caminhos import CORTES, RAIZ, EscritaProibida, garantir_escrita


def test_permite_gravar_em_cortes():
    assert garantir_escrita(CORTES / "x" / "a.json")


def test_bloqueia_pasta_de_episodio():
    with pytest.raises(EscritaProibida):
        garantir_escrita(RAIZ / "Entre Assuntos" / "a.mp4")


def test_bloqueia_caminho_com_ponto_ponto():
    with pytest.raises(EscritaProibida):
        garantir_escrita(CORTES / ".." / "Logos" / "a.png")
