import pytest

from esteira import dividida
from esteira.dividida import (
    dividir_planos,
    enquadrar_painel,
    intervalos_na_saida,
    legenda_no_meio,
    partir_legenda,
    trechos_divididos,
)
from esteira.enquadrar import Cena, Rosto, TrechoVoz, enquadrar_cena
from esteira.legenda import escrever_ass
from esteira.modelos import Cue
from esteira.planos import Plano

P1 = Rosto("P1", 0.3, 0.4, 0.1, 0.2)
P2 = Rosto("P2", 0.7, 0.45, 0.1, 0.2)
LIGACAO = {"V1": "P1", "V2": "P2"}


def _alternando(inicio, duracoes, vozes=("V1", "V2")):
    """Turnos emendados, alternando as vozes, com as durações dadas."""
    turnos, t = [], inicio
    for i, duracao in enumerate(duracoes):
        turnos.append(TrechoVoz(t, t + duracao, vozes[i % 2]))
        t += duracao
    return turnos


def test_monologo_nao_divide():
    assert trechos_divididos([TrechoVoz(0, 30, "V1")], 0, 30) == []


def test_dialogo_rapido_divide():
    vozes = [TrechoVoz(0, 10, "V1"), *_alternando(10, [2, 2.5, 2, 3]), TrechoVoz(19.5, 40, "V1")]
    # V1 10 s | V1 2 (emenda: 12 s) | V2 2,5 | V1 2 | V2 3 | V1 20,5: só três curtos, de 12 a 19,5
    assert trechos_divididos(vozes, 0, 40) == [(12, 19.5)]


def test_sai_no_comeco_do_turno_longo():
    vozes = [TrechoVoz(0, 10, "V1"), *_alternando(10, [2, 2.5, 2, 3, 2], ("V2", "V1")), TrechoVoz(21.5, 40, "V2")]
    # o último curto de V2 emenda com o monólogo de V2: a tela dividida acaba em 19,5
    assert trechos_divididos(vozes, 0, 40) == [(10, 19.5)]


def test_dois_turnos_curtos_nao_bastam():
    vozes = [TrechoVoz(0, 10, "V1"), TrechoVoz(10, 12, "V2"), TrechoVoz(12, 30, "V1")]
    assert trechos_divididos(vozes, 0, 30) == []


def test_interjeicao_curtissima_nao_conta():
    vozes = [TrechoVoz(0, 10, "V1"), TrechoVoz(10, 10.4, "V2"), TrechoVoz(10.5, 12, "V1"),
             TrechoVoz(12, 12.3, "V2"), TrechoVoz(12.4, 30, "V1")]
    assert trechos_divididos(vozes, 0, 30) == []


def test_aham_por_cima_da_fala_nao_conta():
    vozes = [TrechoVoz(0, 30, "V1"), TrechoVoz(5, 6, "V2"), TrechoVoz(9, 10, "V2"), TrechoVoz(14, 15, "V2")]
    assert trechos_divididos(vozes, 0, 30) == []


def test_histerese_turno_medio_mantem_a_tela_dividida():
    # entra com 3 curtos; um turno de 5 s (entre TURNO_CURTO e TURNO_LONGO) não tira; o de 9 s tira
    vozes = [TrechoVoz(0, 8, "V1"), *_alternando(8, [2, 2, 2, 5, 2], ("V2", "V1")), TrechoVoz(21, 30, "V1")]
    assert trechos_divididos(vozes, 0, 30) == [(8, 21)]


def test_turno_medio_sozinho_nao_entra():
    vozes = _alternando(0, [8, 5, 5, 5, 8])
    assert trechos_divididos(vozes, 0, 31) == []


def test_pausa_antes_do_turno_longo_fecha_no_fim_da_fala():
    vozes = [*_alternando(0, [2, 2, 2, 2]), TrechoVoz(11, 30, "V1")]  # 3 s de silêncio antes do monólogo
    assert trechos_divididos(vozes, 0, 30) == [(0, 8)]


