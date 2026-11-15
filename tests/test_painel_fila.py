import json
import threading
import time
from pathlib import Path

import pytest

from esteira.musica import Faixa
from esteira.painel.fila import Fila, NaoCancela, Pedido, PedidoAtivo
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
    assert descartado.estado == "interrompido"
    assert descartado.mensagem == "o painel foi fechado antes de montar este pedido"
    assert [c[1] for c in controle.chamadas] == [1]


def test_excecao_longa_vira_erro_cortado(controle, fabrica):
    controle.excecoes[1] = RuntimeError("erro: " + "y" * 1000)
    fila = fabrica()
    p = fila.pedir(Path("ep1"), 1, FAIXA, -18.0)
    assert esperar(lambda: fila.pedido(p.id).estado == "erro")
    mensagem = fila.pedido(p.id).mensagem
    assert len(mensagem) == 300 and mensagem.startswith("yyy")


def test_base_exception_nao_deixa_pedido_montando(controle, fabrica):
    controle.excecoes[1] = SystemExit(1)
    fila = fabrica()
    p = fila.pedir(Path("ep1"), 1, FAIXA, -18.0)
    assert esperar(lambda: fila.pedido(p.id).estado == "erro")
    final = fila.pedido(p.id)
    assert final.mensagem == "a montagem parou (SystemExit)" and final.terminado is not None
    assert fila.ativo("ep1", 1) is None
    seguinte = fila.pedir(Path("ep1"), 2, FAIXA, -18.0)  # o trabalhador continua vivo
    assert esperar(lambda: fila.pedido(seguinte.id).estado == "pronto")


def tarefa(liberar=None, iniciou=None, texto=None, resultado=None):
    """Executar genérico falso: opcionalmente avisa que iniciou, informa progresso e espera a liberação."""

    def executar(progresso):
        if texto:
            progresso(texto)
        if iniciou:
            iniciou.set()
        if liberar:
            assert liberar.wait(LIMITE)
        return resultado or Resultado("pronto", "ok", [], None)

    return executar


def test_tarefa_de_episodio_bloqueia_so_o_mesmo_tipo(controle, fabrica):
    liberar, iniciou = threading.Event(), threading.Event()
    fila = fabrica()
    try:
        ia = fila.pedir_tarefa("ia", Path("x/ep1"), [1, 2], tarefa(liberar, iniciou))
        assert (ia.tipo, ia.numero, ia.cortes, ia.arquivo, ia.volume_db, ia.estado) == ("ia", 0, [1, 2], "", 0.0, "na fila")
        assert iniciou.wait(LIMITE)
        with pytest.raises(PedidoAtivo):
            fila.pedir_tarefa("ia", Path("x/ep1"), [2], tarefa())
        outro_episodio = fila.pedir_tarefa("ia", Path("x/ep2"), [2], tarefa())
        fotos = fila.pedir_tarefa("fotos", Path("x/ep1"), [2], tarefa())
        musica = fila.pedir(Path("x/ep1"), 2, FAIXA, -18.0)
        assert {fotos.tipo, musica.tipo} == {"fotos", "musica"} and musica.cortes == [2]
        assert fila.ativo("ep1", 2).id == musica.id  # o padrão de ativo é só música
        assert fila.ativo("ep1", 2, "ia").id == ia.id
        assert fila.ativo("ep1", 2, "fotos").id == fotos.id
        assert outro_episodio.id != ia.id
    finally:
        liberar.set()


def test_tarefa_sem_cortes_e_erro(fabrica):
    with pytest.raises(ValueError):
        fabrica().pedir_tarefa("ia", Path("ep1"), [], tarefa())


def test_progresso_aparece_enquanto_roda(fabrica):
    liberar, iniciou = threading.Event(), threading.Event()
    fila = fabrica()
    try:
        p = fila.pedir_tarefa("ia", Path("ep1"), [3], tarefa(liberar, iniciou, "Gerando 2 de 5…"))
        assert p.numero == 3 and p.progresso == ""
        assert iniciou.wait(LIMITE)
        vivo = fila.pedido(p.id)
        assert vivo.estado == "montando" and vivo.progresso == "Gerando 2 de 5…"
        assert fila.montando()
    finally:
        liberar.set()
    assert esperar(lambda: fila.pedido(p.id).estado == "pronto")
    assert fila.ultimo_pronto("ep1", 3) is None  # padrão: só música
    assert fila.ultimo_pronto("ep1", 3, "ia").id == p.id


