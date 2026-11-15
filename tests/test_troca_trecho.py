import json
from datetime import datetime
from pathlib import Path

import pytest

from esteira.cortar import IMAGENS_SUGERIDAS, TRABALHO, pasta_do_corte, preparar_episodio
from esteira.fluxo_imagens import chave_momento
from esteira.modelos import Corte, Cue, Palavra
from esteira.musica import Faixa, gravar_uso, ler_uso
from esteira.painel import troca_trecho
from esteira.painel.troca_trecho import (
    MARCADOR,
    SAIU_DO_TRECHO,
    VIDEO_GUARDADO,
    alinhar,
    aprovados_com_trecho,
    copiar_aprovados,
    correcoes_da_legenda,
    cues_geradas,
    deslocar_alertas,
    no_corte,
    no_episodio,
    planejar_renomeacoes,
    pode_iniciar,
    pode_terminar,
    prever,
    reaplicar_correcoes,
    recuperar_trechos_interrompidos,
    remapear_momentos,
    sobreposicoes,
    tempo_texto,
    trocar_trecho,
)
from esteira.pedidos import Momento, ler_pedidos
from esteira.publicar.post import versao_dos_bytes
from esteira.receita import Musica, gravar_receita, ler_receita

AGORA = datetime(2026, 11, 7, 10, 0, 0)
# Uma palavra por segundo, cada uma fechando frase; sem as palavras 40 e 41: uma pausa de 2,1 s que o preparar corta.
PALAVRAS = [{"texto": f"w{t}.", "inicio": float(t), "fim": t + 0.9} for t in range(1, 200) if t not in (40, 41)]
CORTE = Corte(1, "Um", 10.0, 80.9, "tenso")
OUTRO = Corte(2, "Dois", 120.0, 199.9, "tenso")
FAIXAS = [
    Faixa("Tensa B", "tenso", 100.5, "tenso/Tensa B.mp3", "Música: Tensa B"),
    Faixa("Tensa C", "tenso", 90.0, "tenso/Tensa C.mp3", "Música: Tensa C"),
]
ORIGEM = {"modelo": "teste", "data": "2026-11-01T10:00", "regras": "abc"}


def _p(texto, inicio, fim):
    return Palavra(texto, inicio, fim)


# --- lógica pura ------------------------------------------------------------------------------------------------


def test_tempo_texto():
    assert tempo_texto(724.06) == "12:04,1"
    assert tempo_texto(3723.4) == "1:02:03,4"


def test_alinhar_vai_para_a_palavra_mais_proxima():
    palavras = [_p("a", 1.0, 1.5), _p("b.", 2.0, 2.6), _p("c", 3.0, 3.4)]
    assert alinhar(palavras, 1.9, 3.3) == (2.0, 3.4)
    assert alinhar(palavras, 0.2, 2.0) == (1.0, 1.5)
    with pytest.raises(ValueError):
        alinhar([], 1, 2)


def test_pode_iniciar_e_terminar_seguem_o_validar():
    palavras = [_p("Oi", 0.0, 0.4), _p("tudo", 0.5, 0.8), _p("bem.", 0.9, 1.2), _p("E", 1.3, 1.5), _p("aí", 3.0, 3.3)]
    assert [pode_iniciar(palavras, i) for i in range(5)] == [True, False, False, True, True]  # "aí": pausa > 0,7 s
    assert [pode_terminar(palavras, i) for i in range(5)] == [False, False, True, True, True]


def test_no_episodio_e_no_corte():
    faixas = [(10.0, 20.0), (25.0, 30.0)]
    assert no_episodio(0, faixas) == 10.0
    assert no_episodio(12.0, faixas) == 27.0
    assert no_episodio(15.0, faixas) == 30.0
    assert no_episodio(15.5, faixas) is None
    assert no_corte(27.0, faixas) == 12.0
    assert no_corte(22.0, faixas) == 10.0  # na pausa cortada: o ponto do corte
    assert no_corte(5.0, faixas) == 0.0 and no_corte(40.0, faixas) == 15.0


