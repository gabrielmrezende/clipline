import json

import pytest

from esteira import fluxo_planos, planos
from esteira.fluxo_planos import planejar_episodio
from esteira.pessoas import gravar_pessoas, ler_pessoas
from esteira.midia import ErroMidia
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


OUTRO = {**CORTE, "numero": 2, "titulo": "Outro", "inicio": 30.0, "fim": 50.0}


def _dois_cortes(pasta, trechos=None):
    (pasta / "aprovados.json").write_text(json.dumps({"cortes": [CORTE, OUTRO]}), "utf-8")
    trechos = trechos or [(0.0, 10.0, "V1"), (10.0, 20.0, "V2"), (30.0, 50.0, "V2")]
    vozes = {"trechos": [{"inicio": a, "fim": b, "voz": v} for a, b, v in trechos]}
    (pasta / "transcricao" / "vozes.json").write_text(json.dumps(vozes), "utf-8")


def test_ligacao_conta_so_a_fala_dentro_dos_cortes(episodio):
    pasta, _ = episodio
    vozes = {"trechos": [{"inicio": 0.0, "fim": 10.0, "voz": "V1"}, {"inicio": 10.0, "fim": 20.0, "voz": "V2"},
                         {"inicio": 100.0, "fim": 400.0, "voz": "V1"}]}
    (pasta / "transcricao" / "vozes.json").write_text(json.dumps(vozes), "utf-8")
    planejar_episodio(pasta, None, detectar=detectar_falso)
    assert ler_pessoas(pasta)[0]["V1"] == "P1"


def test_numeros_nao_perde_ligacao_de_outro_corte(episodio):
    pasta, _ = episodio
    _dois_cortes(pasta)
    resultado = planejar_episodio(pasta, {2}, forcar=True, detectar=detectar_falso)
    assert list(resultado) == [2]
    assert ler_pessoas(pasta)[0] == {"V1": "P1", "V2": "P2"}
    assert not (_trabalho(pasta) / "enquadramento.json").exists()
    assert (pasta / "02-outro" / "trabalho" / "enquadramento.json").exists()


def test_reaproveita_rostos_gravados(episodio):
    pasta, _ = episodio
    _dois_cortes(pasta)
    chamadas = []

    def contando(video, inicio, fim):
        chamadas.append(inicio)
        return detectar_falso(video, inicio, fim)

    planejar_episodio(pasta, None, detectar=contando)
    assert chamadas == [0.0, 30.0]
    assert (_trabalho(pasta) / "rostos.json").exists()
    chamadas.clear()
    assert planejar_episodio(pasta, None, detectar=contando) == {1: "mantido (já existe)", 2: "mantido (já existe)"}
    assert chamadas == []
    planejar_episodio(pasta, {1}, forcar=True, detectar=contando)
    assert chamadas == [0.0]


def test_erro_na_deteccao_de_um_corte_nao_para_os_outros(episodio):
    pasta, _ = episodio
    _dois_cortes(pasta)

    def quebra_no_primeiro(video, inicio, fim):
        if inicio == 0.0:
            raise RuntimeError("modelo quebrou")
        return detectar_falso(video, inicio, fim)

    resultado = planejar_episodio(pasta, None, detectar=quebra_no_primeiro)
    assert resultado[1] == "erro: detecção: modelo quebrou"
    assert resultado[2].startswith("ok")
    assert (pasta / "02-outro" / "trabalho" / "enquadramento.json").exists()


def test_falha_na_folha_de_pessoas_vira_alerta(episodio, monkeypatch):
    pasta, _ = episodio

    def quebra(*args):
        raise ErroMidia("ffmpeg falhou")

    monkeypatch.setattr(fluxo_planos, "folha_pessoas", quebra)
    resultado = planejar_episodio(pasta, None, detectar=detectar_falso)
    assert resultado == {0: "ok com alertas: pessoas.jpg: erro ffmpeg falhou", 1: "ok"}
    assert ler_pessoas(pasta) is not None


def test_pessoas_ilegivel_para_sem_gravar(episodio):
    pasta, _ = episodio
    (pasta / "transcricao" / "pessoas.json").write_text("{ruim", "utf-8")
    resultado = planejar_episodio(pasta, None, detectar=detectar_falso)
    assert list(resultado) == [0] and resultado[0].startswith("erro: pessoas.json ilegível: ")
    assert (pasta / "transcricao" / "pessoas.json").read_text("utf-8") == "{ruim"
    assert not (_trabalho(pasta) / "enquadramento.json").exists()


