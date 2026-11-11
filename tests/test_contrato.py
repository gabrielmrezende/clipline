import json

import pytest

from esteira import cli, contrato
from esteira.cortar import ler_aprovados
from esteira.diagnostico import status_episodio
from esteira.enquadrar import TrechoVoz
from esteira.falantes import rotular, texto_com_falantes
from esteira.modelos import Palavra


def _corte(**extra):
    return {"numero": 1, "titulo": "Pergunta?", "inicio": 10.0, "fim": 80.0, "clima": "leve", **extra}


def test_aprovados_valido_sem_problemas():
    assert contrato.conferir_aprovados({"cortes": [_corte(instagram=True, data="2026-12-01 18:00")]}) == []


def test_aprovados_aceita_origem():
    dados = {"origem": {"modelo": "claude", "data": "2026-11-11T10:00", "regras": "abc"}, "cortes": [_corte()]}
    assert contrato.conferir_aprovados(dados) == []


@pytest.mark.parametrize("corte, campo, trecho", [
    (_corte(nota=8), "cortes[0].nota", "campo desconhecido"),
    ({"numero": 1, "titulo": "x", "inicio": 1, "fim": 70}, "cortes[0].clima", "obrigatório"),
    (_corte(inicio="10"), "cortes[0].inicio", "precisa ser número"),
    (_corte(fim=5.0), "cortes[0].fim", "maior que inicio"),
    (_corte(instagram="sim"), "cortes[0].instagram", "true ou false"),
    (_corte(data="amanhã 18h"), "cortes[0].data", "AAAA-MM-DD HH:MM"),
    (_corte(numero=0), "cortes[0].numero", "maior que zero"),
    (_corte(titulo="  "), "cortes[0].titulo", "vazio"),
])
def test_aprovados_diz_campo_e_correcao(corte, campo, trecho):
    problemas = contrato.conferir_aprovados({"cortes": [corte]})
    assert any(p.campo == campo and trecho in p.mensagem for p in problemas), problemas


def test_numero_repetido():
    problemas = contrato.conferir_aprovados({"cortes": [_corte(), _corte()]})
    assert any("repetido" in p.mensagem for p in problemas)


def test_clima_conferido_quando_pedido():
    problemas = contrato.conferir_aprovados({"cortes": [_corte(clima="feliz")]}, climas=("leve", "tenso"))
    assert any(p.campo == "cortes[0].clima" for p in problemas)


def test_ler_aprovados_com_campo_inventado_da_erro_legivel(tmp_path):
    (tmp_path / "aprovados.json").write_text(json.dumps({"cortes": [_corte(nota=9)]}), "utf-8")
    with pytest.raises(contrato.ErroContrato, match=r"cortes\[0\]\.nota: campo desconhecido"):
        ler_aprovados(tmp_path)
    with pytest.raises(ValueError):  # quem já tratava ValueError continua tratando
        ler_aprovados(tmp_path)


def test_ler_aprovados_ausente_continua_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        ler_aprovados(tmp_path)


def test_pedidos():
    bom = {"momentos": [{"inicio": 1.0, "fim": 3.0, "fala": "x", "tipo": "foto", "nome": "a", "busca": "b"}]}
    assert contrato.conferir_pedidos(bom) == []
    ruim = {"momentos": [{"inicio": "1", "fim": 3.0, "fala": "x", "tipo": "video", "nome": "a", "cor": "azul"}]}
    campos = {p.campo for p in contrato.conferir_pedidos(ruim)}
    assert {"momentos[0].inicio", "momentos[0].tipo", "momentos[0].cor"} <= campos


def test_nomes_suspeitos_e_musicas():
    assert contrato.conferir_nomes_suspeitos({"1": ["x"]}, {1}) == []
    assert contrato.conferir_nomes_suspeitos({"7": ["x"]}, {1})
    assert contrato.conferir_musicas_do_episodio({"faixas": [{"arquivo": "leve/a.mp3"}]}, {"leve/a.mp3"}) == []
    assert contrato.conferir_musicas_do_episodio({"faixas": [{"arquivo": "leve/b.mp3"}]}, {"leve/a.mp3"})