def test_remapear_momentos_desloca_e_descarta():
    antigas = [(10.0, 39.975), (41.925, 80.9)]
    novas = [(20.0, 39.975), (41.925, 100.9)]
    momentos = [
        Momento(5.0, 8.0, "f", "foto", "Antes"),
        Momento(15.0, 18.0, "f", "foto", "Ministro"),
        Momento(35.0, 38.0, "f", "ia", "Estádio"),
        Momento(50.0, 52.0, "f", "foto", "Já descartado", descartar=True, motivo="do dono"),
    ]
    novos, deslocados, saidos = remapear_momentos(momentos, antigas, novas, 20.0, 100.9)
    assert momentos[0].descartar is False  # não mexe na lista de entrada
    assert (novos[0].descartar, novos[0].motivo, novos[0].inicio) == (True, SAIU_DO_TRECHO, 5.0)
    assert (novos[1].inicio, novos[1].fim) == (5.0, 8.0)
    assert (novos[2].inicio, novos[2].fim) == (25.0, 28.0)
    assert novos[3].motivo == "do dono"
    assert deslocados == 3 and saidos == ["0:05 Antes"]


def test_correcoes_da_legenda_voltam_na_tela_de_mesmo_texto():
    geradas = [Cue(0.0, 1.0, ["um dois"]), Cue(1.0, 2.0, ["tres quatro"]), Cue(2.0, 3.0, ["cinco"])]
    guardadas = [Cue(0.0, 1.0, ["um dois"]), Cue(1.0, 2.0, ["três quatro"]), Cue(2.0, 3.0, ["cinco seis"])]
    correcoes = correcoes_da_legenda(guardadas, geradas)
    assert correcoes == [(["tres quatro"], ["três quatro"]), (["cinco"], ["cinco seis"])]
    novas_geradas = [Cue(0.0, 1.0, ["tres quatro"], palavras=[[0, 0.5], [0.5, 1]]), Cue(1.0, 2.0, ["sete"])]
    novas, perdidas = reaplicar_correcoes(novas_geradas, correcoes)
    assert novas[0].linhas == ["três quatro"] and novas[0].palavras == [[0, 0.5], [0.5, 1]]
    assert perdidas == [["cinco seis"]]
    assert novas_geradas[0].linhas == ["tres quatro"]


def test_reaplicar_com_outro_numero_de_palavras_tira_o_tempo_por_palavra():
    cues = [Cue(0.0, 1.0, ["um dois"], palavras=[[0, 0.5], [0.5, 1]])]
    novas, _ = reaplicar_correcoes(cues, [(["um dois"], ["um dois três"])])
    assert novas[0].palavras is None


def test_planejar_renomeacoes_nunca_sobrescreve():
    movidos = {"0015-a-1.jpg", "0015-a-2.jpg", "0035-b-ia-1.jpg", "0040-c.png"}
    existentes = movidos | {"0020-c.png", "dono.jpg"}
    pares, paradas = planejar_renomeacoes(
        [("0015-a", "0005-a"), ("0035-b", "0025-b"), ("0040-c", "0020-c")], movidos, existentes
    )
    assert pares == [("0015-a-1.jpg", "0005-a-1.jpg"), ("0015-a-2.jpg", "0005-a-2.jpg"),
                     ("0035-b-ia-1.jpg", "0025-b-ia-1.jpg")]
    assert paradas == {"0040-c"}


def test_planejar_renomeacoes_destino_disputado():
    movidos = {"0015-a-1.jpg", "0016-a-1.jpg"}
    pares, paradas = planejar_renomeacoes([("0015-a", "0005-a"), ("0016-a", "0005-a")], movidos, movidos)
    assert pares == [("0015-a-1.jpg", "0005-a-1.jpg")] and paradas == {"0016-a"}


