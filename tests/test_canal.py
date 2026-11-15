"""`clipline init`: layout de um canal novo, sem sobrescrever nada."""

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from esteira import caminhos, canal, cli, config

REPOSITORIO = Path(__file__).resolve().parent.parent
EXEMPLO = REPOSITORIO / "Contexto.exemplo"


def _clone(tmp_path, nome="Meu Canal") -> Path:
    """Um repositório de mentira dentro da pasta do canal, como o README manda clonar."""
    automacao = tmp_path / nome / "Automacao"
    automacao.mkdir(parents=True)
    return automacao


def _args(*flags) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    canal.registrar(parser.add_subparsers())
    return parser.parse_args(["init", *flags])


def _canal(**mudancas) -> canal.Canal:
    base = canal.Canal(nome="Meu Canal", arroba="@meucanal", perfil_tiktok="https://www.tiktok.com/@meucanal")
    for chave, valor in mudancas.items():
        setattr(base, chave, valor)
    return base


@pytest.fixture
def repositorio_falso(tmp_path, monkeypatch):
    """O init rodando pela CLI aponta para um repositório de mentira: nunca grava o clipline.toml de verdade."""
    automacao = _clone(tmp_path)
    monkeypatch.setattr(canal, "AUTOMACAO", automacao)
    monkeypatch.setattr(canal, "EXEMPLO_CONTEXTO", EXEMPLO)
    monkeypatch.delenv("CLIPLINE_RAIZ", raising=False)
    return automacao


def test_toml_gerado_e_valido_e_tem_o_canal(tmp_path):
    texto = canal.texto_do_toml(_canal(duracao_minima=45, duracao_maxima=90.5), None, [], canal.LOGO_NOVA)
    arquivo = tmp_path / "clipline.toml"
    arquivo.write_text(texto, "utf-8")
    lida = config.ler(arquivo)
    assert (lida.canal, lida.arroba) == ("Meu Canal", "@meucanal")
    assert lida.perfil_tiktok == "https://www.tiktok.com/@meucanal"
    assert (lida.duracao_minima, lida.duracao_maxima, lida.credenciais_prefixo) == (45.0, 90.5, "meu-canal")
    assert lida.extras == {}
    pastas = caminhos.resolver(tomllib.loads(texto), {}, tmp_path / "Canal" / "Automacao")
    assert pastas.origem_raiz == "padrão" and pastas.encerramentos == ()
    assert pastas.logo == tmp_path / "Canal" / "3 - Identidade" / "Logos" / "logo.png"
    assert pastas.sobreposicao == tmp_path / "Canal" / "Automacao" / "assets" / "encerramento.png"


def test_toml_com_aspas_e_barras_no_nome(tmp_path):
    especial = _canal(nome='Canal "Ação" \\ 2', pastas={**caminhos.PASTAS_PADRAO, "cortes": "Saída 'nova'"})
    texto = canal.texto_do_toml(especial, "D:/Canais/Ação", ["Encerramentos/fim (1).mp4"], "Logos/logo.png")
    dados = tomllib.loads(texto)
    assert dados["canal"]["nome"] == 'Canal "Ação" \\ 2'
    assert dados["pastas"]["raiz"] == "D:/Canais/Ação" and dados["pastas"]["cortes"] == "Saída 'nova'"
    assert dados["identidade"]["encerramentos"] == ["Encerramentos/fim (1).mp4"]
    assert dados["credenciais"]["prefixo"] == "canal-acao-2"