def test_parar_interrompe_a_tarefa_no_proximo_progresso(fabrica):
    passou, solto = threading.Event(), threading.Event()
    passos = []

    def gera_em_passos(progresso):
        for i in (1, 2, 3):
            progresso(f"Gerando {i} de 3…")  # ao fechar o painel, o passo seguinte não começa
            passos.append(i)
            passou.set()
            assert solto.wait(LIMITE)
        return Resultado("pronto", "3 geradas", [], None)

    fila = fabrica()
    p = fila.pedir_tarefa("ia", Path("ep1"), [1], gera_em_passos)
    assert passou.wait(LIMITE)
    parada = threading.Thread(target=fila.parar, kwargs={"timeout": LIMITE})
    parada.start()
    assert esperar(fila._parando.is_set)
    solto.set()
    parada.join(LIMITE)
    assert not parada.is_alive() and not fila._trabalhador.is_alive()
    final = fila.pedido(p.id)
    assert final.estado == "interrompido" and final.mensagem == "o painel foi fechado no meio deste pedido"
    assert passos == [1] and final.terminado is not None


def test_interrompido_passa_por_except_exception(fabrica):
    passou, solto = threading.Event(), threading.Event()

    def engole(progresso):
        progresso("Baixando 1 de 2…")
        passou.set()
        assert solto.wait(LIMITE)
        try:
            progresso("Baixando 2 de 2…")
        except Exception:  # um item isolado (como o download de uma foto) não segura o fechamento
            return Resultado("pronto", "engoliu", [], None)
        return Resultado("pronto", "seguiu", [], None)

    fila = fabrica()
    p = fila.pedir_tarefa("fotos", Path("ep1"), [1], engole)
    assert passou.wait(LIMITE)
    parada = threading.Thread(target=fila.parar, kwargs={"timeout": LIMITE})
    parada.start()
    assert esperar(fila._parando.is_set)
    solto.set()
    parada.join(LIMITE)
    assert fila.pedido(p.id).mensagem == "o painel foi fechado no meio deste pedido"


def test_tarefa_com_excecao_vira_erro_e_a_fila_segue(fabrica):
    def quebra(progresso):
        raise RuntimeError("falhou a geração")

    fila = fabrica()
    a = fila.pedir_tarefa("ia", Path("ep1"), [1], quebra)
    assert esperar(lambda: fila.pedido(a.id).estado == "erro")
    assert fila.pedido(a.id).mensagem == "falhou a geração"
    b = fila.pedir_tarefa("ia", Path("ep1"), [1], tarefa(resultado=Resultado("pronto", "feito", ["a"], None)))
    assert esperar(lambda: fila.pedido(b.id).estado == "pronto")
    assert (fila.pedido(b.id).mensagem, fila.pedido(b.id).avisos) == ("feito", ["a"])


def test_musica_e_montagem_se_bloqueiam(controle, fabrica):
    liberar, iniciou = threading.Event(), threading.Event()
    fila = fabrica()
    try:
        fila.pedir_tarefa("montar", Path("x/ep1"), [1], tarefa(liberar, iniciou))
        assert iniciou.wait(LIMITE)
        with pytest.raises(PedidoAtivo, match="o corte 1 já está sendo montado"):
            fila.pedir(Path("x/ep1"), 1, FAIXA, -18.0)
        with pytest.raises(PedidoAtivo, match="o corte 1 já está sendo montado"):
            fila.pedir_tarefa("montar", Path("x/ep1"), [1], tarefa())
        assert fila.pedir_tarefa("fotos", Path("x/ep1"), [1], tarefa()).tipo == "fotos"
        assert fila.pedir(Path("x/ep1"), 2, FAIXA, -18.0).numero == 2
    finally:
        liberar.set()


def test_montagem_recusada_com_troca_de_musica_ativa(controle, fabrica):
    controle.preparar(1)
    fila = fabrica()
    fila.pedir(Path("x/ep1"), 1, FAIXA, -18.0)
    assert controle.iniciou[1].wait(LIMITE)
    with pytest.raises(PedidoAtivo, match="o corte 1 já está sendo montado"):
        fila.pedir_tarefa("montar", Path("x/ep1"), [1], tarefa())
    controle.liberar[1].set()