def test_deslocar_alertas_dos_planos():
    alertas = ["00:25 rosto perdido", "00:05 sem rosto", "sem tempo"]
    assert deslocar_alertas(alertas, 10.0, 20.0, 100.9) == ["00:15 rosto perdido", "sem tempo"]


def test_aprovados_com_trecho_preserva_o_resto():
    conteudo = json.dumps(
        {"origem": ORIGEM, "cortes": [{"numero": 1, "titulo": "Um", "inicio": 1, "fim": 2, "clima": "leve", "x": 1},
                                      {"numero": 2, "titulo": "Dois", "inicio": 5, "fim": 9, "clima": "leve"}]}
    ).encode()
    dados = json.loads(aprovados_com_trecho(conteudo, 1, 3.0, 4.5))
    assert dados["origem"] == ORIGEM
    assert dados["cortes"][0] == {"numero": 1, "titulo": "Um", "inicio": 3.0, "fim": 4.5, "clima": "leve", "x": 1}
    assert dados["cortes"][1]["inicio"] == 5


def test_sobreposicoes_viram_aviso():
    assert sobreposicoes([CORTE, OUTRO], 1, 50.0, 125.9) == ["O trecho novo sobrepõe o corte 2 (Dois) em 5,9 s."]
    assert sobreposicoes([CORTE, OUTRO], 1, 20.0, 100.9) == []


def test_copiar_aprovados_nunca_sobrescreve(tmp_path):
    primeira = copiar_aprovados(tmp_path, b"a", lambda: AGORA, tmp_path)
    segunda = copiar_aprovados(tmp_path, b"b", lambda: AGORA, tmp_path)
    assert primeira.name == "aprovados-20261107-100000.json" and segunda.name == "aprovados-20261107-100000-2.json"
    assert primeira.read_bytes() == b"a" and segunda.read_bytes() == b"b"


# --- a troca, com o preparar de verdade --------------------------------------------------------------------------


def _preparar(musicas):
    def preparar(pasta, numero, nomes):
        return preparar_episodio(pasta, {numero}, forcar=True, nomes=nomes, pasta_musicas=musicas, medir_silencio=None)[
            numero
        ]

    return preparar


class Montar:
    def __init__(self, resultado="ok", conteudo=b"novo", excecao=None):
        self.resultado, self.conteudo, self.excecao = resultado, conteudo, excecao
        self.chamadas = []

    def __call__(self, pasta, numero):
        destino = pasta_do_corte(pasta, CORTE)
        self.chamadas.append((numero, ler_receita(destino / TRABALHO)))
        (destino / "corte.mp4").write_bytes(self.conteudo)
        if self.excecao is not None:
            raise self.excecao
        return self.resultado


