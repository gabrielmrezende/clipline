from esteira import cli
from esteira.musica import Faixa, credito, gravar_catalogo
from tests.auxiliares import preparar_episodio_teste, preparar_teste

BOM = {"numero": 1, "titulo": "Bom corte", "inicio": 1.0, "fim": 62.9, "clima": "leve"}
OUTRO = {**BOM, "numero": 2, "titulo": "Outro"}


def test_imagens_com_receita_ilegivel_nao_para_os_outros(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM, OUTRO])
    preparar_teste(pasta)
    (pasta / "01-bom-corte" / "montagem.json").write_text("{quebrado", "utf-8")
    assert cli.principal(["imagens", str(pasta)]) == 1
    saida = capsys.readouterr().out
    assert "01: erro: " in saida
    assert "02: 0 imagens" in saida


def test_imagens_sem_erros_retorna_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_teste(pasta)
    assert cli.principal(["imagens", str(pasta)]) == 0


def test_cli_musica(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    monkeypatch.setattr(cli, "MUSICAS", tmp_path / "musicas")
    novo = {**BOM, "numero": 3, "titulo": "Novo"}
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM, {**OUTRO, "clima": "tenso"}, novo])
    preparar_teste(pasta, {1, 2})
    gravar_catalogo(tmp_path / "musicas", [Faixa("Alegre", "leve", 200.0, "leve/Alegre.mp3", credito("Alegre"))])
    assert cli.principal(["musica", str(pasta)]) == 1
    saida = capsys.readouterr().out
    assert "01: Alegre" in saida
    assert "02: sem música para o clima tenso" in saida
    assert "03: erro: montagem.json não encontrado, rode preparar" in saida
    assert cli.principal(["musica", str(pasta), "--numero", "1"]) == 0
    assert capsys.readouterr().out == "01: Alegre\n"
