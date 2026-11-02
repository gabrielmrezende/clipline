from esteira.modelos import Corte, Cue
from esteira.planos import Plano
from esteira.receita import (
    Imagem,
    Musica,
    Receita,
    duracao_principal,
    gravar_receita,
    ler_receita,
    validar_receita,
)


def _receita(tmp_path, imagens=None, musica=None, legenda=None):
    (tmp_path / "imagens").mkdir(exist_ok=True)
    (tmp_path / "imagens" / "01-a.jpg").write_bytes(b"x")
    (tmp_path / "imagens" / "02-b.jpg").write_bytes(b"x")
    return Receita(
        [(10.0, 20.0)],
        [Plano(10.0, 20.0)],
        legenda if legenda is not None else [Cue(0.0, 5.0, ["o gripen é um caça"], "Gripen,")],
        imagens or [],
        musica,
    )


def test_receita_ida_e_volta(tmp_path):
    r = Receita(
        [(1.0, 3.0)],
        [Plano(1.0, 3.0, 0.3, 0.5, 1.35)],
        [Cue(0.0, 1.0, ["o gripen"], "gripen")],
        [Imagem(0.5, 1.5, "imagens/01-a.jpg")],
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
    r = _receita(
        tmp_path,
        [Imagem(1.0, 3.0, "imagens/01-a.jpg"), Imagem(3.0, 6.0, "imagens/02-b.jpg")],
        Musica(str(musica), -20),
    )
    assert validar_receita(r, tmp_path) == []


def test_imagem_fora_do_corte(tmp_path):
    r = _receita(tmp_path, [Imagem(8.0, 11.0, "imagens/01-a.jpg")])
    assert validar_receita(r, tmp_path) == ["imagem 1 passa do fim do corte"]


def test_imagens_sobrepostas(tmp_path):
    r = _receita(
        tmp_path, [Imagem(1.0, 4.0, "imagens/01-a.jpg"), Imagem(3.0, 6.0, "imagens/02-b.jpg")]
    )
    assert validar_receita(r, tmp_path) == ["imagens 1 e 2 se sobrepõem"]


def test_imagem_curta_ou_longa(tmp_path):
    r = _receita(
        tmp_path, [Imagem(0.0, 1.5, "imagens/01-a.jpg"), Imagem(2.0, 7.5, "imagens/02-b.jpg")]
    )
    assert validar_receita(r, tmp_path) == [
        "imagem 1 fora de 2 a 5 segundos",
        "imagem 2 fora de 2 a 5 segundos",
    ]


def test_arquivo_de_imagem_inexistente(tmp_path):
    r = _receita(tmp_path, [Imagem(1.0, 3.0, "imagens/99-z.jpg")])
    assert validar_receita(r, tmp_path) == ["imagem 1 não encontrada: imagens/99-z.jpg"]


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


def test_imagem_com_inicio_negativo(tmp_path):
    r = _receita(tmp_path, [Imagem(-1.0, 2.0, "imagens/01-a.jpg")])
    assert validar_receita(r, tmp_path) == ["imagem 1 começa antes do corte"]


def test_legenda_passa_do_fim_do_corte(tmp_path):
    r = _receita(tmp_path, legenda=[Cue(0.0, 5.0, ["o gripen é um caça"], None), Cue(9.0, 10.5, ["fim"], None)])
    assert validar_receita(r, tmp_path) == ["tela 2 passa do fim do corte"]
    r = _receita(tmp_path, legenda=[Cue(9.0, 10.05, ["fim"], None)])
    assert validar_receita(r, tmp_path) == []