@pytest.fixture
def cenario(tmp_path):
    """Episódio em tmp_path/ep1 (tmp_path é a base de escrita e a pasta dos cortes), corte 1 preparado e montado,
    com música escolhida no painel, uma tela da legenda corrigida, três momentos de imagem e as imagens prontas."""
    musicas = tmp_path / "musicas"
    for faixa in FAIXAS:
        (musicas / faixa.arquivo).parent.mkdir(parents=True, exist_ok=True)
        (musicas / faixa.arquivo).write_bytes(b"ID3")
    (musicas / "catalogo.json").write_text(json.dumps([f.__dict__ for f in FAIXAS]), "utf-8")
    pasta = tmp_path / "ep1"
    (pasta / "transcricao").mkdir(parents=True)
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(PALAVRAS), "utf-8")
    (pasta / "episodio.json").write_text(json.dumps({"video": str(tmp_path / "ep.mp4"), "duracao": 210}), "utf-8")
    aprovados = {"origem": ORIGEM, "cortes": [CORTE.__dict__, OUTRO.__dict__]}
    (pasta / "aprovados.json").write_text(json.dumps(aprovados, ensure_ascii=False, indent=2), "utf-8")
    assert _preparar(musicas)(pasta, 1, []).startswith("ok")
    destino = pasta_do_corte(pasta, CORTE)
    trabalho = destino / TRABALHO

    receita = ler_receita(trabalho)
    assert receita.faixas == [(10.0, 39.975), (41.925, 80.9)]
    escolhida = Musica(str(musicas / "tenso/Tensa C.mp3"), -26.0, "Tensa C", "Música: Tensa C")
    receita.musica = escolhida
    novas = cues_geradas([Palavra(**p) for p in PALAVRAS], 20.0, 100.9, [(20.0, 39.975), (41.925, 100.9)], [])
    textos_novos = [c.linhas for c in novas]
    fica = next(i for i, c in enumerate(receita.legenda) if c.inicio > 15 and c.linhas in textos_novos)
    sai = next(i for i, c in enumerate(receita.legenda) if c.linhas not in textos_novos)
    corrigidas = {fica: receita.legenda[fica].linhas, sai: receita.legenda[sai].linhas}
    receita.legenda[fica].linhas = ["FICA corrigida"]
    receita.legenda[sai].linhas = ["SAI corrigida"]
    gravar_receita(trabalho, receita)
    uso = {"ep1/" + destino.name: {"arquivo": "tenso/Tensa C.mp3", "data": "2026-11-01T09:00:00"}}
    gravar_uso(musicas, uso)

    momentos = [
        Momento(5.0, 8.0, "f", "foto", "Antes"),
        Momento(15.0, 18.0, "f", "foto", "Ministro", escolhas=[1]),
        Momento(35.0, 38.0, "f", "ia", "Estádio", prompt="um estádio vazio", aprovado=True),
    ]
    chaves = [chave_momento(m) for m in momentos]
    momentos[1].no_video = f"{chaves[1]}-1.jpg"
    (trabalho / "pedidos.json").write_text(
        json.dumps({"origem": ORIGEM, "momentos": [m.__dict__ for m in momentos]}, ensure_ascii=False), "utf-8"
    )
    imagens = destino / IMAGENS_SUGERIDAS
    imagens.mkdir()
    nomes = [f"{chaves[0]}-1.jpg", f"{chaves[1]}-1.jpg", f"{chaves[1]}-2.jpg", f"{chaves[2]}-ia-1.jpg"]
    for nome in nomes:
        (imagens / nome).write_bytes(nome.encode())
    (imagens / "guia.md").write_text("guia antigo", "utf-8")
    (trabalho / "sugeridas.json").write_text(json.dumps(nomes[:3]), "utf-8")
    (trabalho / "creditos.json").write_text(json.dumps({nomes[1]: {"autor": "A"}}), "utf-8")
    (trabalho / "ia.json").write_text(
        json.dumps([{"momento": chaves[2], "arquivo": nomes[3], "prompt": "um estádio vazio"}]), "utf-8"
    )
    (trabalho / "alertas-planos.json").write_text(json.dumps(["00:25 rosto perdido", "00:05 sem rosto"]), "utf-8")
    (destino / "corte.mp4").write_bytes(b"antigo")
    return {
        "pasta": pasta, "destino": destino, "trabalho": trabalho, "musicas": musicas, "base": tmp_path,
        "escolhida": escolhida, "uso": uso, "chaves": chaves, "nomes": nomes, "corrigidas": corrigidas,
    }


def _versao(pasta: Path) -> str:
    return versao_dos_bytes((pasta / "aprovados.json").read_bytes())


def _trocar(c, montar, inicio=20.0, fim=100.9, **extra):
    extra.setdefault("versao", _versao(c["pasta"]))
    return trocar_trecho(
        c["pasta"], 1, inicio, fim, preparar=extra.pop("preparar", _preparar(c["musicas"])), montar=montar,
        nomes=lambda: [], base=c["base"], pasta_musicas=c["musicas"], agora=lambda: AGORA, **extra,
    )