def test_init_ao_redor_do_clone(tmp_path):
    automacao = _clone(tmp_path)
    raiz = automacao.parent
    relatorio = canal.iniciar(raiz, _canal(), automacao, EXEMPLO)
    assert relatorio.toml_criado
    for nome in ("Contexto", "1 - Programas", "2 - Cortes", "3 - Identidade/Encerramentos", "3 - Identidade/Logos"):
        assert (raiz / nome).is_dir(), nome
    assert sorted(a.name for a in (raiz / "Contexto").iterdir()) == sorted(a.name for a in EXEMPLO.iterdir())
    dados = tomllib.loads((automacao / "clipline.toml").read_text("utf-8"))
    assert "raiz" not in dados["pastas"]  # a de sempre: a pasta acima do repositório
    pastas = caminhos.carregar(automacao / "clipline.toml", {}, automacao)
    assert (pastas.raiz, pastas.cortes) == (raiz, raiz / "2 - Cortes")
    assert config.ler(automacao / "clipline.toml").canal == "Meu Canal"


def test_init_numa_pasta_escolhida_aponta_a_raiz(tmp_path):
    automacao = _clone(tmp_path)
    escolhida = tmp_path / "Canais" / "Outro Canal"
    nomes = {**caminhos.PASTAS_PADRAO, "programas": "Episódios", "cortes": "Saída/Cortes"}
    canal.iniciar(escolhida, _canal(pastas=nomes), automacao, EXEMPLO)
    assert (escolhida / "Episódios").is_dir() and (escolhida / "Saída" / "Cortes").is_dir()
    pastas = caminhos.carregar(automacao / "clipline.toml", {}, automacao)
    assert (pastas.raiz, pastas.origem_raiz) == (escolhida, "clipline.toml")
    assert pastas.cortes == escolhida / "Saída" / "Cortes"
    assert not (automacao.parent / "2 - Cortes").exists()


def test_init_nunca_sobrescreve(tmp_path):
    automacao = _clone(tmp_path)
    raiz = automacao.parent
    (raiz / "Contexto").mkdir()
    (raiz / "Contexto" / "canal.md").write_text("regras do dono", "utf-8")
    (automacao / "clipline.toml").write_text('[canal]\nnome = "Do dono"\n', "utf-8")
    relatorio = canal.iniciar(raiz, _canal(), automacao, EXEMPLO)
    assert not relatorio.toml_criado
    assert (automacao / "clipline.toml").read_text("utf-8") == '[canal]\nnome = "Do dono"\n'
    assert [a.name for a in (raiz / "Contexto").iterdir()] == ["canal.md"]  # nada de regra de exemplo misturada
    assert (raiz / "Contexto" / "canal.md").read_text("utf-8") == "regras do dono"
    assert ("já existe (mantido como está)", automacao / "clipline.toml") in relatorio.linhas


def test_contexto_vazio_recebe_o_modelo(tmp_path):
    automacao = _clone(tmp_path)
    (automacao.parent / "Contexto").mkdir()  # o README antigo mandava criar a pasta vazia
    canal.iniciar(automacao.parent, _canal(), automacao, EXEMPLO)
    assert (automacao.parent / "Contexto" / "glossario.md").is_file()


def test_init_duas_vezes_nao_muda_nada(tmp_path):
    automacao = _clone(tmp_path)
    canal.iniciar(automacao.parent, _canal(), automacao, EXEMPLO)
    antes = (automacao / "clipline.toml").read_bytes()
    segundo = canal.iniciar(automacao.parent, None, automacao, EXEMPLO)
    assert (automacao / "clipline.toml").read_bytes() == antes
    assert all(estado.startswith("já existe") for estado, _ in segundo.linhas)


@pytest.mark.parametrize("dentro", [".", "canal"])
def test_recusa_pasta_do_canal_dentro_do_repositorio(tmp_path, dentro):
    automacao = _clone(tmp_path)
    with pytest.raises(canal.ErroInit, match="dentro do repositório"):
        canal.iniciar(automacao / dentro, _canal(), automacao, EXEMPLO)
    assert not (automacao / "clipline.toml").exists()


def test_recusa_canal_invalido_antes_de_criar_qualquer_coisa(tmp_path):
    automacao = _clone(tmp_path)
    with pytest.raises(canal.ErroInit, match="arroba inválida"):
        canal.iniciar(automacao.parent / "Novo", _canal(arroba="@com espaço"), automacao, EXEMPLO)
    with pytest.raises(caminhos.ErroPastas, match="pasta de programas"):
        canal.iniciar(automacao.parent / "Novo", _canal(pastas={**caminhos.PASTAS_PADRAO, "cortes": "."}),
                      automacao, EXEMPLO)
    assert not (automacao.parent / "Novo").exists()


