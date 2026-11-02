from esteira import cli
from esteira.cortar import preparar_episodio
from tests.auxiliares import preparar_episodio_teste

BOM = {"numero": 1, "titulo": "Bom corte", "inicio": 1.0, "fim": 62.9, "clima": "leve"}
OUTRO = {**BOM, "numero": 2, "titulo": "Outro"}


def test_imagens_com_receita_ilegivel_nao_para_os_outros(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM, OUTRO])
    preparar_episodio(pasta, nomes=[])
    (pasta / "01-bom-corte" / "montagem.json").write_text("{quebrado", "utf-8")
    assert cli.principal(["imagens", str(pasta)]) == 1
    saida = capsys.readouterr().out
    assert "01: erro: " in saida
    assert "02: 0 imagens" in saida


def test_imagens_sem_erros_retorna_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_episodio(pasta, nomes=[])
    assert cli.principal(["imagens", str(pasta)]) == 0