def _foto(c) -> dict[str, bytes]:
    """Tudo o que a troca pode mexer, para comparar antes e depois."""
    arquivos = {}
    for raiz in (c["pasta"], c["musicas"]):
        for arquivo in sorted(raiz.rglob("*")):
            if arquivo.is_file() and "registro.json" != arquivo.name:
                arquivos[arquivo.relative_to(c["base"]).as_posix()] = arquivo.read_bytes()
    return arquivos


def test_troca_preserva_musica_legenda_e_momentos(cenario):
    c = cenario
    antes = (c["pasta"] / "aprovados.json").read_bytes()
    montar = Montar()
    resultado = _trocar(c, montar)
    assert resultado.estado == "pronto", resultado.mensagem
    assert resultado.mensagem == "Trecho novo: 0:20,0 a 1:40,9 (80,9 s)."

    dados = json.loads((c["pasta"] / "aprovados.json").read_text("utf-8"))
    assert dados["origem"] == ORIGEM
    assert (dados["cortes"][0]["inicio"], dados["cortes"][0]["fim"]) == (20.0, 100.9)
    assert dados["cortes"][1] == OUTRO.__dict__
    assert (c["pasta"] / "aprovados-anteriores" / "aprovados-20261107-100000.json").read_bytes() == antes

    receita = ler_receita(c["trabalho"])
    assert receita.faixas == [(20.0, 39.975), (41.925, 100.9)]
    assert receita.musica == c["escolhida"]
    assert ler_uso(c["musicas"]) == c["uso"]
    linhas = [cue.linhas for cue in receita.legenda]
    assert ["FICA corrigida"] in linhas and ["SAI corrigida"] not in linhas
    srt = (c["trabalho"] / "legenda.srt").read_text("utf-8")
    assert "FICA corrigida" in srt and "SAI corrigida" not in srt
    assert montar.chamadas == [(1, receita)]
    assert (c["destino"] / "corte.mp4").read_bytes() == b"novo"

    momentos = ler_pedidos(c["trabalho"])
    assert [(m.inicio, m.descartar) for m in momentos] == [(5.0, True), (5.0, False), (25.0, False)]
    assert momentos[0].motivo == SAIU_DO_TRECHO
    chaves = c["chaves"]
    novas = [chave_momento(m) for m in momentos]
    assert novas[0] == chaves[0]
    assert momentos[1].no_video == f"{novas[1]}-1.jpg"
    imagens = c["destino"] / IMAGENS_SUGERIDAS
    presentes = sorted(a.name for a in imagens.iterdir())
    assert presentes == sorted(
        [f"{chaves[0]}-1.jpg", f"{novas[1]}-1.jpg", f"{novas[1]}-2.jpg", f"{novas[2]}-ia-1.jpg", "guia.md"]
    )
    assert (imagens / f"{novas[1]}-1.jpg").read_bytes() == f"{chaves[1]}-1.jpg".encode()
    pedidos = json.loads((c["trabalho"] / "pedidos.json").read_text("utf-8"))
    assert pedidos["origem"] == ORIGEM
    sugeridas = json.loads((c["trabalho"] / "sugeridas.json").read_text("utf-8"))
    assert sugeridas == sorted([f"{chaves[0]}-1.jpg", f"{novas[1]}-1.jpg", f"{novas[1]}-2.jpg"])
    assert json.loads((c["trabalho"] / "creditos.json").read_text("utf-8")) == {f"{novas[1]}-1.jpg": {"autor": "A"}}
    ia = json.loads((c["trabalho"] / "ia.json").read_text("utf-8"))
    assert ia == [{"momento": novas[2], "arquivo": f"{novas[2]}-ia-1.jpg", "prompt": "um estádio vazio"}]
    guia = (imagens / "guia.md").read_text("utf-8")
    assert f"{novas[1]}-1.jpg" in guia and f"{novas[2]}-ia-1.jpg" in guia and chaves[1] not in guia
    assert json.loads((c["trabalho"] / "alertas-planos.json").read_text("utf-8")) == ["00:15 rosto perdido"]

    assert not (c["trabalho"] / MARCADOR).exists() and not (c["trabalho"] / VIDEO_GUARDADO).exists()
    assert any("Antes" in a and "descartado" in a for a in resultado.avisos)
    assert any("SAI corrigida" in a for a in resultado.avisos)
    assert not any(a.startswith("sem música") for a in resultado.avisos)


