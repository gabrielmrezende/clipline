import json
from datetime import datetime
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from esteira.cortar import _escrever_edicoes, pasta_do_corte
from esteira.limpeza import planejar_limpeza
from esteira.modelos import Corte, Edicao, Palavra
from esteira.painel.app import criar_app
from esteira.painel.rotas_revisao import Remocao, ler_edicoes, remocoes_no_corte
from esteira.receita import Receita, gravar_receita
from tests.auxiliares_painel import criar_episodio

NOME = "Entre Assuntos 03 - Arthur Cerqueira (teste capcut)"
AGORA = datetime(2026, 11, 7, 10)
CORTE = Corte(1, "Um", 10, 20, "tenso")


# --- leitura do edicoes.md -------------------------------------------------------------------------------------------


def test_ler_edicoes_le_o_que_o_preparar_grava(tmp_path):
    edicoes = [
        Edicao(12.31, 12.58, "hesitação", "hum"),
        Edicao(13.0, 13.2, "repetição", "o"),
        Edicao(14.0, 15.25, "pausa", ""),
        Edicao(16.0, 17.0, "pausa com som mantida", ""),
    ]
    arquivo = tmp_path / "edicoes.md"
    _escrever_edicoes(edicoes, arquivo)
    assert ler_edicoes(arquivo.read_text("utf-8")) == edicoes


def test_ler_edicoes_sem_remocao_e_linhas_estranhas():
    assert ler_edicoes("# Edições automáticas\n\n- Nenhuma remoção.\n") == []
    texto = "- 1.00s a 2.00s: outro motivo qualquer\n- isto não é edição\n- 3,0s a 4s: pausa\n"
    assert ler_edicoes(texto) == [Edicao(1.0, 2.0, "outro motivo qualquer", "")]


def test_ler_edicoes_texto_com_espacos_e_pontuacao():
    assert ler_edicoes("- 5.10s a 5.40s: repetição não,\n") == [Edicao(5.1, 5.4, "repetição", "não,")]


# --- remoções no tempo do corte --------------------------------------------------------------------------------------


def test_cada_corte_entre_faixas_vira_uma_remocao_no_tempo_do_corte():
    faixas = [(10.0, 12.0), (12.5, 15.0), (16.0, 20.0)]
    edicoes = [Edicao(12.0, 12.5, "pausa", ""), Edicao(15.1, 15.4, "hesitação", "hum")]
    assert remocoes_no_corte(faixas, edicoes) == [
        Remocao(tempo=2.0, duracao=0.5, motivo="pausa", texto="", episodio=12.0),
        Remocao(tempo=4.5, duracao=1.0, motivo="hesitação", texto="hum", episodio=15.0),
    ]


def test_varias_edicoes_no_mesmo_corte_viram_uma_marca():
    faixas = [(0.0, 3.0), (4.0, 8.0)]
    edicoes = [
        Edicao(3.1, 3.3, "hesitação", "hum"),
        Edicao(3.4, 3.6, "repetição", "o"),
        Edicao(3.6, 3.8, "hesitação", "ahn"),
    ]
    [remocao] = remocoes_no_corte(faixas, edicoes)
    assert remocao.tempo == 3.0 and remocao.duracao == 1.0
    assert remocao.motivo == "hesitação e repetição"
    assert remocao.texto == "hum o ahn"


def test_pausa_com_som_mantida_e_edicao_dentro_da_faixa_nao_viram_marca():
    faixas = [(0.0, 10.0)]
    edicoes = [Edicao(2.0, 3.0, "pausa com som mantida", ""), Edicao(9.6, 9.9, "hesitação", "hum")]
    assert remocoes_no_corte(faixas, edicoes) == []


def test_corte_sem_edicao_que_explique_vira_trecho_removido():
    assert remocoes_no_corte([(0.0, 2.0), (3.0, 4.0)], []) == [
        Remocao(tempo=2.0, duracao=1.0, motivo="trecho removido", texto="", episodio=2.0)
    ]


def test_hesitacao_no_comeco_fica_no_tempo_zero():
    faixas = [(10.45, 14.0), (14.5, 18.0)]
    edicoes = [Edicao(10.0, 10.4, "hesitação", "hã"), Edicao(14.0, 14.5, "pausa", "")]
    remocoes = remocoes_no_corte(faixas, edicoes)
    assert remocoes[0] == Remocao(tempo=0.0, duracao=0.45, motivo="hesitação", texto="hã", episodio=10.0)
    assert remocoes[1].tempo == 3.55


