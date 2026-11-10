import pytest

from esteira.legenda import corrigir_palavras, escrever_ass, escrever_srt, montar_cues, ocultar_durante
from esteira.modelos import Cue, Palavra as P


def falas(textos, passo=0.5):
    return [P(t, i * passo, (i + 1) * passo) for i, t in enumerate(textos)]


def inteiro(palavras):
    return [(palavras[0].inicio, palavras[-1].fim)]


def test_tres_a_seis_palavras_e_duas_linhas():
    p = falas(f"palavra{i}" for i in range(20))
    cues = montar_cues(p, inteiro(p))
    for cue in cues:
        assert 3 <= len(" ".join(cue.linhas).split()) <= 6
        assert 1 <= len(cue.linhas) <= 2
        assert all(len(linha) <= 28 for linha in cue.linhas)


def test_quebra_em_virgula_antes_do_limite():
    p = falas(["um", "dois", "três,", "quatro", "cinco", "seis", "sete"])
    assert " ".join(montar_cues(p, inteiro(p))[0].linhas) == "um dois três"


def test_nao_quebra_virgula_com_menos_de_tres_palavras():
    p = falas(["sim,", "eu", "acho", "isso", "certo."])
    assert " ".join(montar_cues(p, inteiro(p))[0].linhas).startswith("sim, eu acho")


def test_minusculas_preservando_nomes_e_siglas():
    p = falas(["O", "Gripen", "da", "ONU", "voa."])
    assert " ".join(montar_cues(p, inteiro(p))[0].linhas) == "o Gripen da ONU voa"


def test_nome_do_glossario_mantem_maiuscula_no_inicio():
    p = falas(["Gripen", "é", "um", "caça."])
    assert " ".join(montar_cues(p, inteiro(p), ["Gripen"])[0].linhas).startswith("Gripen")


def test_palavra_minuscula_do_glossario_nao_preserva_maiuscula():
    p = falas(["E", "o", "Massa", "voltou."])
    texto = " ".join(montar_cues(p, inteiro(p), ["Tudo é Política"])[0].linhas)
    assert texto == "e o Massa voltou"


def test_fim_de_frase_fecha_a_tela_com_duas_palavras():
    p = falas(["muito", "técnica.", "Qual", "que", "é", "a", "dificuldade?"])
    assert " ".join(montar_cues(p, inteiro(p))[0].linhas) == "muito técnica"


def test_fim_de_frase_nao_fica_preso_a_frase_seguinte():
    p = falas(["polêmico.", "Vou", "falar", "da", "Espanha."])
    assert montar_cues(p, inteiro(p))[0].linhas == ["polêmico"]


def test_junta_parte_com_hifen_a_palavra_anterior():
    p = falas(["esporte", "-washing", "é", "assim."])
    assert " ".join(montar_cues(p, inteiro(p))[0].linhas) == "esporte-washing é assim"


def test_remove_pontuacao_final():
    p = falas(["isso", "é", "verdade?"])
    assert montar_cues(p, inteiro(p))[0].linhas == ["isso é verdade"]


def test_palavra_removida_nao_aparece():
    p = falas(["um", "dois", "três", "quatro"])
    cues = montar_cues(p, [(0, 0.5), (1.0, 2.0)])
    assert "dois" not in " ".join(cues[0].linhas)


def test_tempos_usam_faixas_finais():
    p = [P("um", 10, 10.5), P("dois", 10.5, 11), P("três", 11, 11.5)]
    cue = montar_cues(p, [(10, 11.5)])[0]
    assert (cue.inicio, cue.fim) == (0, 1.5)


def test_corrige_nome_ignorando_acento_e_caixa():
    p = falas(["o", "pio", "pacelli,", "e", "a", "embraer"])
    r = corrigir_palavras(p, ["Pio Pacelli", "Embraer"])
    assert [x.texto for x in r] == ["o", "Pio", "Pacelli,", "e", "a", "Embraer"]
    assert r[1].inicio == p[1].inicio