def test_troca_que_falha_na_montagem_volta_tudo(cenario):
    c = cenario
    foto = _foto(c)
    resultado = _trocar(c, Montar("erro: ffmpeg falhou"))
    assert resultado.estado == "erro"
    assert resultado.mensagem == "a montagem falhou: ffmpeg falhou. O corte voltou ao que era."
    assert _foto(c) == foto
    assert not (c["pasta"] / "aprovados-anteriores" / "aprovados-20261107-100000.json").exists()


def test_troca_que_falha_no_preparar_volta_tudo(cenario):
    c = cenario
    foto = _foto(c)
    montar = Montar()
    resultado = _trocar(c, montar, preparar=lambda pasta, n, nomes: "erro: algo")
    assert resultado.estado == "erro" and resultado.mensagem.startswith("o preparar falhou: algo")
    assert _foto(c) == foto and montar.chamadas == []


def test_painel_fechando_no_meio_volta_tudo_e_sai(cenario):
    c = cenario
    foto = _foto(c)

    class Fechando(BaseException):
        pass

    with pytest.raises(Fechando):
        _trocar(c, Montar(excecao=Fechando()))
    assert _foto(c) == foto


def test_queda_no_meio_e_desfeita_na_proxima_abertura(cenario, monkeypatch):
    c = cenario
    foto = _foto(c)

    class Queda(BaseException):
        pass

    with monkeypatch.context() as m:
        m.setattr(troca_trecho, "_desfazer_sem_erro", lambda guarda: None)  # o processo morreu: ninguém desfaz
        with pytest.raises(Queda):
            _trocar(c, Montar(conteudo=b"pela metade", excecao=Queda()))
    assert (c["trabalho"] / MARCADOR).exists() and (c["trabalho"] / VIDEO_GUARDADO).exists()
    assert recuperar_trechos_interrompidos(c["base"]) == [f"ep1/{c['destino'].name}"]
    assert _foto(c) == foto
    assert (c["destino"] / "corte.mp4").read_bytes() == b"antigo"


def test_marcador_de_troca_terminada_so_e_limpo(cenario):
    c = cenario
    (c["trabalho"] / MARCADOR).write_text(json.dumps({"fase": "pronto", "arquivos": {}, "renomeados": [],
                                                      "video": True, "uso": None}), "utf-8")
    (c["trabalho"] / VIDEO_GUARDADO).write_bytes(b"velho")
    foto = _foto(c)
    assert recuperar_trechos_interrompidos(c["base"]) == []
    assert not (c["trabalho"] / MARCADOR).exists() and not (c["trabalho"] / VIDEO_GUARDADO).exists()
    del foto[f"ep1/{c['destino'].name}/{TRABALHO}/{MARCADOR}"]
    del foto[f"ep1/{c['destino'].name}/{TRABALHO}/{VIDEO_GUARDADO}"]
    assert _foto(c) == foto


def test_video_aberto_nao_muda_nada(cenario):
    c = cenario
    foto = _foto(c)

    def substituir(origem, destino):
        raise PermissionError("WinError 32")

    resultado = _trocar(c, Montar(), substituir=substituir, dormir=lambda s: None)
    assert resultado.estado == "erro" and "aberto" in resultado.mensagem
    assert _foto(c) == foto


def test_versao_diferente_recusa(cenario):
    c = cenario
    foto = _foto(c)
    resultado = _trocar(c, Montar(), versao="outra")
    assert resultado.estado == "erro" and "mudou" in resultado.mensagem
    assert _foto(c) == foto


