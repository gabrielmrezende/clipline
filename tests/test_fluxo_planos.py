import json

import pytest

from esteira import fluxo_planos, planos
from esteira.fluxo_planos import planejar_episodio
from esteira.pessoas import gravar_pessoas, ler_pessoas
from esteira.planos import ler_planos
from esteira.rostos import Deteccao
from tests.auxiliares import preparar_teste

CORTE = {"numero": 1, "titulo": "Bom corte", "inicio": 0.0, "fim": 20.0, "clima": "leve"}
ROSTO_A = [1.0, 0.0, 0.0]
ROSTO_B = [0.0, 1.0, 0.0]


def detectar_falso(video, inicio, fim):
    """Cena 0-10 s com a pessoa A à esquerda; cena 10-20 s com a pessoa B à direita."""
    deteccoes = []
    t = inicio
    while t < fim:
        if t < 10:
            deteccoes.append(Deteccao(t, 0.3, 0.4, 0.1, 0.2, ROSTO_A))
        else:
            deteccoes.append(Deteccao(t, 0.7, 0.4, 0.1, 0.25 if t == 15 else 0.2, ROSTO_B))
        t += 0.5
    return deteccoes


@pytest.fixture
def episodio(tmp_path, monkeypatch):
    pasta = tmp_path / "ep"
    (pasta / "transcricao").mkdir(parents=True)
    (pasta / "episodio.json").write_text(json.dumps({"video": str(tmp_path / "v.mp4"), "duracao": 80}), "utf-8")
    (pasta / "aprovados.json").write_text(json.dumps({"cortes": [CORTE]}), "utf-8")
    vozes = {"trechos": [{"inicio": 0.0, "fim": 10.0, "voz": "V1"}, {"inicio": 10.0, "fim": 20.0, "voz": "V2"}]}
    (pasta / "transcricao" / "vozes.json").write_text(json.dumps(vozes), "utf-8")
    palavras = [{"texto": f"p{i}", "inicio": i * 1.0, "fim": i * 1.0 + 0.9} for i in range(20)]
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(palavras), "utf-8")
    monkeypatch.setattr(planos, "detectar_cortes", lambda video, inicio, fim: [10.0])
    folhas = {}

    def folha(video, lista, saida, rotulos=None, caixas=None):
        folhas["planos"] = (lista, rotulos, caixas)
        saida.write_bytes(b"x")
        return saida

    def folha_pessoas(video, amostras, ligacao, tempo_de_fala, nomes, saida):
        folhas["pessoas"] = (amostras, tempo_de_fala)
        saida.write_bytes(b"x")
        return saida

    monkeypatch.setattr(fluxo_planos, "gerar_folha", folha)
    monkeypatch.setattr(fluxo_planos, "folha_pessoas", folha_pessoas)
    return pasta, folhas


def _trabalho(pasta):
    return pasta / "01-bom-corte" / "trabalho"


def test_planejar_grava_enquadramento_e_pessoas(episodio):
    pasta, folhas = episodio
    assert planejar_episodio(pasta, None, detectar=detectar_falso) == {1: "ok"}
    lista = ler_planos(_trabalho(pasta))
    assert [(p.inicio, p.fim, p.x, p.zoom) for p in lista] == [(0.0, 10.0, 0.3, 1.35), (10.0, 20.0, 0.7, 1.35)]
    ligacao, assinaturas, nomes = ler_pessoas(pasta)
    assert ligacao == {"V1": "P1", "V2": "P2"}
    assert set(assinaturas) == {"P1", "P2"} and nomes == {}
    assert (pasta / "transcricao" / "pessoas.jpg").exists()
    assert (_trabalho(pasta) / "planos.jpg").exists()
    assert json.loads((_trabalho(pasta) / "alertas-planos.json").read_text("utf-8")) == []
    _, rotulos, caixas = folhas["planos"]
    assert rotulos == ["1 P1 · p0 p1 p2 p3 p4 p5", "2 P2 · p10 p11 p12 p13 p14 p15"]
    assert caixas[0] == pytest.approx((0.3, 0.4, 0.1, 0.2))
    amostras, tempo_de_fala = folhas["pessoas"]
    assert amostras["P2"][0] == 15.0 and amostras["P2"][1].altura == 0.25
    assert tempo_de_fala == {"V1": 10.0, "V2": 10.0}