def test_montando_corte_ve_os_dois_tipos(controle, fabrica):
    liberar = threading.Event()
    controle.preparar(2)
    fila = fabrica()
    try:
        montar = fila.pedir_tarefa("montar", Path("x/ep1"), [1], tarefa(liberar))
        fila.pedir(Path("x/ep1"), 2, FAIXA, -18.0)
        fila.pedir_tarefa("fotos", Path("x/ep1"), [3], tarefa())
        assert fila.montando_corte("ep1", 1) and fila.montando_corte("ep1", 2)
        assert not fila.montando_corte("ep1", 3) and not fila.montando_corte("ep2", 1)
    finally:
        liberar.set()
        controle.liberar[2].set()
    assert esperar(lambda: fila.pedido(montar.id).estado == "pronto")
    assert esperar(lambda: not fila.montando_corte("ep1", 1) and not fila.montando_corte("ep1", 2))


# --- histórico gravado, recuperação e cancelamento ----------------------------------------------------------------


def _ler_arquivo(caminho):
    for _ in range(50):  # a leitura pode cruzar com a troca do arquivo (no Windows, PermissionError)
        try:
            return json.loads(caminho.read_text("utf-8"))
        except (OSError, ValueError):
            time.sleep(0.01)
    return json.loads(caminho.read_text("utf-8"))


def _gravar_arquivo(caminho, pedidos):
    caminho.write_text(json.dumps({"formato": 1, "pedidos": pedidos}), "utf-8")


def _dict(id, estado, tipo="ia", **extra):
    base = {
        "id": id, "episodio": "ep1", "numero": 1, "arquivo": "", "volume_db": 0.0, "estado": estado,
        "criado": 10.0, "tipo": tipo, "cortes": [1],
    }
    return {**base, **extra}


def test_pedidos_vao_para_o_arquivo_a_cada_mudanca_de_estado(controle, fabrica, tmp_path):
    arquivo = tmp_path / "painel-fila.json"
    controle.preparar(1)
    fila = fabrica(arquivo=arquivo, base=tmp_path, relogio=lambda: 50.0)
    p = fila.pedir(Path("x/ep1"), 1, FAIXA, -18.0)
    assert controle.iniciou[1].wait(LIMITE)
    assert esperar(lambda: _ler_arquivo(arquivo)["pedidos"][0]["estado"] == "montando")
    gravado = _ler_arquivo(arquivo)
    assert gravado["formato"] == 1
    assert gravado["pedidos"][0] == fila.pedido(p.id).como_dict()
    controle.liberar[1].set()
    assert esperar(lambda: _ler_arquivo(arquivo)["pedidos"][0]["estado"] == "pronto")
    assert _ler_arquivo(arquivo)["pedidos"][0]["terminado"] == 50.0
    assert not (tmp_path / "painel-fila.json.tmp").exists()  # gravação atômica


def test_sem_arquivo_a_fila_fica_so_na_memoria(controle, fabrica, tmp_path):
    fila = fabrica()
    p = fila.pedir(Path("x/ep1"), 1, FAIXA, -18.0)
    assert esperar(lambda: fila.pedido(p.id).estado == "pronto")
    assert list(tmp_path.iterdir()) == []


def test_arquivo_fora_da_area_permitida_e_recusado(controle, tmp_path):
    from esteira.caminhos import EscritaProibida

    with pytest.raises(EscritaProibida):
        Fila(controle, arquivo=Path(tmp_path.anchor) / "fora-do-clipline" / "painel-fila.json")