def test_trecho_invalido_recusa(cenario):
    c = cenario
    foto = _foto(c)
    resultado = _trocar(c, Montar(), inicio=20.0, fim=50.9)
    assert resultado.estado == "erro" and "duração fora de 60 a 120 segundos" in resultado.mensagem
    assert _foto(c) == foto


def test_corte_nao_preparado_so_muda_o_aprovados(cenario):
    c = cenario
    antes = (c["pasta"] / "aprovados.json").read_bytes()
    montar = Montar()
    resultado = trocar_trecho(
        c["pasta"], 2, 110.0, 190.9, _versao(c["pasta"]), _preparar(c["musicas"]), montar, lambda: [],
        base=c["base"], pasta_musicas=c["musicas"], agora=lambda: AGORA,
    )
    assert resultado.estado == "pronto" and "só o aprovados.json mudou" in resultado.mensagem
    dados = json.loads((c["pasta"] / "aprovados.json").read_text("utf-8"))
    assert (dados["cortes"][1]["inicio"], dados["cortes"][1]["fim"]) == (110.0, 190.9)
    assert (c["pasta"] / "aprovados-anteriores" / "aprovados-20261107-100000.json").read_bytes() == antes
    assert montar.chamadas == [] and not pasta_do_corte(c["pasta"], OUTRO).exists()


def test_corte_aprovado_avisa_que_a_aprovacao_deixa_de_valer(cenario):
    c = cenario
    final = c["destino"] / "video-final"
    final.mkdir()
    video = final / "corte-aprovado.mp4"
    video.write_bytes(b"aprovado")
    info = video.stat()
    (c["trabalho"] / "aprovado.json").write_text(json.dumps(
        {"arquivo": "corte-aprovado.mp4", "tamanho": info.st_size, "modificado_ns": info.st_mtime_ns}), "utf-8")
    palavras = [Palavra(**p) for p in PALAVRAS]
    previsao = prever(c["pasta"], CORTE, [CORTE, OUTRO], 20.0, 100.9, palavras, [])
    assert any("aprovação deixa de valer" in p for p in previsao.perdas)
    resultado = _trocar(c, Montar())
    assert resultado.estado == "pronto"
    assert "aprovação deixa de valer" in resultado.avisos[0]
    assert video.read_bytes() == b"aprovado"


def test_prever_conta_o_que_muda_e_o_que_se_perde(cenario):
    c = cenario
    foto = _foto(c)
    palavras = [Palavra(**p) for p in PALAVRAS]
    previsao = prever(c["pasta"], CORTE, [CORTE, OUTRO], 20.0, 100.9, palavras, [])
    texto = "\n".join(previsao.resumo)
    assert "preparado e montado de novo" in texto
    assert "A música continua a mesma: Tensa C (-26 dB)." in previsao.resumo
    assert "1 tela corrigida no painel volta no trecho novo." in previsao.resumo
    assert "2 momentos de imagem passam para os tempos novos, com as imagens prontas." in previsao.resumo
    assert previsao.perdas == [
        "Correção da legenda que sai do corte: “SAI corrigida”.",
        "Momento de imagem fora do trecho novo (fica descartado): 0:05 Antes.",
    ]
    assert previsao.avisos == []
    sobrepondo = prever(c["pasta"], CORTE, [CORTE, OUTRO], 50.0, 125.9, palavras, None)
    assert sobrepondo.avisos[0].startswith("O trecho novo sobrepõe o corte 2")
    assert any("Glossário ilegível" in a for a in sobrepondo.avisos)
    assert _foto(c) == foto


def test_prever_corte_nao_preparado(cenario):
    c = cenario
    previsao = prever(c["pasta"], OUTRO, [CORTE, OUTRO], 110.0, 190.9, [Palavra(**p) for p in PALAVRAS], [])
    assert previsao.resumo == ["Só o aprovados.json muda: o corte ainda não foi preparado."]