def test_pausa_longa_quebra_a_sequencia():
    vozes = [TrechoVoz(0, 2, "V1"), TrechoVoz(2, 4, "V2"), TrechoVoz(7, 9, "V1"), TrechoVoz(20, 30, "V2")]
    assert trechos_divididos(vozes, 0, 30) == []


def test_tela_cheia_curta_entre_duas_divididas_vira_dividida():
    # pausa de 2 s quebra a sequência; os 2 s de tela cheia entre as duas divididas viram dividida
    vozes = [*_alternando(0, [2, 2, 2]), *_alternando(8, [2, 2, 2], ("V2", "V1")), TrechoVoz(14, 30, "V1")]
    assert trechos_divididos(vozes, 0, 30) == [(0, 14)]


def test_divididas_separadas_por_solo_longo_ficam_separadas():
    vozes = _alternando(0, [2, 2, 2, 14, 2, 2, 2, 14], ("V2", "V1"))
    assert trechos_divididos(vozes, 0, 40) == [(0, 6), (20, 26)]


def test_dividida_curta_nao_entra():
    vozes = [TrechoVoz(0, 10, "V1"), *_alternando(10, [1, 1, 1]), TrechoVoz(13, 30, "V2")]
    assert trechos_divididos(vozes, 0, 30) == []


def test_encosta_na_borda_da_cena():
    vozes = [TrechoVoz(0, 2, "V1"), *_alternando(2, [2, 2, 2], ("V2", "V1")), TrechoVoz(8, 9.5, "V1")]
    assert trechos_divididos(vozes, 0, 10) == [(0, 10)]


def test_enquadrar_painel_deixa_espaco_para_a_legenda_embaixo():
    cima, baixo = enquadrar_painel(P1, False), enquadrar_painel(P1, True)
    assert cima["pessoa"] == "P1" and cima["x"] == P1.x and cima["zoom"] == 1.35
    olhos = P1.y - P1.altura * 0.1
    altura = 1 / cima["zoom"]

    def olhos_no_painel(painel):
        return (olhos - (painel["y"] - altura / 2)) / altura

    assert olhos_no_painel(cima) == pytest.approx(dividida.OLHOS_EM_CIMA, abs=1e-3)
    assert olhos_no_painel(baixo) == pytest.approx(dividida.OLHOS_EMBAIXO, abs=1e-3)


def _dialogo():
    return [TrechoVoz(0, 10, "V1"), *_alternando(10, [2, 2.5, 2, 3, 2], ("V2", "V1")), TrechoVoz(21.5, 40, "V2")]


def _planos(cena, vozes):
    return enquadrar_cena(cena, vozes, LIGACAO)[0]


def _sem_buracos(planos, inicio, fim):
    assert planos[0].inicio == inicio and planos[-1].fim == fim
    assert all(a.fim == b.inicio for a, b in zip(planos, planos[1:]))


def test_dividir_planos_com_os_dois_rostos_na_cena():
    cena = Cena(0, 40, [P1, P2])
    vozes = _dialogo()
    planos = dividir_planos(_planos(cena, vozes), [cena], vozes, LIGACAO)
    _sem_buracos(planos, 0, 40)
    divididos = [p for p in planos if p.divisao]
    assert [(p.inicio, p.fim) for p in divididos] == [(10, 19.5)]
    cima, baixo = divididos[0].divisao
    assert (cima["pessoa"], baixo["pessoa"]) == ("P1", "P2")  # a da esquerda vai em cima
    assert divididos[0].zoom == 1.0 and divididos[0].x == pytest.approx(0.5)
    assert all(p.fim - p.inicio >= 2.0 for p in planos)


def test_sem_os_dois_rostos_nao_divide():
    cena = Cena(0, 40, [P1])
    vozes = _dialogo()
    planos = _planos(cena, vozes)
    assert dividir_planos(planos, [cena], vozes, LIGACAO) == planos


