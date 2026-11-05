from esteira.modelos import Corte, Cue
from esteira.planos import Plano
from esteira.receita import (
    Musica,
    Receita,
    duracao_principal,
    gravar_receita,
    ler_receita,
    validar_receita,
)


def _receita(tmp_path, musica=None, legenda=None):
    return Receita(
        [(10.0, 20.0)],
        [Plano(10.0, 20.0)],
        legenda if legenda is not None else [Cue(0.0, 5.0, ["o gripen é um caça"], "Gripen,")],
        musica=musica,
    )


def test_receita_ida_e_volta(tmp_path):
    r = Receita(
        [(1.0, 3.0)],
        [Plano(1.0, 3.0, 0.3, 0.5, 1.35)],
        [Cue(0.0, 1.0, ["o gripen"], "gripen")],
        Musica("C:/m.mp3", -20),
    )
    gravar_receita(tmp_path, r)
    assert ler_receita(tmp_path) == r


def test_receita_sem_musica_nem_destaque_ida_e_volta(tmp_path):
    r = Receita([(1.0, 3.0)], [], [Cue(0.0, 1.0, ["oi"])], encerramento=False)
    gravar_receita(tmp_path, r)
    assert ler_receita(tmp_path) == r


def test_duracao_principal():
    assert duracao_principal(Receita([(1.0, 3.0), (5.0, 8.5)], [], [])) == 5.5


def test_receita_valida_nao_tem_problemas(tmp_path):
    musica = tmp_path / "m.mp3"
    musica.write_bytes(b"x")
    r = _receita(tmp_path, Musica(str(musica), -20))
    assert validar_receita(r, tmp_path) == []


def test_musica_inexistente_ou_volume_fora(tmp_path):
    r = _receita(tmp_path, musica=Musica(str(tmp_path / "nao.mp3"), -10))
    assert validar_receita(r, tmp_path) == [
        "música não encontrada",
        "volume da música fora de -22 a -18 dB",
    ]


def test_destaque_ausente_da_tela(tmp_path):
    r = _receita(tmp_path, legenda=[Cue(0.0, 1.0, ["o gripen"]), Cue(1.0, 2.0, ["o caça"], "gripen")])
    assert validar_receita(r, tmp_path) == ["destaque 'gripen' não está na tela 2"]


def test_destaque_ignora_maiuscula_e_pontuacao(tmp_path):
    r = _receita(tmp_path, legenda=[Cue(0.0, 1.0, ["Gripen, é caça"], "gripen")])
    assert validar_receita(r, tmp_path) == []


def test_corte_aceita_campos_novos():
    c = Corte(1, "t", 0, 60, "leve")
    assert c.instagram is False
    assert c.data == ""


def test_legenda_passa_do_fim_do_corte(tmp_path):
    r = _receita(tmp_path, legenda=[Cue(0.0, 5.0, ["o gripen é um caça"], None), Cue(9.0, 10.5, ["fim"], None)])
    assert validar_receita(r, tmp_path) == ["tela 2 passa do fim do corte"]
    r = _receita(tmp_path, legenda=[Cue(9.0, 10.05, ["fim"], None)])
    assert validar_receita(r, tmp_path) == []