def test_srt_formato(tmp_path):
    a = tmp_path / "a.srt"
    escrever_srt([Cue(1, 2.5, ["olá", "Brasil"])], a)
    assert a.read_text("utf-8") == "1\n00:00:01,000 --> 00:00:02,500\nolá\nBrasil\n"


def test_ass_estilo(tmp_path):
    a = tmp_path / "a.ass"
    escrever_ass([Cue(1, 2.5, ["olá", "{Brasil}"])], a)
    texto = a.read_text("utf-8")
    assert "Montserrat" in texto and ",90," in texto
    assert r"\an8\pos(540,1530)" in texto
    assert r"olá\N\{Brasil\}" in texto
    assert "0:00:01.00,0:00:02.50" in texto


def test_ass_pinta_destaque(tmp_path):
    escrever_ass([Cue(0, 1, ["o Gripen, sueco"], "gripen")], tmp_path / "a.ass")
    assert r"{\c&H00FFFF&}Gripen{\c&HFFFFFF&}," in (tmp_path / "a.ass").read_text("utf-8")


def test_ass_destaque_com_maiuscula_acento_e_pontuacao(tmp_path):
    escrever_ass([Cue(0, 1, ["a (Última) vez"], "ULTIMA!")], tmp_path / "a.ass")
    assert r"({\c&H00FFFF&}Última{\c&HFFFFFF&})" in (tmp_path / "a.ass").read_text("utf-8")


def test_ass_sem_destaque_nao_muda(tmp_path):
    escrever_ass([Cue(0, 1, ["o Gripen, sueco"])], tmp_path / "a.ass")
    texto = (tmp_path / "a.ass").read_text("utf-8")
    assert r"c&H" not in texto
    assert "o Gripen, sueco" in texto


def test_ass_destaque_ausente_nao_pinta(tmp_path):
    escrever_ass([Cue(0, 1, ["o Gripen"], "lula")], tmp_path / "a.ass")
    assert r"c&H" not in (tmp_path / "a.ass").read_text("utf-8")


def test_destaque_pinta_so_uma_palavra(tmp_path):
    escrever_ass([Cue(0, 1, ["lula e", "lula"], "lula")], tmp_path / "a.ass")
    assert (tmp_path / "a.ass").read_text("utf-8").count(r"{\c&H00FFFF&}") == 1


def test_destaque_continua_escapando_texto(tmp_path):
    escrever_ass([Cue(0, 1, ["{x} Lula"], "lula")], tmp_path / "a.ass")
    assert r"\{x\} {\c&H00FFFF&}Lula{\c&HFFFFFF&}" in (tmp_path / "a.ass").read_text("utf-8")


def test_ocultar_remove_cue_dentro():
    assert ocultar_durante([Cue(1, 2, ["a"])], [(0.5, 2.5)]) == []


def test_ocultar_encurta_borda():
    assert ocultar_durante([Cue(1, 3, ["a"])], [(2, 4)]) == [Cue(1, 2, ["a"])]
    assert ocultar_durante([Cue(1, 3, ["a"])], [(0, 2)]) == [Cue(2, 3, ["a"])]


def test_ocultar_cue_que_contem_imagem_fica_com_o_lado_maior():
    assert ocultar_durante([Cue(0, 10, ["a"])], [(2, 4)]) == [Cue(4, 10, ["a"])]
    assert ocultar_durante([Cue(0, 10, ["a"])], [(6, 8)]) == [Cue(0, 6, ["a"])]
    assert ocultar_durante([Cue(0, 10, ["a"])], [(4, 6)]) == [Cue(0, 4, ["a"])]


def test_ocultar_sem_intervalo_ou_fora_nao_muda():
    cues = [Cue(0, 1, ["a"]), Cue(5, 6, ["b"])]
    assert ocultar_durante(cues, [(2, 4)]) == cues
    assert ocultar_durante(cues, []) == cues


def test_ocultar_varios_intervalos_e_preserva_destaque():
    r = ocultar_durante([Cue(0, 10, ["a"], "a"), Cue(11, 12, ["b"])], [(0, 2), (3, 5), (10.5, 12)])
    assert r == [Cue(5, 10, ["a"], "a")]
