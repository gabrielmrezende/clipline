"""doctor mostra as pastas e a identidade em uso; a CLI para quando o clipline.toml está quebrado."""

import json

from esteira import caminhos, cli, config, diagnostico


def _por_nome(itens):
    return {i.nome: i for i in itens}


def test_doctor_mostra_pastas_e_identidade():
    itens = _por_nome(diagnostico.doctor(ler_credencial=lambda servico, campo: None))
    for nome in ("clipline.toml", "pasta raiz", "pasta de contexto", "glossário", "pasta de programas",
                 "pasta de cortes", "pasta de identidade", "identidade do canal", "encerramentos", "logo",
                 "sobreposição", "credenciais"):
        assert nome in itens, nome
    assert str(caminhos.CORTES) in itens["pasta de cortes"].detalhe
    assert str(caminhos.RAIZ) in itens["pasta raiz"].detalhe


def test_identidade_do_canal_original_pede_init(monkeypatch):
    itens = _por_nome(diagnostico._identidade(config.Config()))
    assert itens["identidade do canal"].estado == "aviso"
    assert "Tudo é Política" in itens["identidade do canal"].detalhe
    assert "clipline init" in itens["identidade do canal"].detalhe
    assert itens["credenciais"].detalhe.startswith("prefixo tudo-e-politica (padrão)")


def test_identidade_de_outro_canal_fica_ok(monkeypatch, tmp_path):
    padrao = tmp_path / "assets" / "encerramento.png"
    monkeypatch.setattr(caminhos, "AUTOMACAO", tmp_path)
    monkeypatch.setattr(caminhos, "SOBREPOSICAO_PADRAO", padrao)
    monkeypatch.setattr(caminhos, "SOBREPOSICAO", padrao)
    monkeypatch.setattr(caminhos, "ENCERRAMENTOS", [])
    monkeypatch.setattr(caminhos, "LOGO", tmp_path / "logo.png")
    ajustes = config.Config(canal="Canal da Ana", arroba="@ana", credenciais_prefixo="ana")
    itens = _por_nome(diagnostico._identidade(ajustes))
    assert (itens["identidade do canal"].estado, itens["identidade do canal"].detalhe) == ("ok", "Canal da Ana (@ana)")
    assert itens["encerramentos"].detalhe.startswith("nenhum")
    assert itens["logo"].estado == "aviso" and "não encontrada" in itens["logo"].detalhe
    assert itens["sobreposição"].detalhe.startswith(str(tmp_path / "assets" / "encerramento-ana.png"))
    assert "primeira montagem" in itens["sobreposição"].detalhe
    assert itens["credenciais"].detalhe.startswith("prefixo ana no")


def test_pastas_que_faltam(monkeypatch, tmp_path):
    monkeypatch.setattr(caminhos, "RAIZ", tmp_path / "nao-existe")
    monkeypatch.setattr(caminhos, "CONTEXTO", tmp_path / "nao-existe" / "Contexto")
    monkeypatch.setattr(caminhos, "PROGRAMAS", tmp_path / "nao-existe" / "Programas")
    itens = _por_nome(diagnostico._pastas())
    assert itens["pasta raiz"].estado == "falta" and "clipline init" in itens["pasta raiz"].detalhe
    assert itens["pasta de contexto"].estado == "falta"
    assert itens["pasta de programas"].estado == "aviso"


def test_toml_quebrado_aparece_no_doctor(monkeypatch):
    monkeypatch.setattr(caminhos, "ERRO_CONFIG", "clipline.toml: [pastas] cortez não existe")
    itens, ajustes = diagnostico._configuracao()
    assert ajustes is None
    assert (itens[0].nome, itens[0].estado) == ("clipline.toml", "falta")
    assert "cortez" in itens[0].detalhe
    assert "identidade do canal" not in _por_nome(diagnostico._identidade(None))


def test_config_quebrada_nao_derruba_o_doctor(monkeypatch):
    def quebrada():
        raise config.ErroConfig("clipline.toml: legenda_estilo deve ser um destes: fixa, palavra")

    monkeypatch.setattr(config, "atual", quebrada)
    itens, ajustes = diagnostico._configuracao()
    assert ajustes is None and itens[0].estado == "falta"
    assert diagnostico._credenciais(lambda servico, campo: None) == []


