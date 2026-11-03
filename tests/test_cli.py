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


def _proposta_falsa(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "MUSICAS", tmp_path / "musicas")
    monkeypatch.setattr(cli, "baixar_catalogo", lambda: [])
    monkeypatch.setattr(cli, "propor", lambda pecas: {"leve": [
        {"filename": "A.mp3", "title": "A", "length": "1:00"},
    ]})


def test_musicas_propor_recusa_sobrescrever_aprovadas(tmp_path, monkeypatch, capsys):
    _proposta_falsa(monkeypatch, tmp_path)
    aprovadas = tmp_path / "musicas" / "aprovadas.json"
    aprovadas.parent.mkdir()
    aprovadas.write_text('{"tenso": ["X.mp3"]}', "utf-8")
    assert cli.principal(["musicas", "propor"]) == 1
    assert "--forcar" in capsys.readouterr().err
    assert aprovadas.read_text("utf-8") == '{"tenso": ["X.mp3"]}'
    assert not (tmp_path / "musicas" / "proposta.md").exists()
    assert cli.principal(["musicas", "propor", "--forcar"]) == 0
    assert "A.mp3" in aprovadas.read_text("utf-8")


def test_musicas_propor_sem_aprovadas_grava(tmp_path, monkeypatch, capsys):
    _proposta_falsa(monkeypatch, tmp_path)
    assert cli.principal(["musicas", "propor"]) == 0
    assert (tmp_path / "musicas" / "aprovadas.json").exists()


def test_musicas_baixar_retorna_um_com_erros(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "MUSICAS", tmp_path / "musicas")
    monkeypatch.setattr(cli, "baixar_catalogo", lambda: [])
    monkeypatch.setattr(cli, "ler_catalogo", lambda pasta: [])
    monkeypatch.setattr(cli, "baixar_musicas", lambda *a: ["erro: X.mp3"])
    assert cli.principal(["musicas", "baixar"]) == 1
    assert "erro: X.mp3" in capsys.readouterr().out
    monkeypatch.setattr(cli, "baixar_musicas", lambda *a: [])
    assert cli.principal(["musicas", "baixar"]) == 0
