import base64
import json
import threading
from datetime import datetime
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from esteira.cortar import TRABALHO, pasta_do_corte, preparar_episodio
from esteira.modelos import Corte
from esteira.painel import rotas_editor
from esteira.painel.app import criar_app
from esteira.painel.fila import Fila
from esteira.painel.rotas_editor import Dependencias
from esteira.painel.troca_musica import Resultado
from esteira.painel.troca_trecho import MARCADOR
from esteira.publicar.post import versao_dos_bytes

NOME = "Entre Assuntos 03 - Arthur Cerqueira (teste)"
AGORA = datetime(2026, 11, 7, 10)
PALAVRAS = [{"texto": f"w{t}.", "inicio": float(t), "fim": t + 0.9} for t in range(1, 200) if t not in (40, 41)]
CORTE = Corte(1, "Um", 10.0, 80.9, "tenso")
OUTRO = Corte(2, "Dois", 120.0, 199.9, "tenso")


def _preparar(pasta, numero, nomes, pasta_musicas):
    return preparar_episodio(
        pasta, {numero}, forcar=True, nomes=nomes, pasta_musicas=pasta_musicas, medir_silencio=None
    )[numero]


class Montar:
    def __init__(self):
        self.liberar = threading.Event()
        self.liberar.set()
        self.comecou = threading.Event()
        self.chamadas = []

    def __call__(self, pasta, numero):
        self.comecou.set()
        self.liberar.wait(10)
        self.chamadas.append(numero)
        (pasta_do_corte(pasta, CORTE) / "corte.mp4").write_bytes(b"novo")
        return "ok"


@pytest.fixture
def ambiente(tmp_path):
    cortes = tmp_path / "cortes"
    musicas = tmp_path / "musicas"
    musicas.mkdir()
    pasta = cortes / NOME
    (pasta / "transcricao").mkdir(parents=True)
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(PALAVRAS), "utf-8")
    (pasta / "episodio.json").write_text(json.dumps({"video": str(tmp_path / "ep.mp4"), "duracao": 210}), "utf-8")
    aprovados = {"cortes": [CORTE.__dict__, OUTRO.__dict__]}
    (pasta / "aprovados.json").write_text(json.dumps(aprovados, ensure_ascii=False, indent=2), "utf-8")
    assert _preparar(pasta, 1, [], musicas).startswith("ok")
    (pasta_do_corte(pasta, CORTE) / "corte.mp4").write_bytes(b"antigo")
    filas: list[Fila] = []
    montar = Montar()

    def construir():
        fila = Fila(lambda *a: Resultado("erro", "não usado", [], None))
        filas.append(fila)
        app = criar_app(cortes, agora=lambda: AGORA, fila=fila, pasta_musicas=musicas, montar=montar)
        app.state.editor_trecho = Dependencias(preparar=_preparar, nomes=lambda: [])
        return TestClient(app), fila

    yield construir, pasta, montar
    montar.liberar.set()
    for fila in filas:
        fila.parar(5)


def _url(sufixo: str = "", n: int = 1) -> str:
    return f"/api/episodios/{quote(NOME)}/cortes/{n}/trecho{sufixo}"


def _esperar(condicao):
    for _ in range(300):
        valor = condicao()
        if valor:
            return valor
        threading.Event().wait(0.05)
    return condicao()


def _versao(pasta) -> str:
    return versao_dos_bytes((pasta / "aprovados.json").read_bytes())


def _vozes(pasta):
    (pasta / "transcricao" / "vozes.json").write_text(json.dumps({"trechos": [
        {"inicio": 0, "fim": 50, "voz": "SPEAKER_00"}, {"inicio": 50, "fim": 210, "voz": "SPEAKER_01"},
    ]}), "utf-8")
    (pasta / "transcricao" / "pessoas.json").write_text(json.dumps(
        {"ligacao": {"SPEAKER_00": "p1"}, "assinaturas": {}, "nomes": {"p1": "Gabriel"}}), "utf-8")


