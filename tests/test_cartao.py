import pytest
from PIL import Image

from esteira import cartao
from esteira.caminhos import LOGO


def test_cartao_tamanho_e_manchete_longa(tmp_path):
    saida = cartao.gerar_cartao("Manchete muito longa " * 10, "O Globo", "14/08/2002", tmp_path / "c.png")
    assert Image.open(saida).size == (1080, 1920)


def test_manchete_longa_cabe_nas_margens():
    linhas, fonte = cartao.ajustar_manchete("Manchete muito longa " * 10)
    assert all(fonte.getlength(l) <= cartao.LARGURA_TEXTO for l in linhas)
    assert len(linhas) * fonte.size * 1.25 <= cartao.ALTURA_TEXTO


@pytest.mark.skipif(not LOGO.is_file(), reason="só na máquina do canal: precisa do logo real em 3 - Identidade/")
def test_sobreposicao_tem_logo_no_topo_e_fundo_transparente(tmp_path):
    imagem = Image.open(cartao.gerar_sobreposicao(tmp_path / "s.png"))
    assert imagem.mode == "RGBA" and imagem.size == (1080, 1920)
    assert imagem.crop((0, 0, 1080, 500)).getchannel("A").getextrema()[1] == 255
    assert imagem.crop((0, 700, 1080, 1920)).getchannel("A").getextrema() == (0, 0)


def test_arroba_do_canal():
    assert cartao.ARROBA == "@tudoepoliticabr"


def test_linha_de_fonte():
    assert cartao.linha_fonte("O Globo", "14/08/2002") == "Fonte: O Globo, 14/08/2002"
