"""[pastas], [identidade] e [credenciais] no clipline.toml, vistos pela config."""

import pytest

from esteira import config


def _ler(tmp_path, texto):
    arquivo = tmp_path / "clipline.toml"
    arquivo.write_text(texto, "utf-8")
    return config.ler(arquivo)


def test_secoes_de_pastas_e_identidade_nao_viram_extras(tmp_path):
    lida = _ler(tmp_path, '[pastas]\ncortes = "Saída"\n[identidade]\nencerramentos = []\n'
                          '[credenciais]\nprefixo = "meu-canal"\n')
    assert lida.extras == {}
    assert lida.credenciais_prefixo == "meu-canal"


@pytest.mark.parametrize("texto, trecho", [
    ('[pastas]\ncortez = "x"\n', "cortez"),
    ('[identidade]\nencerramentos = "fim.mp4"\n', "encerramentos"),
    ('[pastas]\ncortes = "."\n', "pasta de programas"),
    ("[credenciais]\nprefixo = 3\n", "credenciais_prefixo"),
])
def test_erros_das_secoes_novas_sao_erros_de_config(tmp_path, texto, trecho):
    with pytest.raises(config.ErroConfig, match="clipline.toml") as erro:
        _ler(tmp_path, texto)
    assert trecho in str(erro.value)


def test_sem_prefixo_os_nomes_de_sempre(monkeypatch):
    monkeypatch.setattr(config, "atual", lambda: config.Config())
    assert config.servico_de_credenciais() == "tudo-e-politica"
    assert config.servico_de_credenciais("imagens") == "tudo-e-politica-imagens"
    assert config.servico_de_credenciais("painel") == "tudo-e-politica-painel"