def test_cli_para_com_toml_quebrado_menos_no_doctor_e_no_init(monkeypatch, capsys):
    monkeypatch.setattr(caminhos, "ERRO_CONFIG", "clipline.toml ilegível: linha 3")
    assert cli.principal(["status"]) == 1
    erro = capsys.readouterr().err
    assert erro.startswith("Erro: clipline.toml ilegível: linha 3") and "Traceback" not in erro
    monkeypatch.setattr(diagnostico, "doctor", lambda: [diagnostico.Item("clipline.toml", "falta", "ilegível")])
    assert cli.principal(["doctor", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == [{"nome": "clipline.toml", "estado": "falta", "detalhe": "ilegível"}]


def test_cli_para_com_config_invalida(monkeypatch, capsys):
    def quebrada():
        raise config.ErroConfig("clipline.toml: duracao_minima precisa ser positiva e menor que duracao_maxima")

    monkeypatch.setattr(config, "atual", quebrada)
    assert cli.principal(["status"]) == 1
    assert "duracao_minima" in capsys.readouterr().err


def test_nomes_das_credenciais_seguem_o_prefixo(monkeypatch):
    from esteira.imagens_ia import chaves
    from esteira.painel import acesso
    from esteira.publicar import credenciais

    assert (chaves.servico(), acesso.servico(), credenciais.servico()) == (
        "tudo-e-politica-imagens", "tudo-e-politica-painel", "tudo-e-politica")
    assert (chaves.SERVICO, acesso.SERVICO, credenciais.SERVICO) == (
        chaves.servico(), acesso.servico(), credenciais.servico())
    monkeypatch.setattr(config, "atual", lambda: config.Config(credenciais_prefixo="canal-da-ana"))
    assert (chaves.servico(), acesso.servico(), credenciais.servico()) == (
        "canal-da-ana-imagens", "canal-da-ana-painel", "canal-da-ana")


def test_keyring_usa_o_nome_do_prefixo(monkeypatch):
    from esteira.imagens_ia import chaves
    from esteira.painel import acesso
    from esteira.publicar import credenciais

    guardado = {}

    class KeyringFalso:
        def get_password(self, servico, campo):
            return guardado.get((servico, campo))

        def set_password(self, servico, campo, valor):
            guardado[(servico, campo)] = valor

    falso = KeyringFalso()
    monkeypatch.setattr(config, "atual", lambda: config.Config(credenciais_prefixo="ana"))
    monkeypatch.setattr(chaves, "_keyring", lambda: falso)
    monkeypatch.setattr(credenciais, "_keyring", lambda: falso)
    monkeypatch.setattr(acesso.CofreKeyring, "_keyring", lambda self: falso)
    chaves.gravar_chave("openai", "k1")
    credenciais.gravar("youtube", "refresh_token", "k2")
    acesso.CofreKeyring().gravar("codigo", "k3")
    assert set(guardado) == {
        ("ana-imagens", "openai:chave"), ("ana", "youtube:refresh_token"), ("ana-painel", "codigo"),
    }
    assert chaves.ler_chave("openai") == "k1" and acesso.CofreKeyring().ler("codigo") == "k3"


def test_prefixo_vazio_e_recusado(tmp_path):
    import pytest

    arquivo = tmp_path / "clipline.toml"
    arquivo.write_text('[credenciais]\nprefixo = " "\n', "utf-8")
    with pytest.raises(config.ErroConfig, match="prefixo"):
        config.ler(arquivo)


def test_doctor_lista_os_extras_opcionais(monkeypatch):
    instalados = {"yt_dlp", "mcp"}
    monkeypatch.setattr(diagnostico, "_tem_modulo", lambda nome: nome in instalados)
    itens = {i.nome: i for i in diagnostico._opcionais()}
    assert itens["extra entrada"].estado == "ok"
    assert itens["extra mcp"].estado == "ok"
    assert itens["extra ia"].estado == "aviso" and ".[ia]" in itens["extra ia"].detalhe


def test_doctor_diz_se_a_chave_anthropic_existe_sem_mostrar():
    def ler(servico, campo):
        return "segredo" if campo == "anthropic:chave" else None

    itens = _por_nome(diagnostico.doctor(ler_credencial=ler))
    assert itens["chave anthropic"].estado == "ok"
    assert "segredo" not in str([i.detalhe for i in itens.values()])