def test_ao_abrir_ativos_viram_interrompidos_e_nao_rodam(controle, fabrica, tmp_path):
    arquivo = tmp_path / "painel-fila.json"
    _gravar_arquivo(arquivo, [
        _dict("aaaa0001", "pronto", tipo="musica", arquivo="leve/a.mp3", volume_db=-20.0, terminado=11.0,
              anterior={"arquivo": "b.mp3", "titulo": "B", "volume_db": -26.0}),
        _dict("aaaa0002", "montando", progresso="Gerando 1 de 3…"),
        _dict("aaaa0003", "na fila", tipo="fotos", cortes=[1, 2], numero=0),
    ])
    fila = fabrica(arquivo=arquivo, base=tmp_path, relogio=lambda: 99.0)
    montando, na_fila = fila.pedido("aaaa0002"), fila.pedido("aaaa0003")
    assert (montando.estado, montando.mensagem, montando.terminado) == (
        "interrompido", "o painel foi fechado no meio deste pedido", 99.0)
    assert (na_fila.estado, na_fila.mensagem) == ("interrompido", "o painel foi fechado antes de montar este pedido")
    assert na_fila.cortes == [1, 2]
    assert fila.ultimo_pronto("ep1", 1).anterior == {"arquivo": "b.mp3", "titulo": "B", "volume_db": -26.0}
    assert [p.id for p in fila.pedidos()] == ["aaaa0003", "aaaa0002", "aaaa0001"]
    assert not fila.montando() and fila.ativo("ep1", 1, "ia") is None
    assert [p["estado"] for p in _ler_arquivo(arquivo)["pedidos"]] == ["pronto", "interrompido", "interrompido"]
    time.sleep(0.05)
    assert controle.chamadas == []  # nada roda sozinho
    novo = fila.pedir_tarefa("ia", Path("x/ep1"), [1], tarefa())  # o corte não fica travado
    assert esperar(lambda: fila.pedido(novo.id).estado == "pronto")


def test_arquivo_ilegivel_comeca_vazio_e_entradas_ruins_sao_ignoradas(controle, fabrica, tmp_path, capsys):
    arquivo = tmp_path / "painel-fila.json"
    arquivo.write_text("{não é json", "utf-8")
    assert fabrica(arquivo=arquivo, base=tmp_path).pedidos() == []
    assert "ilegível" in capsys.readouterr().err
    _gravar_arquivo(arquivo, [
        "texto", {"id": "x"}, _dict("bbbb0001", "inventado"), _dict("bbbb0002", "pronto", cortes=["1"]),
        _dict("bbbb0003", "pronto", numero="1"), _dict("bbbb0004", "erro", campo_novo=1),
    ])
    assert [p.id for p in fabrica(arquivo=arquivo, base=tmp_path).pedidos()] == ["bbbb0004"]


def test_historico_gravado_tem_os_50_mais_recentes(controle, fabrica, tmp_path):
    arquivo = tmp_path / "painel-fila.json"
    _gravar_arquivo(arquivo, [_dict(f"c{n:07d}", "pronto", tipo="musica", numero=n, cortes=[n]) for n in range(60)])
    fila = fabrica(arquivo=arquivo, base=tmp_path)
    p = fila.pedir(Path("x/ep1"), 99, FAIXA, -18.0)
    assert esperar(lambda: _ler_arquivo(arquivo)["pedidos"][-1]["estado"] == "pronto")
    ids = [d["id"] for d in _ler_arquivo(arquivo)["pedidos"]]
    assert len(ids) == 50 and ids[-1] == p.id and ids[0] == "c0000011"


def test_falha_ao_gravar_so_avisa(controle, fabrica, tmp_path, capsys):
    arquivo = tmp_path / "painel-fila.json"
    arquivo.mkdir()  # um diretório no lugar do arquivo: a troca falha
    fila = fabrica(arquivo=arquivo, base=tmp_path)
    p = fila.pedir(Path("x/ep1"), 1, FAIXA, -18.0)
    assert esperar(lambda: fila.pedido(p.id).estado == "pronto")
    assert "Não consegui gravar a fila do painel" in capsys.readouterr().err


def test_cancelar_na_fila_tira_da_fila_sem_rodar(controle, fabrica, tmp_path):
    controle.preparar(1)
    arquivo = tmp_path / "painel-fila.json"
    fila = fabrica(arquivo=arquivo, base=tmp_path, relogio=lambda: 7.0)
    primeiro = fila.pedir(Path("x/ep1"), 1, FAIXA, -18.0)
    assert controle.iniciou[1].wait(LIMITE)
    segundo = fila.pedir(Path("x/ep1"), 2, FAIXA, -18.0)
    cancelado = fila.cancelar(segundo.id)
    assert (cancelado.estado, cancelado.mensagem) == ("cancelado", "cancelado antes de começar")
    assert cancelado.terminado == 7.0
    assert not fila.montando_corte("ep1", 2)  # o corte fica livre para outro pedido
    assert esperar(lambda: _ler_arquivo(arquivo)["pedidos"][-1]["estado"] == "cancelado")
    with pytest.raises(NaoCancela, match="já terminou"):
        fila.cancelar(segundo.id)
    with pytest.raises(NaoCancela, match="não para no meio"):
        fila.cancelar(primeiro.id)  # música: o ffmpeg não para no meio
    with pytest.raises(KeyError):
        fila.cancelar("naoexiste")
    controle.liberar[1].set()
    assert esperar(lambda: fila.pedido(primeiro.id).estado == "pronto")
    time.sleep(0.05)
    assert [c[1] for c in controle.chamadas] == [1]
    assert fila.pedido(segundo.id).estado == "cancelado"


