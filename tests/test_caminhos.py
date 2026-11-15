import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from esteira import caminhos
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

REPOSITORIO = Path(__file__).resolve().parent.parent


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


# --- pastas e identidade configuráveis ([pastas], [identidade], CLIPLINE_RAIZ) ---------------------------------


def _automacao(tmp_path) -> Path:
    return tmp_path / "Canal" / "Automacao"


def test_sem_configuracao_valem_as_pastas_de_sempre(tmp_path):
    automacao = _automacao(tmp_path)
    raiz = automacao.parent
    p = caminhos.resolver({}, {}, automacao)
    assert (p.raiz, p.origem_raiz) == (raiz, "padrão")
    assert (p.contexto, p.programas, p.cortes, p.identidade) == (
        raiz / "Contexto", raiz / "1 - Programas", raiz / "2 - Cortes", raiz / "3 - Identidade",
    )
    assert [str(e) for e in p.encerramentos] == [
        str(raiz / "3 - Identidade" / "Encerramentos" / f"Final Corte ({nome}).mp4")
        for nome in ("Gabriel 1", "Tigas 1", "Gabriel 2", "Tigas 2")
    ]
    assert str(p.logo) == str(raiz / "3 - Identidade" / "Logos" / "Logo sem Fundo.png")
    assert p.sobreposicao == automacao / "assets" / "encerramento.png"


@pytest.mark.skipif(bool(os.environ.get("CLIPLINE_RAIZ")) or caminhos.ARQUIVO_CONFIG.exists(),
                    reason="esta máquina tem configuração própria")
def test_constantes_sem_configuracao_sao_as_de_antes():
    raiz = caminhos.AUTOMACAO.parent
    assert caminhos.ERRO_CONFIG is None
    assert (caminhos.RAIZ, caminhos.CORTES, caminhos.PROGRAMAS) == (raiz, raiz / "2 - Cortes", raiz / "1 - Programas")
    assert (caminhos.CONTEXTO, caminhos.IDENTIDADE) == (raiz / "Contexto", raiz / "3 - Identidade")
    assert caminhos.ENCERRAMENTOS == list(caminhos.resolver({}, {}).encerramentos)
    assert len(caminhos.ENCERRAMENTOS) == 4
    assert caminhos.LOGO == raiz / "3 - Identidade" / "Logos" / "Logo sem Fundo.png"
    assert caminhos.SOBREPOSICAO == caminhos.SOBREPOSICAO_PADRAO == caminhos.AUTOMACAO / "assets" / "encerramento.png"


def test_exemplo_do_repositorio_da_as_pastas_padrao(tmp_path):
    dados = tomllib.loads((REPOSITORIO / "clipline.exemplo.toml").read_text("utf-8"))
    assert caminhos.resolver(dados, {}, _automacao(tmp_path)) == caminhos.resolver({}, {}, _automacao(tmp_path))


def test_pastas_relativas_a_raiz_e_raiz_relativa_ao_repositorio(tmp_path):
    automacao = _automacao(tmp_path)
    dados = {"pastas": {"raiz": "../../Outro", "cortes": "Saída/Cortes", "programas": "Episódios"}}
    p = caminhos.resolver(dados, {}, automacao)
    assert (p.raiz, p.origem_raiz) == (tmp_path / "Outro", "clipline.toml")
    assert p.cortes == tmp_path / "Outro" / "Saída" / "Cortes"
    assert p.programas == tmp_path / "Outro" / "Episódios"
    assert p.contexto == tmp_path / "Outro" / "Contexto"


def test_raiz_absoluta_e_pasta_absoluta(tmp_path):
    outra = tmp_path / "em outro disco"
    dados = {"pastas": {"raiz": str(outra), "contexto": str(tmp_path / "Regras")}}
    p = caminhos.resolver(dados, {}, _automacao(tmp_path))
    assert p.raiz == outra and p.contexto == tmp_path / "Regras" and p.cortes == outra / "2 - Cortes"


def test_variavel_de_ambiente_vence_o_toml(tmp_path):
    dados = {"pastas": {"raiz": str(tmp_path / "do-toml")}}
    p = caminhos.resolver(dados, {"CLIPLINE_RAIZ": str(tmp_path / "da-variavel")}, _automacao(tmp_path))
    assert (p.raiz, p.origem_raiz) == (tmp_path / "da-variavel", "CLIPLINE_RAIZ")
    assert p.cortes == tmp_path / "da-variavel" / "2 - Cortes"
    vazia = caminhos.resolver(dados, {"CLIPLINE_RAIZ": "  "}, _automacao(tmp_path))
    assert vazia.raiz == tmp_path / "do-toml"