def test_encontra_os_encerramentos_e_a_logo_que_ja_estao_la(tmp_path):
    identidade = tmp_path / "3 - Identidade"
    (identidade / "Encerramentos").mkdir(parents=True)
    (identidade / "Logos").mkdir()
    assert canal.encerramentos_encontrados(identidade) == []
    assert canal.logo_encontrada(identidade) == "Logos/logo.png"
    for nome in ("b.mp4", "A.MOV", "notas.txt"):
        (identidade / "Encerramentos" / nome).write_bytes(b"")
    (identidade / "Logos" / "Marca.png").write_bytes(b"")
    assert canal.encerramentos_encontrados(identidade) == ["Encerramentos/A.MOV", "Encerramentos/b.mp4"]
    assert canal.logo_encontrada(identidade) == "Logos/Marca.png"


def test_encerramentos_do_canal_original_mantem_o_rodizio(tmp_path):
    identidade = tmp_path / "3 - Identidade"
    (identidade / "Encerramentos").mkdir(parents=True)
    for relativo in caminhos.ENCERRAMENTOS_PADRAO:
        (identidade / relativo).write_bytes(b"")
    (identidade / caminhos.LOGO_PADRAO).parent.mkdir()
    (identidade / caminhos.LOGO_PADRAO).write_bytes(b"")
    assert canal.encerramentos_encontrados(identidade) == list(caminhos.ENCERRAMENTOS_PADRAO)
    assert canal.logo_encontrada(identidade) == caminhos.LOGO_PADRAO


def test_o_canal_original_pelo_init_fica_igual_ao_de_hoje(tmp_path):
    """O dono rodando init com o próprio canal: mesmas pastas, encerramentos, logo, sobreposição e credenciais."""
    automacao = _clone(tmp_path)
    identidade = automacao.parent / "3 - Identidade"
    for relativo in (*caminhos.ENCERRAMENTOS_PADRAO, caminhos.LOGO_PADRAO):
        (identidade / relativo).parent.mkdir(parents=True, exist_ok=True)
        (identidade / relativo).write_bytes(b"")
    original = config.Config()
    proprio = canal.Canal(nome=original.canal, arroba=original.arroba, perfil_tiktok=original.perfil_tiktok)
    canal.iniciar(automacao.parent, proprio, automacao, EXEMPLO)
    assert caminhos.carregar(automacao / "clipline.toml", {}, automacao) == caminhos.resolver({}, {}, automacao)
    lida = config.ler(automacao / "clipline.toml")
    assert lida == original


def test_perguntas_preenchem_o_que_falta(repositorio_falso, capsys):
    respostas = iter(["", "Canal da Ana", "anapolitica", "", "45", "noventa", "90"])
    perguntas = []

    def perguntar(rotulo, padrao):
        perguntas.append((rotulo, padrao))
        return next(respostas) or padrao

    assert canal.executar(_args("--programas", "Episódios"), perguntar) == 0
    lida = config.ler(repositorio_falso / "clipline.toml")
    assert (lida.canal, lida.arroba, lida.perfil_tiktok) == (
        "Canal da Ana", "@anapolitica", "https://www.tiktok.com/@anapolitica")
    assert (lida.duracao_minima, lida.duracao_maxima, lida.credenciais_prefixo) == (45.0, 90.0, "canal-da-ana")
    assert perguntas[0] == ("Pasta do canal", str(repositorio_falso.parent))
    assert perguntas[2] == ("Arroba nas redes", "@canaldaana")
    assert (repositorio_falso.parent / "Episódios").is_dir()
    saida = capsys.readouterr().out
    assert "não é um número" in saida and "Próximos passos:" in saida and "doctor" in saida and "transcrever" in saida