def test_rosto_sem_voz_ligada_nao_entra():
    cena = Cena(0, 40, [P1, P2])
    vozes = _dialogo()
    planos = _planos(cena, vozes)
    assert dividir_planos(planos, [cena], vozes, {"V1": "P1"}) == planos


def test_so_na_cena_em_que_os_dois_aparecem():
    cenas = [Cena(0, 15, [P1]), Cena(15, 40, [P1, P2])]
    vozes = [TrechoVoz(0, 10, "V1"), *_alternando(10, [2, 2, 2, 2, 2, 2], ("V2", "V1")), TrechoVoz(22, 40, "V2")]
    planos = [p for cena in cenas for p in _planos(cena, vozes)]
    novos = dividir_planos(planos, cenas, vozes, LIGACAO)
    _sem_buracos(novos, 0, 40)
    assert [(p.inicio, p.fim) for p in novos if p.divisao] == [(15, 22)]


def test_pedaco_curto_colado_entra_na_tela_dividida():
    cena = Cena(0, 30, [P1, P2])
    vozes = [TrechoVoz(0, 9, "V1"), *_alternando(9, [2, 2, 2], ("V2", "V1")), TrechoVoz(15, 30, "V1")]
    planos = [Plano(0, 8, x=0.3, zoom=1.35), Plano(8, 9.5, x=0.7, zoom=1.35), Plano(9.5, 30, x=0.3, zoom=1.35)]
    novos = dividir_planos(planos, [cena], vozes, LIGACAO)
    _sem_buracos(novos, 0, 30)
    assert [(p.inicio, p.fim, bool(p.divisao)) for p in novos] == [(0, 8, False), (8, 15, True), (15, 30, False)]


def test_intervalos_na_saida_emendam_os_segmentos():
    dividido = Plano(10, 20, divisao=[{"pessoa": "P1", "x": 0.3, "y": 0.5, "zoom": 1.35}] * 2)
    segmentos = [(5, 8, Plano(0, 10)), (12, 15, dividido), (16, 18, dividido), (18, 22, Plano(20, 30))]
    assert intervalos_na_saida(segmentos) == [(3, 8)]


def test_partir_legenda_nas_trocas_de_layout():
    cues = [Cue(0, 2, ["antes"]), Cue(2.5, 3.5, ["na troca"]), Cue(4.0, 4.9, ["dentro"]), Cue(5.85, 7, ["fim"])]
    partes = partir_legenda(cues, [(3.0, 6.0)])
    assert [(c.inicio, c.fim, c.linhas[0]) for c in partes] == [
        (0, 2, "antes"), (2.5, 3.0, "na troca"), (3.0, 3.5, "na troca"), (4.0, 4.9, "dentro"), (6.0, 7, "fim"),
    ]  # o pedaço de 5,85 a 6,0 sumiu (só piscaria)


def test_legenda_vai_para_a_emenda_so_na_tela_dividida(tmp_path):
    arquivo = tmp_path / "l.ass"
    escrever_ass([Cue(0, 1, ["fora"]), Cue(1, 2, ["dentro"])], arquivo)
    texto = legenda_no_meio(arquivo.read_text("utf-8"), [(1.0, 2.0)])
    fora = next(linha for linha in texto.splitlines() if linha.endswith("fora"))
    dentro = next(linha for linha in texto.splitlines() if linha.endswith("dentro"))
    assert r"\pos(540,1530)" in fora
    assert dividida.POSICAO_LEGENDA in dentro and "1530" not in dentro


def test_legenda_por_palavra_tambem_vai_para_a_emenda(tmp_path):
    arquivo = tmp_path / "l.ass"
    escrever_ass([Cue(1, 2, ["olá Brasil"], palavras=[[1.0, 1.4], [1.5, 2.0]])], arquivo, estilo="palavra")
    texto = legenda_no_meio(arquivo.read_text("utf-8"), [(1.0, 2.0)])
    eventos = [linha for linha in texto.splitlines() if linha.startswith("Dialogue:")]
    assert len(eventos) == 2 and all(dividida.POSICAO_LEGENDA in e for e in eventos)