def test_cancelar_interrompido_descarta(controle, fabrica, tmp_path):
    arquivo = tmp_path / "painel-fila.json"
    _gravar_arquivo(arquivo, [_dict("dddd0001", "na fila")])
    fila = fabrica(arquivo=arquivo, base=tmp_path)
    descartado = fila.cancelar("dddd0001")
    assert descartado.estado == "cancelado"
    assert descartado.mensagem == "interrompido e descartado: não vai rodar de novo"


def test_cancelar_ia_no_meio_para_antes_da_proxima_imagem(fabrica):
    passou, solto = threading.Event(), threading.Event()
    passos = []

    def gera_em_passos(progresso):
        for i in (1, 2, 3):
            progresso(f"Gerando {i} de 3…")
            passos.append(i)
            passou.set()
            assert solto.wait(LIMITE)
        return Resultado("pronto", "3 geradas", [], None)

    fila = fabrica()
    p = fila.pedir_tarefa("ia", Path("ep1"), [1], gera_em_passos)
    assert passou.wait(LIMITE)
    pedido = fila.cancelar(p.id)
    assert (pedido.estado, pedido.cancelando) == ("montando", True)
    assert fila.cancelar(p.id).cancelando  # repetir não muda nada
    solto.set()
    assert esperar(lambda: fila.pedido(p.id).estado == "cancelado")
    final = fila.pedido(p.id)
    assert final.mensagem == "cancelado no meio: o que já ficou pronto foi mantido"
    assert passos == [1] and not final.cancelando and final.terminado is not None


def test_cancelamento_que_chega_tarde_avisa(fabrica):
    passou, solto = threading.Event(), threading.Event()

    def uma_so(progresso):
        progresso("Gerando 1 de 1…")
        passou.set()
        assert solto.wait(LIMITE)
        return Resultado("pronto", "1 gerada", [], None)

    fila = fabrica()
    p = fila.pedir_tarefa("ia", Path("ep1"), [1], uma_so)
    assert passou.wait(LIMITE)
    fila.cancelar(p.id)
    solto.set()
    assert esperar(lambda: fila.pedido(p.id).estado == "pronto")
    assert fila.pedido(p.id).avisos == ["O cancelamento chegou depois do último passo: o pedido terminou."]


@pytest.mark.parametrize("tipo", ["fotos", "montar", "publicar"])
def test_tipos_que_nao_param_no_meio_recusam_cancelar_montando(fabrica, tipo):
    liberar, iniciou = threading.Event(), threading.Event()
    fila = fabrica()
    try:
        p = fila.pedir_tarefa(tipo, Path("ep1"), [1], tarefa(liberar, iniciou))
        assert iniciou.wait(LIMITE)
        with pytest.raises(NaoCancela):
            fila.cancelar(p.id)
    finally:
        liberar.set()
    assert esperar(lambda: fila.pedido(p.id).estado == "pronto")


def test_ouvintes_sao_avisados_a_cada_mudanca(fabrica):
    liberar, iniciou = threading.Event(), threading.Event()
    fila = fabrica()
    avisos = []
    parar_de_ouvir = fila.ouvir(lambda: avisos.append(1))
    fila.ouvir(lambda: 1 / 0)  # um ouvinte quebrado não atrapalha os outros nem a fila
    p = fila.pedir_tarefa("ia", Path("ep1"), [1], tarefa(liberar, iniciou, "Gerando 1 de 1…"))
    assert iniciou.wait(LIMITE)
    assert esperar(lambda: len(avisos) >= 3)  # na fila, montando e o progresso
    liberar.set()
    assert esperar(lambda: fila.pedido(p.id).estado == "pronto")
    assert esperar(lambda: len(avisos) >= 4)
    parar_de_ouvir()
    antes = len(avisos)
    fila.acordar()
    assert len(avisos) == antes