def test_identidade_configurada(tmp_path):
    dados = {"identidade": {"encerramentos": ["Fim/a.mp4", "Fim/b.mp4"], "logo": "logo.png",
                            "sobreposicao": "por-cima.png"}}
    p = caminhos.resolver(dados, {}, _automacao(tmp_path))
    identidade = tmp_path / "Canal" / "3 - Identidade"
    assert p.encerramentos == (identidade / "Fim" / "a.mp4", identidade / "Fim" / "b.mp4")
    assert p.logo == identidade / "logo.png"
    assert p.sobreposicao == identidade / "por-cima.png"


def test_lista_vazia_tira_o_encerramento_e_texto_vazio_tira_a_sobreposicao(tmp_path):
    p = caminhos.resolver({"identidade": {"encerramentos": [], "sobreposicao": ""}}, {}, _automacao(tmp_path))
    assert p.encerramentos == () and p.sobreposicao is None


@pytest.mark.parametrize("dados, trecho", [
    ({"pastas": {"cortez": "x"}}, "cortez não existe"),
    ({"pastas": {"cortes": 3}}, "[pastas] cortes"),
    ({"pastas": {"raiz": ""}}, "[pastas] raiz"),
    ({"pastas": "x"}, "[pastas] precisa ser uma seção"),
    ({"identidade": {"encerramentos": "fim.mp4"}}, "encerramentos precisa ser uma lista"),
    ({"identidade": {"encerramentos": ["ok.mp4", ""]}}, "encerramentos precisa ser uma lista"),
    ({"identidade": {"logo": ""}}, "[identidade] logo"),
    ({"identidade": {"sobreposicao": False}}, "sobreposicao"),
    ({"pastas": {"cortes": "."}}, "pasta de programas"),
    ({"pastas": {"programas": "2 - Cortes/Programas"}}, "pasta de programas"),
    ({"pastas": {"raiz": "."}}, "nem do repositório"),
    ({"pastas": {"identidade": "Automacao/marca"}}, "pasta de identidade"),
])
def test_erros_claros_nas_pastas(tmp_path, dados, trecho):
    with pytest.raises(caminhos.ErroPastas, match="clipline.toml") as erro:
        caminhos.resolver(dados, {}, _automacao(tmp_path))
    assert trecho in str(erro.value)


def test_carregar_le_o_arquivo_e_recusa_toml_quebrado(tmp_path):
    arquivo = tmp_path / "clipline.toml"
    assert caminhos.carregar(arquivo, {}, _automacao(tmp_path)).origem_raiz == "padrão"
    arquivo.write_text(f'[pastas]\nraiz = "{(tmp_path / "Canal").as_posix()}"\n', "utf-8")
    assert caminhos.carregar(arquivo, {}, _automacao(tmp_path)).origem_raiz == "clipline.toml"
    arquivo.write_text("[pastas\n", "utf-8")
    with pytest.raises(caminhos.ErroPastas, match="clipline.toml ilegível"):
        caminhos.carregar(arquivo, {}, _automacao(tmp_path))


def test_garantir_escrita_recusa_tudo_com_a_configuracao_quebrada(monkeypatch):
    monkeypatch.setattr(caminhos, "ERRO_CONFIG", "clipline.toml ilegível: linha 2")
    with pytest.raises(EscritaProibida, match="Corrija o clipline.toml"):
        garantir_escrita(caminhos.CORTES / "x" / "a.json")


def test_garantir_escrita_segue_a_pasta_de_cortes_configurada(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "CORTES", tmp_path / "Saida")
    assert garantir_escrita(tmp_path / "Saida" / "ep" / "a.json")
    with pytest.raises(EscritaProibida, match="Escrita fora de Saida/"):
        garantir_escrita(tmp_path / "outra" / "a.json")


