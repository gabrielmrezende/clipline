import threading
import time
from pathlib import Path

import pytest

from esteira.musica import Faixa
from esteira.painel.fila import Fila, Pedido, PedidoAtivo
from esteira.painel.troca_musica import Resultado
from esteira.receita import Musica

FAIXA = Faixa("Nova Faixa", "tensao", 120.0, "nova.mp3", "Música: Nova Faixa")
LIMITE = 5.0


def esperar(condicao, limite=LIMITE):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.005)
    return condicao()


class Controle:
    """Executar falso: cada chamada espera o evento de liberação do seu corte."""

    def __init__(self):
        self.chamadas = []
        self.iniciou = {}
        self.liberar = {}
        self.resultados = {}
        self.excecoes = {}
        self.ordem_fim = []

    def preparar(self, numero):
        self.iniciou[numero] = threading.Event()
        self.liberar[numero] = threading.Event()

    def __call__(self, pasta, numero, faixa, volume_db):
        self.chamadas.append((pasta, numero, faixa, volume_db))
        if numero in self.iniciou:
            self.iniciou[numero].set()
            assert self.liberar[numero].wait(LIMITE)
        self.ordem_fim.append(numero)
        if numero in self.excecoes:
            raise self.excecoes[numero]
        return self.resultados.get(numero, Resultado("pronto", "ok", []))


@pytest.fixture
def controle():
    return Controle()


@pytest.fixture
def fabrica(controle):
    filas = []

    def criar(**kw):
        fila = Fila(controle, **kw)
        filas.append(fila)
        return fila

    yield criar
    for controle_liberar in controle.liberar.values():
        controle_liberar.set()
    for fila in filas:
        fila.parar()


def test_pedido_vai_de_na_fila_a_pronto(controle, fabrica):
    controle.preparar(1)
    controle.resultados[1] = Resultado(
        "pronto", "ok", ["aviso"], Musica("C:/m/antiga.mp3", -20.0, "Antiga", "cred")
    )
    fila = fabrica(relogio=lambda: 100.0)
    pedido = fila.pedir(Path("x/ep1"), 1, FAIXA, -18.0)
    assert len(pedido.id) == 8
    assert (pedido.episodio, pedido.numero, pedido.arquivo, pedido.volume_db) == ("ep1", 1, "nova.mp3", -18.0)
    assert pedido.criado == 100.0
    assert controle.iniciou[1].wait(LIMITE)
    assert fila.pedido(pedido.id).estado == "montando"
    assert fila.ativo("ep1", 1).id == pedido.id
    controle.liberar[1].set()
    assert esperar(lambda: fila.pedido(pedido.id).estado == "pronto")
    final = fila.pedido(pedido.id)
    assert final.avisos == ["aviso"]
    assert final.terminado == 100.0
    assert final.anterior == {"arquivo": "antiga.mp3", "titulo": "Antiga", "volume_db": -20.0}
    assert fila.ativo("ep1", 1) is None
    assert fila.ultimo_pronto("ep1", 1).id == pedido.id
    assert fila.ultimo_pronto("ep1", 2) is None
    assert controle.chamadas == [(Path("x/ep1"), 1, FAIXA, -18.0)]
    assert final.como_dict()["estado"] == "pronto"
    assert fila.pedido("nao-existe") is None


def test_pedido_na_fila_antes_de_montar(controle, fabrica):
    controle.preparar(1)
    controle.preparar(2)
    fila = fabrica()
    fila.pedir(Path("ep1"), 1, FAIXA, -18.0)
    assert controle.iniciou[1].wait(LIMITE)
    segundo = fila.pedir(Path("ep1"), 2, FAIXA, -18.0)
    assert segundo.estado == "na fila"
    assert fila.ativo("ep1", 2).id == segundo.id


