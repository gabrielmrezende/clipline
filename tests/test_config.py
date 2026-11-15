import shutil
from pathlib import Path

import pytest

from esteira import config


def test_sem_arquivo_valem_os_padroes_de_sempre(tmp_path):
    c = config.ler(tmp_path / "nao-existe.toml")
    assert (c.duracao_minima, c.duracao_maxima, c.legenda_estilo, c.normalizar_voz) == (60.0, 120.0, "fixa", False)


def test_exemplo_do_repositorio_e_igual_aos_padroes(tmp_path):
    exemplo = Path(__file__).resolve().parent.parent / "clipline.exemplo.toml"
    lida = config.ler(exemplo)
    assert lida == config.Config()
    assert lida.extras == {}


def test_secoes_e_tipos(tmp_path):
    arquivo = tmp_path / "clipline.toml"
    arquivo.write_text('[duracao]\nminima = 45\nmaxima = 90\n[legenda]\nestilo = "palavra"\n[voz]\nnormalizar = true\n', "utf-8")
    c = config.ler(arquivo)
    assert (c.duracao_minima, c.duracao_maxima, c.legenda_estilo, c.normalizar_voz) == (45.0, 90.0, "palavra", True)


@pytest.mark.parametrize("texto", ['[legenda]\nestilo = "neon"\n', '[duracao]\nminima = "dez"\n', "isto não é toml = ="])
def test_erros_claros(tmp_path, texto):
    arquivo = tmp_path / "clipline.toml"
    arquivo.write_text(texto, "utf-8")
    with pytest.raises(config.ErroConfig, match="clipline.toml"):
        config.ler(arquivo)


def test_idioma_e_licencas(tmp_path):
    arquivo = tmp_path / "clipline.toml"
    arquivo.write_text('[transcricao]\nidioma = "es"\n[imagens]\nlicencas = ["cc0", "cc-by"]\n', "utf-8")
    c = config.ler(arquivo)
    assert (c.transcricao_idioma, c.imagens_licencas) == ("es", ("cc0", "cc-by"))


def test_padrao_de_idioma_e_licencas_e_o_de_sempre(tmp_path):
    c = config.ler(tmp_path / "nao-existe.toml")
    assert c.transcricao_idioma == "pt"
    assert c.imagens_licencas == ("cc0", "dominio-publico", "cc-by", "cc-by-sa")


@pytest.mark.parametrize("texto", [
    '[transcricao]\nidioma = "pt-BR"\n', '[transcricao]\nidioma = 1\n', '[imagens]\nlicencas = ["cc-by-nc"]\n',
    '[imagens]\nlicencas = []\n', '[imagens]\nlicencas = "cc0"\n',
])
def test_idioma_e_licencas_invalidos(tmp_path, texto):
    arquivo = tmp_path / "clipline.toml"
    arquivo.write_text(texto, "utf-8")
    with pytest.raises(config.ErroConfig, match="clipline.toml"):
        config.ler(arquivo)