def test_flags_nao_perguntam(repositorio_falso):
    def perguntar(rotulo, padrao):
        raise AssertionError(f"perguntou {rotulo}")

    flags = ["--canal", "Política Já", "--arroba", "@politicaja", "--perfil-tiktok", "https://tiktok.com/@pj",
             "--duracao-minima", "30", "--duracao-maxima", "75", "--prefixo-credenciais", "pj"]
    assert canal.executar(_args(str(repositorio_falso.parent), *flags), perguntar) == 0
    lida = config.ler(repositorio_falso / "clipline.toml")
    assert (lida.canal, lida.arroba, lida.perfil_tiktok) == ("Política Já", "@politicaja", "https://tiktok.com/@pj")
    assert (lida.duracao_minima, lida.duracao_maxima, lida.credenciais_prefixo) == (30.0, 75.0, "pj")


def test_sem_perguntas_usa_padroes_do_nome_da_pasta(repositorio_falso):
    def perguntar(rotulo, padrao):
        raise AssertionError(f"perguntou {rotulo}")

    assert canal.executar(_args("--sem-perguntas"), perguntar) == 0
    lida = config.ler(repositorio_falso / "clipline.toml")
    assert (lida.canal, lida.arroba, lida.credenciais_prefixo) == ("Meu Canal", "@meucanal", "meu-canal")
    assert (lida.duracao_minima, lida.duracao_maxima) == (60.0, 120.0)
    assert (repositorio_falso.parent / "2 - Cortes").is_dir()


def test_sem_terminal_fica_o_padrao(monkeypatch):
    def sem_entrada(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", sem_entrada)
    assert canal.perguntar_no_terminal("Nome do canal", "Meu Canal") == "Meu Canal"


def test_toml_existente_so_cria_pastas_e_avisa_raiz_diferente(repositorio_falso, tmp_path, capsys):
    (repositorio_falso / "clipline.toml").write_text('[canal]\nnome = "Do dono"\n', "utf-8")
    outra = tmp_path / "Outra"
    assert canal.executar(_args(str(outra), "--sem-perguntas")) == 0
    assert (outra / "2 - Cortes").is_dir()
    assert (repositorio_falso / "clipline.toml").read_text("utf-8") == '[canal]\nnome = "Do dono"\n'
    saida = capsys.readouterr().out
    assert "já existe" in saida and f'raiz = "{outra.as_posix()}"' in saida


def test_erro_vira_mensagem_e_codigo_1(repositorio_falso, capsys):
    assert canal.executar(_args(str(repositorio_falso), "--sem-perguntas")) == 1
    assert capsys.readouterr().err.startswith("Erro: a pasta do canal não pode ficar dentro do repositório")


def test_cli_init_e_iniciar(repositorio_falso, capsys):
    assert cli.principal(["iniciar", "--sem-perguntas", "--canal", "Canal X", "--arroba", "@x"]) == 0
    assert config.ler(repositorio_falso / "clipline.toml").arroba == "@x"
    assert cli.principal(["init", "--sem-perguntas"]) == 0  # de novo: nada muda
    assert "já existe" in capsys.readouterr().out


def test_init_roda_sem_as_dependencias_da_esteira():
    """`python -m esteira init` não importa a CLI (que puxa Pillow, OpenCV...): roda antes do venv."""
    codigo = (
        "import runpy, sys\n"
        "sys.argv = ['esteira', 'init', '--help']\n"
        "try:\n"
        "    runpy.run_module('esteira', run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "print(sorted(m for m in ('PIL', 'cv2', 'numpy', 'esteira.cli') if m in sys.modules))\n"
    )
    feito = subprocess.run([sys.executable, "-c", codigo], cwd=REPOSITORIO, capture_output=True, text=True,
                           encoding="utf-8", timeout=60, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert feito.returncode == 0, feito.stderr
    assert "--sem-perguntas" in feito.stdout
    assert feito.stdout.strip().splitlines()[-1] == "[]"