def test_alerta_sem_tempo_fica_igual():
    assert fluxo_planos._relativo_ao_corte("sem tempo nenhum", 10) == "sem tempo nenhum"
    assert fluxo_planos._relativo_ao_corte("00:05 sem rosto", 70) == "01:15 sem rosto"


def test_preparar_com_alertas_de_planos_ilegivel(episodio):
    pasta, _ = episodio
    trabalho = _trabalho(pasta)
    trabalho.mkdir(parents=True)
    (trabalho / "alertas-planos.json").write_text("[ruim", "utf-8")
    preparar_teste(pasta)
    registro = json.loads((trabalho / "registro.json").read_text("utf-8"))
    assert registro["alertas"][0].startswith("alertas-planos.json ilegível: ")


def _x_dos_planos(pasta):
    return [(p.inicio, p.fim, p.x) for p in ler_planos(_trabalho(pasta))]


def detectar_dois(video, inicio, fim):
    """A à esquerda e B à direita durante todo o corte."""
    deteccoes = []
    t = inicio
    while t < fim:
        deteccoes += [Deteccao(t, 0.3, 0.4, 0.1, 0.2, ROSTO_A), Deteccao(t, 0.7, 0.4, 0.1, 0.2, ROSTO_B)]
        t += 0.5
    return deteccoes


def test_forcar_preserva_ligacao_editada_e_religar_recalcula(episodio):
    pasta, _ = episodio
    planejar_episodio(pasta, None, detectar=detectar_falso)
    ligacao, assinaturas, _ = ler_pessoas(pasta)
    assert ligacao == {"V1": "P1", "V2": "P2"}
    gravar_pessoas(pasta, {"V1": "P2", "V2": "P1"}, assinaturas, {"P1": "Arthur"})

    planejar_episodio(pasta, None, forcar=True, detectar=detectar_dois)
    assert ler_pessoas(pasta)[0] == {"V1": "P2", "V2": "P1"}
    assert ler_pessoas(pasta)[2] == {"P1": "Arthur"}
    assert _x_dos_planos(pasta) == [(0.0, 10.0, 0.7), (10.0, 20.0, 0.3)]

    planejar_episodio(pasta, None, religar=True, detectar=detectar_falso)
    assert ler_pessoas(pasta)[0] == {"V1": "P1", "V2": "P2"}
    assert ler_pessoas(pasta)[2] == {"P1": "Arthur"}
    assert _x_dos_planos(pasta) == [(0.0, 10.0, 0.3), (10.0, 20.0, 0.7)]


def test_forcar_acrescenta_voz_ainda_nao_ligada(episodio):
    pasta, _ = episodio
    gravar_pessoas(pasta, {"V1": "P1"}, {"P1": ROSTO_A}, {})
    planejar_episodio(pasta, None, forcar=True, detectar=detectar_falso)
    assert ler_pessoas(pasta)[0] == {"V1": "P1", "V2": "P2"}


def test_convidado_e_quem_mais_fala():
    from esteira.enquadrar import TrechoVoz
    from esteira.fluxo_planos import convidado_do_episodio

    vozes = [TrechoVoz(0, 30, "V3"), TrechoVoz(30, 40, "V1"), TrechoVoz(40, 45, "V2"), TrechoVoz(45, 50, "V9")]
    assert convidado_do_episodio(vozes, {"V1": "P1", "V2": "P3", "V3": "P2"}) == "P2"
    assert convidado_do_episodio(vozes, {}) is None


# [enquadramento] no clipline.toml (docs/enquadramento.md)


@pytest.fixture
def enquadramento(monkeypatch):
    from esteira import config
    from esteira.midia import Midia

    sondados = []

    def ligar(**campos):
        monkeypatch.setattr(config, "atual", lambda: config.Config(**campos))

    def sondar(video):
        sondados.append(video)
        return Midia(20.0, 1920, 1080, True)

    monkeypatch.setattr(fluxo_planos, "sondar", sondar)
    return ligar, sondados


def detectar_andando(video, inicio, fim):
    """Como detectar_falso, mas a pessoa A anda da esquerda (0,3) para 0,4 a partir de 4 s."""
    return [
        Deteccao(d.tempo, 0.3 if d.tempo < 4 else 0.4, d.y, d.largura, d.altura, d.assinatura) if d.tempo < 10 else d
        for d in detectar_falso(video, inicio, fim)
    ]


def test_sem_enquadramento_nao_sonda_o_video_nem_muda_o_arquivo(episodio, enquadramento):
    pasta, _ = episodio
    ligar, sondados = enquadramento
    ligar()
    planejar_episodio(pasta, None, detectar=detectar_andando)
    assert sondados == []
    texto = (_trabalho(pasta) / "enquadramento.json").read_text("utf-8")
    assert "trajeto" not in texto and "divisao" not in texto


