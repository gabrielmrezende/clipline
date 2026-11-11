import pytest

from esteira.caminhos import (
    CORTES,
    ENCERRAMENTOS,
    IDENTIDADE,
    LOGO,
    PROGRAMAS,
    RAIZ,
    EscritaProibida,
    garantir_escrita,
)


def test_permite_gravar_em_cortes():
    assert garantir_escrita(CORTES / "x" / "a.json")


def test_bloqueia_pasta_de_episodio():
    with pytest.raises(EscritaProibida):
        garantir_escrita(PROGRAMAS / "Entre Assuntos" / "a.mp4")


def test_bloqueia_caminho_com_ponto_ponto():
    with pytest.raises(EscritaProibida):
        garantir_escrita(CORTES / ".." / "3 - Identidade" / "Logos" / "a.png")


@pytest.mark.skipif(not LOGO.is_file(), reason="só na máquina do canal: precisa das pastas e da identidade reais")
def test_arquivos_do_canal_existem():
    assert RAIZ.joinpath("Contexto").is_dir()
    assert PROGRAMAS.is_dir() and IDENTIDADE.is_dir()
    assert LOGO.is_file()
    assert all(e.is_file() for e in ENCERRAMENTOS)
