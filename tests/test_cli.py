import json

import pytest

from esteira import cli
from esteira.fluxo_imagens import ErroBusca
from esteira.musica import Faixa, credito, gravar_catalogo
from tests.auxiliares import preparar_episodio_teste, preparar_teste

BOM = {"numero": 1, "titulo": "Bom corte", "inicio": 1.0, "fim": 62.9, "clima": "leve"}
OUTRO = {**BOM, "numero": 2, "titulo": "Outro"}


def test_imagens_buscar_chama_fluxo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    chamadas = []

    def falso(pasta, numeros, pessoas):
        chamadas.append((pasta, numeros, pessoas))
        return {1: "ok"}

    monkeypatch.setattr(cli, "buscar_episodio", falso)
    assert cli.principal(["imagens", "buscar", str(tmp_path), "--numero", "1"]) == 0
    assert chamadas[0][1] == {1}
    assert isinstance(chamadas[0][2], list)
    assert "01: ok" in capsys.readouterr().out


def test_imagens_resumo_imprime_total(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    chamadas = []

    def falso(pasta, numeros, pessoas=None):
        chamadas.append((pasta, numeros, pessoas))
        return 3, 5 * 1_048_576, {1: "ok", 2: "erro: momento 1: escolhas inválidas"}

    monkeypatch.setattr(cli, "resumir_episodio", falso)
    assert cli.principal(["imagens", "resumo", str(tmp_path)]) == 1
    saida = capsys.readouterr().out
    assert "3 fotos, 5,0 MB, origem Wikimedia Commons" in saida
    assert "02: erro: momento 1: escolhas inválidas" in saida
    assert isinstance(chamadas[0][2], list)


def test_imagens_sugerir_chama_fluxo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    chamadas = []

    def falso(pasta, numeros, pessoas):
        chamadas.append((pasta, numeros))
        return {1: "ok"}

    monkeypatch.setattr(cli, "sugerir_episodio", falso)
    assert cli.principal(["imagens", "sugerir", str(tmp_path), "--numero", "1"]) == 0
    assert chamadas == [(tmp_path, {1})] and "01: ok" in capsys.readouterr().out


def test_imagens_sem_lista_nem_baixar(tmp_path):
    for acao in ("lista", "baixar"):
        with pytest.raises(SystemExit):
            cli.principal(["imagens", acao, str(tmp_path)])


def test_imagens_buscar_api_fora(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)

    def quebra(*a):
        raise ErroBusca("Wikimedia indisponível: x")

    monkeypatch.setattr(cli, "buscar_episodio", quebra)
    assert cli.principal(["imagens", "buscar", str(tmp_path)]) == 1
    assert "Wikimedia indisponível" in capsys.readouterr().err


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


def test_planos_chama_fluxo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    chamadas = []

    def falso(pasta, numeros, forcar, religar=False):
        chamadas.append((pasta, numeros, forcar, religar))
        return {1: "ok", 2: "mantido (já existe)", 3: "ok com alertas: 00:10 sem rosto"}

    monkeypatch.setattr(cli, "planejar_episodio", falso)
    assert cli.principal(["planos", str(tmp_path), "--numero", "1", "--forcar"]) == 0
    assert chamadas == [(tmp_path, {1}, True, False)]
    saida = capsys.readouterr().out
    assert "02: mantido (já existe)" in saida and "03: ok com alertas: 00:10 sem rosto" in saida
    assert cli.principal(["planos", str(tmp_path), "--religar"]) == 0
    assert chamadas[-1] == (tmp_path, None, True, True)


def test_planos_sem_vozes_retorna_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    monkeypatch.setattr(cli, "planejar_episodio", lambda p, n, f, **k: {0: "erro: vozes.json não encontrado"})
    assert cli.principal(["planos", str(tmp_path)]) == 1
    assert "vozes.json não encontrado" in capsys.readouterr().out


def test_planos_erro_em_um_corte_retorna_1(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    monkeypatch.setattr(cli, "planejar_episodio", lambda p, n, f, **k: {1: "ok", 2: "erro: x"})
    assert cli.principal(["planos", str(tmp_path)]) == 1


def test_escrita_proibida_vira_erro(tmp_path, capsys):
    assert cli.principal(["preparar", str(tmp_path)]) == 1
    saida = capsys.readouterr()
    assert saida.err.startswith("Erro: Escrita fora de 2 - Cortes/ e Automacao/")
    assert "Traceback" not in saida.err


def _episodio_com_ia(tmp_path):
    from esteira.pedidos import Momento, gravar_pedidos

    ep = tmp_path / "ep"
    corte = ep / "01-bom-corte"
    (corte / "trabalho").mkdir(parents=True)
    (ep / "aprovados.json").write_text(json.dumps({"cortes": [BOM]}), "utf-8")
    gravar_pedidos(corte / "trabalho", [Momento(52.0, 55.0, "f", "ia", "Turistas", prompt="praia", aprovado=True)])
    return ep, corte


class _ProvedorFalso:
    nome = "openai"

    def __init__(self):
        self.chamadas = 0

    def gerar(self, prompt, proporcao="9:16"):
        import io

        from PIL import Image

        self.chamadas += 1
        buffer = io.BytesIO()
        Image.new("RGB", (64, 96), (10, 10, 200)).save(buffer, "PNG")
        return buffer.getvalue()


def test_imagens_gerar_sem_confirmar_so_mostra_orcamento(tmp_path, monkeypatch, capsys):
    from esteira.imagens_ia.config import padrao

    ep, corte = _episodio_com_ia(tmp_path)
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    monkeypatch.setattr(cli, "ler_config", padrao)
    monkeypatch.setattr(cli, "provedor_atual", lambda config: pytest.fail("não deve construir o provedor"))
    assert cli.principal(["imagens", "gerar", str(ep)]) == 0
    assert "1 imagens, provedor openai, modelo gpt-image-2, custo estimado ~US$ 0.04" in capsys.readouterr().out
    assert not (corte / "imagens-sugeridas").exists()


def test_imagens_gerar_confirmar_gera(tmp_path, monkeypatch, capsys):
    from esteira.imagens_ia.config import padrao

    ep, corte = _episodio_com_ia(tmp_path)
    falso = _ProvedorFalso()
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    monkeypatch.setattr("esteira.caminhos.garantir_escrita", lambda caminho, base_extra=None: caminho)
    monkeypatch.setattr(cli, "ler_config", padrao)
    monkeypatch.setattr(cli, "provedor_atual", lambda config: falso)
    assert cli.principal(["imagens", "gerar", str(ep), "--confirmar"]) == 0
    saida = capsys.readouterr().out
    assert "Gerando 1 de 1…" in saida and "0052-turistas-ia-1.jpg" in saida
    assert falso.chamadas == 1
    assert (corte / "imagens-sugeridas" / "0052-turistas-ia-1.jpg").exists()


def test_cli_montar_sem_imagens_repassa(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    chamadas = []

    def falso(pasta, numeros, forcar, sem_imagens=False):
        chamadas.append((numeros, forcar, sem_imagens))
        return {1: "ok"}

    monkeypatch.setattr(cli, "montar_episodio", falso)
    assert cli.principal(["montar", str(tmp_path), "--numero", "1", "--forcar", "--sem-imagens"]) == 0
    assert cli.principal(["montar", str(tmp_path)]) == 0
    assert chamadas == [({1}, True, True), (None, False, False)]