CODIGO_DAS_CONSTANTES = """
import json
from esteira import caminhos, cartao, cli, cortar, episodio
from esteira.painel import app
from esteira.publicar import comandos, rodar
print(json.dumps({
    "cli": [str(cli.CORTES), str(cli.CONTEXTO)],
    "episodio": str(episodio.criar_episodio.__defaults__[-1]),
    "rodar": str(rodar.rodar_tudo.__defaults__[0]),
    "comandos": str(comandos.CORTES),
    "cortar": [str(cortar.CONTEXTO), str(cortar.ENCERRAMENTOS[0])],
    "cartao": str(cartao.LOGO),
    "painel": str(app.CONTEXTO),
    "garantir": str(caminhos.garantir_escrita(caminhos.CORTES / "ep" / "a.json")),
}))
"""


def test_todos_os_modulos_usam_a_raiz_configurada(tmp_path):
    """Num processo novo, com CLIPLINE_RAIZ: as constantes e os padrões calculados na importação seguem a raiz."""
    pytest.importorskip("fastapi")
    raiz = tmp_path / "Meu Canal"
    ambiente = {**os.environ, "CLIPLINE_RAIZ": str(raiz), "PYTHONIOENCODING": "utf-8"}
    feito = subprocess.run([sys.executable, "-c", CODIGO_DAS_CONSTANTES], cwd=REPOSITORIO, env=ambiente,
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert feito.returncode == 0, feito.stderr
    saida = json.loads(feito.stdout)
    cortes, contexto, identidade = str(raiz / "2 - Cortes"), str(raiz / "Contexto"), raiz / "3 - Identidade"
    assert saida["cli"] == [cortes, contexto]
    assert saida["episodio"] == saida["rodar"] == saida["comandos"] == cortes
    assert saida["cortar"] == [contexto, str(identidade / "Encerramentos" / "Final Corte (Gabriel 1).mp4")]
    assert saida["cartao"] == str(identidade / "Logos" / "Logo sem Fundo.png")
    assert saida["painel"] == contexto
    assert Path(saida["garantir"]).is_relative_to(Path(cortes).resolve())


def test_sobreposicao_segue_a_arroba_quando_nao_configurada(monkeypatch):
    padrao = caminhos.AUTOMACAO / "assets" / "encerramento.png"
    monkeypatch.setattr(caminhos, "SOBREPOSICAO_PADRAO", padrao)
    monkeypatch.setattr(caminhos, "SOBREPOSICAO", padrao)
    assert caminhos.sobreposicao_do_canal("@tudoepoliticabr", "@tudoepoliticabr") == padrao
    assert caminhos.sobreposicao_do_canal("@Canal Ação", "@tudoepoliticabr") == (
        caminhos.AUTOMACAO / "assets" / "encerramento-canal-acao.png"
    )
    configurada = caminhos.AUTOMACAO.parent / "3 - Identidade" / "minha.png"
    monkeypatch.setattr(caminhos, "SOBREPOSICAO", configurada)
    assert caminhos.sobreposicao_do_canal("@outro", "@tudoepoliticabr") == configurada
    monkeypatch.setattr(caminhos, "SOBREPOSICAO", None)
    assert caminhos.sobreposicao_do_canal("@outro", "@tudoepoliticabr") is None


def test_variavel_de_ambiente_errada_nao_quebra_a_importacao():
    """CLIPLINE_RAIZ apontando para o próprio repositório: importa, avisa e a CLI para sem gravar nada."""
    codigo = "from esteira import caminhos, cli\nprint(caminhos.ERRO_CONFIG)\nraise SystemExit(cli.principal(['status']))\n"
    ambiente = {**os.environ, "CLIPLINE_RAIZ": ".", "PYTHONIOENCODING": "utf-8"}
    feito = subprocess.run([sys.executable, "-c", codigo], cwd=REPOSITORIO, env=ambiente, capture_output=True,
                           text=True, encoding="utf-8", timeout=120)
    assert feito.returncode == 1, feito.stderr
    assert feito.stdout.startswith("CLIPLINE_RAIZ: a pasta de programas")
    assert feito.stderr.startswith("Erro: CLIPLINE_RAIZ: a pasta de programas") and "Traceback" not in feito.stderr


def test_pasta_de_entrada_padrao_e_configurada(tmp_path):
    automacao = _automacao(tmp_path)
    assert caminhos.resolver({}, {}, automacao).entrada == automacao.parent / "0 - Entrada"
    dados = {"pastas": {"raiz": "../../Outro", "entrada": "Baixados"}}
    assert caminhos.resolver(dados, {}, automacao).entrada == tmp_path / "Outro" / "Baixados"


def test_a_entrada_do_baixar_segue_a_configuracao():
    from esteira import entrada

    assert entrada.PASTA == caminhos.ENTRADA
