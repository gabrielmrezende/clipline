import json

import pytest

from esteira import cli
from esteira.imagens_ia import chaves, config
from esteira.imagens_ia.provedor import ErroImagem


class KeyringFalso:
    def __init__(self):
        self.dados = {}

    def get_password(self, servico, campo):
        return self.dados.get((servico, campo))

    def set_password(self, servico, campo, valor):
        self.dados[(servico, campo)] = valor


@pytest.fixture
def keyring_falso(monkeypatch):
    falso = KeyringFalso()
    monkeypatch.setattr(chaves, "_keyring", lambda: falso)
    return falso


def test_config_ausente_devolve_padrao(tmp_path):
    cfg = config.ler_config(tmp_path / "nao-existe.json")
    assert cfg.provedor == "openai"
    assert set(cfg.provedores) == set(config.PROVEDORES)
    for dados in cfg.provedores.values():
        assert {"modelo", "qualidade", "preco_usd"} <= set(dados)


def test_config_ida_e_volta(tmp_path):
    caminho = tmp_path / "imagens-ia.json"
    cfg = config.ler_config(tmp_path / "x.json")
    cfg.provedor = "google"
    cfg.provedores["google"]["preco_usd"] = 0.5
    config.gravar_config(cfg, caminho, base=tmp_path)
    lido = config.ler_config(caminho)
    assert lido.provedor == "google"
    assert lido.provedores["google"]["preco_usd"] == 0.5


def test_gravar_em_lf(tmp_path):
    caminho = tmp_path / "imagens-ia.json"
    config.gravar_config(config.padrao(), caminho, base=tmp_path)
    conteudo = caminho.read_bytes()
    assert b"\n" in conteudo and b"\r\n" not in conteudo


def test_gravar_so_campos_conhecidos(tmp_path):
    caminho = tmp_path / "imagens-ia.json"
    cfg = config.padrao()
    cfg.provedores["openai"]["chave"] = "sk-x"
    cfg.provedores["google"]["token"] = "sk-y"
    config.gravar_config(cfg, caminho, base=tmp_path)
    texto = caminho.read_text(encoding="utf-8")
    assert "sk-x" not in texto and "sk-y" not in texto
    assert json.loads(texto)["provedores"] == config.padrao().provedores


@pytest.mark.parametrize("campo", ["modelo", "qualidade"])
def test_gravar_modelo_e_qualidade_sao_texto(tmp_path, campo):
    cfg = config.padrao()
    cfg.provedores["openai"][campo] = 5
    with pytest.raises(ErroImagem, match="de openai deve ser texto"):
        config.gravar_config(cfg, tmp_path / "c.json", base=tmp_path)
    assert not (tmp_path / "c.json").exists()


def test_gravar_provedor_invalido(tmp_path):
    cfg = config.Config("midjourney", {})
    with pytest.raises(ErroImagem):
        config.gravar_config(cfg, tmp_path / "c.json", base=tmp_path)


def test_gravar_preco_negativo_ou_texto(tmp_path):
    for preco in (-1, "caro"):
        cfg = config.ler_config(tmp_path / "x.json")
        cfg.provedores["openai"]["preco_usd"] = preco
        with pytest.raises(ErroImagem):
            config.gravar_config(cfg, tmp_path / "c.json", base=tmp_path)
    assert not (tmp_path / "c.json").exists()


def test_config_ilegivel(tmp_path):
    caminho = tmp_path / "c.json"
    caminho.write_text("{quebrado", encoding="utf-8")
    with pytest.raises(ErroImagem, match="imagens-ia.json ilegível"):
        config.ler_config(caminho)
    caminho.write_text("[1]", encoding="utf-8")
    with pytest.raises(ErroImagem, match="imagens-ia.json ilegível"):
        config.ler_config(caminho)


def test_config_completa_provedor_faltando(tmp_path):
    caminho = tmp_path / "c.json"
    caminho.write_text(json.dumps({"provedor": "google", "provedores": {"google": {"modelo": "m", "qualidade": "1K", "preco_usd": 1}}}), encoding="utf-8")
    cfg = config.ler_config(caminho)
    assert cfg.provedores["google"]["modelo"] == "m"
    assert cfg.provedores["openai"]["modelo"]


def test_arquivo_inicial_bate_com_padrao():
    lido = json.loads(config.ARQUIVO.read_text(encoding="utf-8"))
    assert lido["provedor"] == "openai"
    assert lido["provedores"] == config.padrao().provedores


def test_provedor_atual_usa_fabrica(tmp_path):
    cfg = config.ler_config(tmp_path / "x.json")
    cfg.provedor = "google"
    recebido = {}

    def fabrica(dados):
        recebido.update(dados)
        return "provedor-google"

    assert config.provedor_atual(cfg, {"google": fabrica}) == "provedor-google"
    assert recebido["modelo"] == cfg.provedores["google"]["modelo"]


def test_chaves_ida_e_volta(keyring_falso):
    assert chaves.tem_chave("openai") is False
    assert chaves.ler_chave("openai") is None
    chaves.gravar_chave("openai", "sk-segredo")
    assert chaves.ler_chave("openai") == "sk-segredo"
    assert chaves.tem_chave("openai") is True
    assert chaves.tem_chave("google") is False
    assert (chaves.SERVICO, "openai:chave") in keyring_falso.dados


def test_cli_conectar_grava_sem_imprimir(keyring_falso, monkeypatch, capsys):
    pedidos = []
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: pedidos.append(prompt) or "  sk-segredo  ")
    codigo = cli.principal(["imagens", "conectar", "openai"])
    saida = capsys.readouterr()
    assert codigo == 0
    assert pedidos == ["Chave da API (openai): "]
    assert chaves.ler_chave("openai") == "sk-segredo"
    assert "Chave da openai guardada no Windows." in saida.out
    assert "sk-segredo" not in saida.out + saida.err


def test_cli_conectar_chave_vazia(keyring_falso, monkeypatch, capsys):
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "   ")
    assert cli.principal(["imagens", "conectar", "google"]) == 1
    assert chaves.tem_chave("google") is False
    assert "vazia" in capsys.readouterr().err


def test_cli_conectar_provedor_desconhecido(keyring_falso, capsys):
    assert cli.principal(["imagens", "conectar", "midjourney"]) == 2
    assert "midjourney" in capsys.readouterr().err