def test_ler_trecho_traz_palavras_falantes_e_limites(ambiente):
    construir, pasta, _ = ambiente
    _vozes(pasta)
    cliente, _ = construir()
    dados = cliente.get(_url()).json()
    assert dados["versao"] == _versao(pasta)
    assert (dados["inicio"], dados["fim"], dados["duracao_episodio"]) == (10.0, 80.9, 210)
    assert (dados["minima"], dados["maxima"]) == (60, 120)
    assert (dados["de"], dados["ate"]) == (0.0, 110.9)
    palavras = dados["palavras"]
    assert palavras[0] == {"texto": "w1.", "inicio": 1.0, "fim": 1.9, "voz": "SPEAKER_00",
                           "falante": "SPEAKER_00 (Gabriel)", "pode_iniciar": True, "pode_terminar": True}
    assert palavras[-1]["texto"] == "w110." and palavras[-1]["falante"] == "SPEAKER_01"
    assert len(palavras) == 108  # w1 a w110, sem w40 e w41
    assert dados["outros"] == []
    assert (dados["preparado"], dados["montado"], dados["problemas"], dados["pedido"]) == (True, True, [], None)


def test_ler_trecho_janela_e_outros_cortes(ambiente):
    construir, pasta, _ = ambiente
    cliente, _ = construir()
    dados = cliente.get(_url("?antes=5&depois=60")).json()
    assert (dados["de"], dados["ate"]) == (5.0, 140.9)
    assert dados["outros"] == [{"numero": 2, "titulo": "Dois", "inicio": 120.0, "fim": 199.9}]
    assert dados["palavras"][0]["voz"] is None and dados["palavras"][0]["falante"] is None  # sem vozes.json
    limitada = cliente.get(_url("?antes=100000&depois=-3")).json()
    assert (limitada["de"], limitada["ate"]) == (0.0, 80.9)
    outro = cliente.get(_url(n=2)).json()
    assert (outro["preparado"], outro["montado"]) == (False, False)


def test_ler_trecho_nao_encontrado(ambiente):
    construir, pasta, _ = ambiente
    cliente, _ = construir()
    assert cliente.get(_url(n=9)).status_code == 404
    (pasta / "episodio.json").unlink()
    sem_episodio = cliente.get(_url())
    assert sem_episodio.status_code == 404
    assert "transcrever" in sem_episodio.json()["detail"] and "Errno" not in sem_episodio.json()["detail"]
    (pasta / "transcricao" / "palavras.json").unlink()
    assert cliente.get(_url()).status_code == 404


def test_conferir_alinha_e_conta_o_que_muda(ambiente):
    construir, pasta, _ = ambiente
    cliente, _ = construir()
    antes = (pasta / "aprovados.json").read_bytes()
    dados = cliente.post(_url("/conferir"), json={"inicio": 19.7, "fim": 101.2}).json()
    assert (dados["inicio"], dados["fim"], dados["duracao"], dados["mudou"]) == (20.0, 100.9, 80.9, True)
    assert dados["problemas"] == []
    assert any("preparado e montado de novo" in r for r in dados["resumo"])
    assert (pasta / "aprovados.json").read_bytes() == antes


def test_conferir_mostra_os_problemas(ambiente):
    construir, _, _ = ambiente
    cliente, _ = construir()
    curto = cliente.post(_url("/conferir"), json={"inicio": 20, "fim": 50.9}).json()
    assert curto["problemas"] == ["duração fora de 60 a 120 segundos"] and curto["resumo"] == []
    invertido = cliente.post(_url("/conferir"), json={"inicio": 90, "fim": 30}).json()
    assert invertido["problemas"] == [rotas_editor.FIM_ANTES]
    igual = cliente.post(_url("/conferir"), json={"inicio": 10.1, "fim": 80.8}).json()
    assert igual["mudou"] is False and igual["resumo"] == []
    sobrepondo = cliente.post(_url("/conferir"), json={"inicio": 50, "fim": 125.9}).json()
    assert sobrepondo["avisos"][0].startswith("O trecho novo sobrepõe o corte 2 (Dois)")
    nan = cliente.post(_url("/conferir"), content=b'{"inicio": NaN, "fim": 2}',
                       headers={"Content-Type": "application/json"})
    assert nan.status_code == 422


