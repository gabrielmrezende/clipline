import pytest

from esteira import config, idiomas, limpeza, pedidos
from esteira.limpeza import planejar_limpeza
from esteira.modelos import Palavra as P
from esteira.pedidos import _pessoa_citada

# As listas de antes desta mudança, copiadas à mão: o padrão (português) tem que continuar idêntico.
CARGOS_DE_SEMPRE = (
    "presidente", "presidenta", "vice-presidente", "ex-presidente", "primeiro-ministro", "primeira-ministra",
    "ministro", "ministra", "senador", "senadora", "deputado", "deputada", "governador", "governadora",
    "prefeito", "prefeita", "vereador", "vereadora", "chanceler", "papa", "rei", "rainha", "principe", "princesa",
    "candidato", "candidata", "ditador", "ditadora", "stf",
    "president", "vice president", "prime minister", "minister", "senator", "congressman", "congresswoman",
    "member of congress", "governor", "mayor", "chancellor", "pope", "king", "queen", "prince", "princess",
    "dictator", "candidate", "head of state", "supreme court justice",
)


def _canal_em(monkeypatch, idioma: str) -> None:
    monkeypatch.setattr(config, "atual", lambda: config.Config(transcricao_idioma=idioma))


def test_padrao_identico_ao_de_sempre():
    assert pedidos.CARGOS == CARGOS_DE_SEMPRE
    assert idiomas.cargos("pt") == CARGOS_DE_SEMPRE
    assert limpeza.HESITACOES == {"hum", "hã", "ahn", "éé", "hmm", "ãh", "eh"}
    assert limpeza.PROTEGIDAS == {"né", "tá", "não", "muito", "nunca", "sim", "isso"}


@pytest.mark.parametrize("idioma", ["en", "es"])
def test_ingles_e_espanhol_tem_todas_as_listas(idioma):
    assert idiomas.hesitacoes(idioma) and idiomas.protegidas(idioma)
    assert set(idiomas.CARGOS["en"]) <= set(idiomas.cargos(idioma))


def test_idioma_sem_lista_usa_todos_os_cargos_e_nenhuma_hesitacao():
    assert {"alcalde", "prefeito", "mayor"} <= set(idiomas.cargos("fr"))
    assert len(idiomas.cargos("fr")) == len(set(idiomas.cargos("fr")))
    assert idiomas.hesitacoes("fr") == frozenset()


def test_um_e_palavra_em_portugues_e_hesitacao_em_ingles():
    p = [P("um", 0, 0.2), P("ponto.", 0.25, 0.6)]
    assert planejar_limpeza(p, 0, 0.6, idioma="pt")[1] == []
    assert [e.motivo for e in planejar_limpeza(p, 0, 0.6, idioma="en")[1]] == ["hesitação"]


def test_limpeza_usa_o_idioma_do_clipline_toml(monkeypatch):
    p = [P("eh", 0, 0.2), P("no", 0.25, 0.4), P("no", 0.45, 0.6), P("vale.", 0.65, 1)]
    _canal_em(monkeypatch, "es")
    _, edicoes = planejar_limpeza(p, 0, 1)
    assert [e.motivo for e in edicoes] == ["hesitação"]  # "no, no" em espanhol é de propósito


def test_repeticao_protegida_em_ingles():
    p = [P("very", 0, 0.2), P("very", 0.25, 0.45), P("good.", 0.5, 1)]
    assert planejar_limpeza(p, 0, 1, idioma="en")[1] == []
    assert [e.motivo for e in planejar_limpeza(p, 0, 1, idioma="pt")[1]] == ["repetição"]


def test_cargo_em_espanhol_so_quando_o_canal_e_em_espanhol(monkeypatch):
    prompt = "el alcalde de la ciudad en una plaza"
    assert _pessoa_citada(prompt, []) is None  # canal em português: como sempre
    _canal_em(monkeypatch, "es")
    assert _pessoa_citada(prompt, []) == "cargo público: alcalde"
    assert _pessoa_citada("the mayor of the city", []) == "cargo público: mayor"  # inglês vale sempre


def test_cargos_explicitos_continuam_valendo(monkeypatch):
    _canal_em(monkeypatch, "es")
    assert _pessoa_citada("o vereador", [], cargos=("vereador",)) == "cargo público: vereador"