def test_suave_grava_trajeto_de_quem_anda(episodio, enquadramento):
    pasta, folhas = episodio
    ligar, sondados = enquadramento
    ligar(enquadramento_suave=True)
    assert planejar_episodio(pasta, None, detectar=detectar_andando) == {1: "ok"}
    andando, parado = ler_planos(_trabalho(pasta))
    assert (andando.inicio, andando.fim, andando.x, andando.zoom) == (0.0, 10.0, pytest.approx(0.36), 1.35)
    assert andando.trajeto[0][1] == pytest.approx(0.3, abs=0.002)
    assert andando.trajeto[-1][1] == pytest.approx(0.4, abs=0.002)
    assert parado.trajeto is None
    assert len(sondados) == 1
    assert folhas["planos"][0][0].trajeto == andando.trajeto  # a folha recebe o plano suave


ROSTO_DIREITA = [0.0, 1.0, 0.0]


def detectar_os_dois(video, inicio, fim):
    """As duas pessoas na tela o tempo todo: A à esquerda, B à direita."""
    deteccoes = []
    t = inicio
    while t < fim:
        deteccoes.append(Deteccao(t, 0.3, 0.4, 0.1, 0.2, ROSTO_A))
        deteccoes.append(Deteccao(t, 0.7, 0.4, 0.1, 0.2, ROSTO_DIREITA))
        t += 0.5
    return deteccoes


def _dialogo_rapido(pasta):
    """Corte de 0 a 30 s: V1 fala 8 s, três turnos curtos alternando, V1 fala 16 s."""
    (pasta / "aprovados.json").write_text(json.dumps({"cortes": [{**CORTE, "fim": 30.0}]}), "utf-8")
    trechos = [(0.0, 8.0, "V1"), (8.0, 10.0, "V2"), (10.0, 12.0, "V1"), (12.0, 14.0, "V2"), (14.0, 30.0, "V1")]
    vozes = {"trechos": [{"inicio": a, "fim": b, "voz": v} for a, b, v in trechos]}
    (pasta / "transcricao" / "vozes.json").write_text(json.dumps(vozes), "utf-8")
    gravar_pessoas(pasta, {"V1": "P1", "V2": "P2"}, {"P1": ROSTO_A, "P2": ROSTO_DIREITA}, {"P1": "Arthur"})


def test_tela_dividida_no_dialogo_rapido(episodio, enquadramento, monkeypatch):
    pasta, folhas = episodio
    monkeypatch.setattr(planos, "detectar_cortes", lambda video, inicio, fim: [])
    _dialogo_rapido(pasta)
    ligar, _ = enquadramento
    ligar(enquadramento_tela_dividida=True)
    assert planejar_episodio(pasta, None, detectar=detectar_os_dois) == {1: "ok"}
    lista = ler_planos(_trabalho(pasta))
    assert [(p.inicio, p.fim, bool(p.divisao)) for p in lista] == [(0.0, 8.0, False), (8.0, 14.0, True),
                                                                    (14.0, 30.0, False)]
    cima, baixo = lista[1].divisao
    assert (cima["pessoa"], cima["x"], baixo["pessoa"], baixo["x"]) == ("P1", 0.3, "P2", 0.7)
    texto = (_trabalho(pasta) / "enquadramento.json").read_text("utf-8")
    assert texto.count('"divisao"') == 1 and "trajeto" not in texto
    rotulos = folhas["planos"][1]
    assert rotulos[1] == "2 Arthur + P2 · p8 p9 p10 p11 p12 p13"


def test_sem_tela_dividida_o_dialogo_fica_como_sempre(episodio, enquadramento, monkeypatch):
    pasta, _ = episodio
    monkeypatch.setattr(planos, "detectar_cortes", lambda video, inicio, fim: [])
    _dialogo_rapido(pasta)
    ligar, _ = enquadramento
    ligar(enquadramento_suave=True)  # rostos parados: nada de trajeto
    planejar_episodio(pasta, None, detectar=detectar_os_dois)
    lista = ler_planos(_trabalho(pasta))
    assert not any(p.divisao or p.trajeto for p in lista)


def test_clipline_toml_ilegivel_para_o_planos(episodio, monkeypatch):
    from esteira import config

    pasta, _ = episodio

    def quebrado():
        raise config.ErroConfig("clipline.toml ilegível: x")

    monkeypatch.setattr(config, "atual", quebrado)
    assert planejar_episodio(pasta, None, detectar=detectar_falso) == {0: "erro: clipline.toml ilegível: x"}