def test_trocar_poe_na_fila_e_refaz_o_corte(ambiente):
    construir, pasta, montar = ambiente
    cliente, fila = construir()
    corpo = {"inicio": 19.7, "fim": 101.2, "versao": _versao(pasta), "confirmado": True}
    resposta = cliente.post(_url(), json=corpo)
    assert resposta.status_code == 202
    pedido = resposta.json()
    assert (pedido["tipo"], pedido["cortes"]) == ("trecho", [1])
    final = _esperar(lambda: (p := cliente.get(f"/api/tarefas/{pedido['id']}").json())["estado"] != "na fila"
                     and p["estado"] != "montando" and p)
    assert final["estado"] == "pronto", final["mensagem"]
    assert final["mensagem"] == "Trecho novo: 0:20,0 a 1:40,9 (80,9 s)."
    corte = json.loads((pasta / "aprovados.json").read_text("utf-8"))["cortes"][0]
    assert (corte["inicio"], corte["fim"]) == (20.0, 100.9)
    assert len(list((pasta / "aprovados-anteriores").iterdir())) == 1
    assert montar.chamadas == [1]
    assert (pasta_do_corte(pasta, CORTE) / "corte.mp4").read_bytes() == b"novo"
    dados = cliente.get(_url()).json()
    assert (dados["inicio"], dados["fim"]) == (20.0, 100.9)
    assert dados["pedido"]["id"] == pedido["id"] and dados["pedido"]["estado"] == "pronto"


def test_trocar_recusa(ambiente):
    construir, pasta, _ = ambiente
    cliente, _ = construir()
    antes = (pasta / "aprovados.json").read_bytes()
    versao = _versao(pasta)
    sem_confirmar = cliente.post(_url(), json={"inicio": 20, "fim": 100.9, "versao": versao})
    assert sem_confirmar.status_code == 422
    velha = cliente.post(_url(), json={"inicio": 20, "fim": 100.9, "versao": "x", "confirmado": True})
    assert velha.status_code == 409 and velha.json()["versao_atual"] == versao
    curto = cliente.post(_url(), json={"inicio": 20, "fim": 50.9, "versao": versao, "confirmado": True})
    assert curto.status_code == 422 and "duração fora" in curto.json()["detail"]
    igual = cliente.post(_url(), json={"inicio": 10, "fim": 80.9, "versao": versao, "confirmado": True})
    assert igual.status_code == 422 and igual.json()["detail"] == rotas_editor.SEM_MUDANCA
    assert (pasta / "aprovados.json").read_bytes() == antes


def test_trocar_bloqueia_o_corte_enquanto_roda(ambiente):
    construir, pasta, montar = ambiente
    cliente, fila = construir()
    montar.liberar.clear()
    corpo = {"inicio": 20, "fim": 100.9, "versao": _versao(pasta), "confirmado": True}
    assert cliente.post(_url(), json=corpo).status_code == 202
    assert montar.comecou.wait(30)
    assert fila.montando_corte(NOME, 1)  # aprovar, legenda e música esperam a troca terminar
    de_novo = cliente.post(_url(), json={**corpo, "versao": _versao(pasta)})
    assert de_novo.status_code == 409 and de_novo.json()["detail"] == rotas_editor.MONTANDO
    montar.liberar.set()
    assert _esperar(lambda: not fila.montando_corte(NOME, 1))


def test_trocar_recusa_se_o_corte_ja_esta_montando(ambiente):
    construir, pasta, _ = ambiente
    cliente, fila = construir()
    liberar = threading.Event()
    fila.pedir_tarefa("montar", pasta, [1], lambda progresso: liberar.wait(10) and Resultado("pronto", "", [], None))
    try:
        resposta = cliente.post(_url(), json={"inicio": 20, "fim": 100.9, "versao": _versao(pasta), "confirmado": True})
        assert resposta.status_code == 409
    finally:
        liberar.set()


def test_painel_desfaz_troca_interrompida_ao_abrir(ambiente):
    construir, pasta, _ = ambiente
    original = (pasta / "aprovados.json").read_bytes()
    trabalho = pasta_do_corte(pasta, CORTE) / TRABALHO
    (trabalho / MARCADOR).write_text(json.dumps({
        "fase": "aplicando", "arquivos": {"aprovados.json": base64.b64encode(original).decode("ascii")},
        "renomeados": [], "video": False, "uso": None,
    }), "utf-8")
    (pasta / "aprovados.json").write_text("pela metade", "utf-8")
    construir()
    assert (pasta / "aprovados.json").read_bytes() == original
    assert not (trabalho / MARCADOR).exists()