def test_faixas_fora_de_ordem_ou_invalidas_nao_quebram():
    faixas = [(5.0, 8.0), (0.0, 4.0), (9.0, 9.0), ("x", 1)]
    assert [r.tempo for r in remocoes_no_corte(faixas, [Edicao(4.2, 4.8, "pausa", "")])] == [4.0]
    assert remocoes_no_corte([], [Edicao(1.0, 2.0, "pausa", "")]) == []


def test_bate_com_a_limpeza_de_verdade():
    """As marcas caem onde o planejar_limpeza cortou, na mesma conta do remapear."""
    textos = ["então", "hum", "a", "a", "gente", "foi", "lá"]
    tempos = [(0.0, 0.4), (0.5, 0.8), (0.9, 1.0), (1.05, 1.2), (1.3, 1.6), (2.8, 3.1), (3.2, 3.5)]
    palavras = [Palavra(t, de, ate) for t, (de, ate) in zip(textos, tempos, strict=True)]
    faixas, edicoes = planejar_limpeza(palavras, 0.0, 3.5)
    remocoes = remocoes_no_corte(faixas, edicoes)
    assert [r.motivo for r in remocoes] == ["hesitação e repetição", "pausa"]
    assert remocoes[0].texto == "hum a"
    assert remocoes[0].tempo == pytest.approx(faixas[0][1] - faixas[0][0], abs=0.01)
    total = sum(ate - de for de, ate in faixas)
    removido = sum(r.duracao for r in remocoes)
    assert total + removido == pytest.approx(3.5, abs=0.02)


# --- rota ------------------------------------------------------------------------------------------------------------


def _cliente(tmp_path) -> TestClient:
    return TestClient(criar_app(tmp_path / "cortes", agora=lambda: AGORA))


def _url(n: int = 1) -> str:
    return f"/api/episodios/{quote(NOME)}/cortes/{n}/remocoes"


def _trabalho(tmp_path):
    (tmp_path / "cortes").mkdir(exist_ok=True)
    pasta = criar_episodio(tmp_path / "cortes", NOME, [CORTE], {1})
    return pasta_do_corte(pasta, CORTE) / "trabalho"


def test_rota_devolve_as_remocoes_do_corte(tmp_path):
    trabalho = _trabalho(tmp_path)
    gravar_receita(trabalho, Receita([(10.0, 12.0), (12.6, 20.0)], [], []))
    _escrever_edicoes([Edicao(12.0, 12.6, "pausa", "")], trabalho / "edicoes.md")
    resposta = _cliente(tmp_path).get(_url())
    assert resposta.status_code == 200
    assert resposta.json() == {
        "remocoes": [{"tempo": 2.0, "duracao": 0.6, "motivo": "pausa", "texto": "", "episodio": 12.0}],
        "removido": 0.6,
        "avisos": [],
    }


def test_rota_sem_edicoes_md_mostra_os_cortes_sem_motivo(tmp_path):
    trabalho = _trabalho(tmp_path)
    gravar_receita(trabalho, Receita([(10.0, 12.0), (13.0, 20.0)], [], []))
    dados = _cliente(tmp_path).get(_url()).json()
    assert [r["motivo"] for r in dados["remocoes"]] == ["trecho removido"]
    assert dados["avisos"] == ["sem edicoes.md: os motivos das remoções não aparecem"]


def test_rota_sem_montagem_nao_falha(tmp_path):
    trabalho = _trabalho(tmp_path)
    (trabalho / "montagem.json").unlink()
    dados = _cliente(tmp_path).get(_url()).json()
    assert dados == {"remocoes": [], "removido": 0.0, "avisos": ["sem montagem.json: rode preparar"]}


def test_rota_montagem_ilegivel_avisa(tmp_path):
    trabalho = _trabalho(tmp_path)
    (trabalho / "montagem.json").write_text("{quebrado", "utf-8")
    dados = _cliente(tmp_path).get(_url()).json()
    assert dados["remocoes"] == [] and dados["avisos"] == ["montagem.json ilegível"]


def test_rota_corte_fora_dos_aprovados_404(tmp_path):
    _trabalho(tmp_path)
    resposta = _cliente(tmp_path).get(_url(7))
    assert resposta.status_code == 404 and resposta.json()["detail"]


def test_rota_nao_grava_nada(tmp_path):
    trabalho = _trabalho(tmp_path)
    _escrever_edicoes([], trabalho / "edicoes.md")
    antes = {p: p.read_bytes() for p in trabalho.iterdir()}
    _cliente(tmp_path).get(_url())
    assert {p: p.read_bytes() for p in trabalho.iterdir()} == antes
    assert json.loads((trabalho / "montagem.json").read_text("utf-8"))["faixas"] == [[10, 20]]