def test_planejar_nao_sobrescreve_sem_forcar(episodio):
    pasta, _ = episodio
    trabalho = _trabalho(pasta)
    trabalho.mkdir(parents=True)
    editado = json.dumps({"planos": [{"inicio": 0.0, "fim": 20.0, "x": 0.9, "y": 0.5, "zoom": 2.0}]})
    (trabalho / "enquadramento.json").write_text(editado, "utf-8")
    assert planejar_episodio(pasta, None, detectar=detectar_falso) == {1: "mantido (já existe)"}
    assert (trabalho / "enquadramento.json").read_text("utf-8") == editado
    assert planejar_episodio(pasta, None, forcar=True, detectar=detectar_falso) == {1: "ok"}
    primeiro = ler_planos(trabalho)[0]
    assert (primeiro.inicio, primeiro.fim, primeiro.x, primeiro.zoom) == (0.0, 10.0, 0.3, 1.35)


def test_planejar_preserva_nomes_de_pessoas(episodio):
    pasta, _ = episodio
    gravar_pessoas(pasta, {"V1": "P1"}, {"P1": ROSTO_A}, {"P1": "Arthur"})
    resultado = planejar_episodio(pasta, None, detectar=detectar_falso)
    ligacao, assinaturas, nomes = ler_pessoas(pasta)
    assert nomes == {"P1": "Arthur"}
    assert ligacao == {"V1": "P1"}
    assert assinaturas["P1"] == ROSTO_A and "P2" in assinaturas
    assert resultado[1].startswith("ok com alertas: ") and "V2" in resultado[1]
    alertas = json.loads((_trabalho(pasta) / "alertas-planos.json").read_text("utf-8"))
    assert "00:10 voz V2 sem pessoa" in alertas


def test_planejar_rotulo_usa_nome(episodio):
    pasta, folhas = episodio
    gravar_pessoas(pasta, {"V1": "P1", "V2": "P2"}, {"P1": ROSTO_A, "P2": ROSTO_B}, {"P1": "Arthur"})
    planejar_episodio(pasta, None, detectar=detectar_falso)
    assert folhas["planos"][1][0] == "1 Arthur · p0 p1 p2 p3 p4 p5"


def test_planejar_sem_vozes_para(episodio):
    pasta, _ = episodio
    (pasta / "transcricao" / "vozes.json").unlink()
    resultado = planejar_episodio(pasta, None, detectar=detectar_falso)
    assert list(resultado) == [0] and resultado[0].startswith("erro: ")
    assert not (_trabalho(pasta) / "enquadramento.json").exists()
    assert ler_pessoas(pasta) is None


def test_planejar_alertas_relativos_ao_corte(episodio):
    pasta, _ = episodio
    corte = {**CORTE, "inicio": 0.0, "fim": 30.0}
    (pasta / "aprovados.json").write_text(json.dumps({"cortes": [corte]}), "utf-8")
    resultado = planejar_episodio(pasta, None, detectar=detectar_falso)
    alertas = json.loads((_trabalho(pasta) / "alertas-planos.json").read_text("utf-8"))
    assert alertas == []  # pessoa B continua na tela de 10 a 30 s
    assert resultado == {1: "ok"}

    sem_rosto = lambda video, inicio, fim: [d for d in detectar_falso(video, inicio, fim) if d.tempo < 10]
    resultado = planejar_episodio(pasta, None, forcar=True, detectar=sem_rosto)
    alertas = json.loads((_trabalho(pasta) / "alertas-planos.json").read_text("utf-8"))
    assert "00:10 sem rosto" in alertas


def test_preparar_leva_alertas_de_planos(episodio):
    pasta, _ = episodio
    trabalho = _trabalho(pasta)
    trabalho.mkdir(parents=True)
    (trabalho / "alertas-planos.json").write_text(json.dumps(["00:10 sem rosto"]), "utf-8")
    preparar_teste(pasta)
    registro = json.loads((trabalho / "registro.json").read_text("utf-8"))
    assert "00:10 sem rosto" in registro["alertas"]