def test_um_pedido_ativo_por_corte(controle, fabrica):
    controle.preparar(1)
    fila = fabrica()
    primeiro = fila.pedir(Path("ep1"), 1, FAIXA, -18.0)
    with pytest.raises(PedidoAtivo):
        fila.pedir(Path("ep1"), 1, FAIXA, -10.0)
    assert fila.pedir(Path("ep2"), 1, FAIXA, -18.0).id != primeiro.id
    controle.liberar[1].set()
    assert esperar(lambda: fila.pedido(primeiro.id).estado == "pronto")
    outro = fila.pedir(Path("ep1"), 1, FAIXA, -10.0)
    assert outro.id != primeiro.id
    assert esperar(lambda: fila.pedido(outro.id).estado == "pronto")


def test_dois_cortes_em_sequencia(controle, fabrica):
    controle.preparar(1)
    fila = fabrica()
    a = fila.pedir(Path("ep1"), 1, FAIXA, -18.0)
    assert controle.iniciou[1].wait(LIMITE)
    b = fila.pedir(Path("ep1"), 2, FAIXA, -18.0)
    time.sleep(0.05)
    assert fila.pedido(b.id).estado == "na fila"
    assert controle.ordem_fim == []
    controle.liberar[1].set()
    assert esperar(lambda: fila.pedido(a.id).estado == "pronto" and fila.pedido(b.id).estado == "pronto")
    assert controle.ordem_fim == [1, 2]


def test_erro_e_excecao_viram_estado_erro(controle, fabrica):
    controle.resultados[1] = Resultado("erro", "x", [])
    controle.excecoes[2] = RuntimeError("quebrou")
    controle.excecoes[3] = ValueError()
    fila = fabrica()
    a = fila.pedir(Path("ep1"), 1, FAIXA, -18.0)
    assert esperar(lambda: fila.pedido(a.id).estado == "erro")
    assert fila.pedido(a.id).mensagem == "x"
    assert fila.pedido(a.id).terminado is not None
    b = fila.pedir(Path("ep1"), 2, FAIXA, -18.0)
    assert esperar(lambda: fila.pedido(b.id).estado == "erro")
    assert fila.pedido(b.id).mensagem == "quebrou"
    c = fila.pedir(Path("ep1"), 3, FAIXA, -18.0)
    assert esperar(lambda: fila.pedido(c.id).estado == "erro")
    assert fila.pedido(c.id).mensagem == "ValueError"
    d = fila.pedir(Path("ep1"), 4, FAIXA, -18.0)
    assert esperar(lambda: fila.pedido(d.id).estado == "pronto")
    assert fila.ultimo_pronto("ep1", 1) is None


def test_lista_limita_50(controle, fabrica):
    fila = fabrica()
    ids = []
    for n in range(1, 61):
        p = fila.pedir(Path("ep1"), n, FAIXA, -18.0)
        ids.append(p.id)
        assert esperar(lambda: fila.pedido(p.id).estado == "pronto")
    lista = fila.pedidos()
    assert len(lista) == 50
    assert [p.id for p in lista] == ids[::-1][:50]


def test_parar_encerra_o_trabalhador(controle, fabrica):
    fila = fabrica()
    fila.parar()
    assert not fila._trabalhador.is_alive()


def test_parar_espera_o_atual_e_descarta_os_da_fila(controle, fabrica):
    controle.preparar(1)
    fila = fabrica()
    atual = fila.pedir(Path("ep1"), 1, FAIXA, -18.0)
    assert controle.iniciou[1].wait(LIMITE)
    esperando = fila.pedir(Path("ep1"), 2, FAIXA, -18.0)
    parada = threading.Thread(target=fila.parar, kwargs={"timeout": LIMITE})
    parada.start()
    time.sleep(0.05)
    assert parada.is_alive()  # espera a montagem atual
    controle.liberar[1].set()
    parada.join(LIMITE)
    assert not parada.is_alive() and not fila._trabalhador.is_alive()
    assert fila.pedido(atual.id).estado == "pronto"
    descartado = fila.pedido(esperando.id)
    assert descartado.estado == "erro"
    assert descartado.mensagem == "o painel foi fechado antes de montar este pedido"
    assert [c[1] for c in controle.chamadas] == [1]