def _episodio(tmp_path, cortes):
    (tmp_path / "aprovados.json").write_text(json.dumps({"cortes": cortes}), "utf-8")
    (tmp_path / "episodio.json").write_text(json.dumps({"duracao": 600.0}), "utf-8")
    (tmp_path / "transcricao").mkdir()
    palavras = [{"texto": "Começo.", "inicio": 9.5, "fim": 10.0}, {"texto": "Oi", "inicio": 10.0, "fim": 10.4},
                {"texto": "fim.", "inicio": 79.6, "fim": 80.0}, {"texto": "Depois", "inicio": 81.0, "fim": 81.4}]
    (tmp_path / "transcricao" / "palavras.json").write_text(json.dumps(palavras), "utf-8")


def test_cli_validar_json_aponta_o_campo(tmp_path, capsys):
    _episodio(tmp_path, [_corte(nota=1)])
    assert cli.principal(["validar", str(tmp_path), "--json"]) == 1
    saida = json.loads(capsys.readouterr().out)
    assert saida["ok"] is False
    assert saida["arquivos"][0]["campo"] == "cortes[0].nota"


def test_cli_validar_ok(tmp_path, capsys):
    _episodio(tmp_path, [_corte()])
    assert cli.principal(["validar", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_json_quebrado_vira_mensagem_e_nao_traceback(tmp_path, capsys):
    _episodio(tmp_path, [_corte()])
    (tmp_path / "aprovados.json").write_text("{quebrado", "utf-8")
    assert cli.principal(["status", str(tmp_path)]) == 0  # status nunca quebra: mostra o erro
    assert "JSON inválido" in capsys.readouterr().out
    (tmp_path / "episodio.json").write_text("{quebrado", "utf-8")
    assert cli.principal(["trecho", str(tmp_path), "--de", "1", "--ate", "2"]) == 0
    (tmp_path / "transcricao" / "palavras.json").write_text("[{quebrado", "utf-8")
    assert cli.principal(["trecho", str(tmp_path), "--de", "1", "--ate", "2"]) == 1
    erro = capsys.readouterr().err
    assert erro.startswith("Erro:") and "JSON inválido" in erro


def test_cli_trecho(tmp_path, capsys):
    _episodio(tmp_path, [_corte()])
    assert cli.principal(["trecho", str(tmp_path), "--de", "10", "--ate", "11", "--margem", "1", "--json"]) == 0
    linhas = json.loads(capsys.readouterr().out)
    assert [l["texto"] for l in linhas] == ["Começo.", "Oi"]
    assert [l["dentro"] for l in linhas] == [False, True]


def test_status_diz_o_proximo_passo(tmp_path):
    _episodio(tmp_path, [_corte()])
    status = status_episodio(tmp_path)
    assert status["cortes"][0]["proximo"] == "planos"
    (tmp_path / "01-pergunta" / "trabalho").mkdir(parents=True)
    (tmp_path / "01-pergunta" / "trabalho" / "enquadramento.json").write_text("{}", "utf-8")
    assert status_episodio(tmp_path)["cortes"][0]["proximo"] == "preparar"


def test_status_sem_transcricao(tmp_path):
    assert status_episodio(tmp_path)["proximo"] == "transcrever"


def test_falantes_por_sobreposicao():
    palavras = [Palavra("a", 0.0, 0.5), Palavra("b", 0.7, 1.0), Palavra("c", 3.0, 3.4)]
    trechos = [TrechoVoz(0.0, 0.8, "V1"), TrechoVoz(0.8, 5.0, "V2")]
    assert rotular(palavras, trechos) == ["V1", "V2", "V2"]


def test_texto_com_falantes_marca_pausa_e_nome():
    palavras = [Palavra("Oi.", 0.0, 0.5), Palavra("Tudo", 2.0, 2.4), Palavra("bem?", 2.4, 2.8)]
    trechos = [TrechoVoz(0.0, 1.0, "V1"), TrechoVoz(1.9, 3.0, "V2")]
    texto = texto_com_falantes(palavras, trechos, {"V2": "P1"}, {"P1": "Ana"})
    assert texto.splitlines() == ["[00:00:00.0] V1: Oi. [pausa 1,5 s]", "[00:00:02.0] V2 (Ana): Tudo bem?"]


def test_doctor_nao_mostra_segredo():
    from esteira.diagnostico import doctor

    segredo = "sk-segredo-que-nao-pode-aparecer"
    itens = doctor(ler_credencial=lambda servico, campo: segredo)
    assert all(segredo not in i.detalhe for i in itens)
    assert any(i.nome == "chave openai" and i.estado == "ok" for i in itens)
