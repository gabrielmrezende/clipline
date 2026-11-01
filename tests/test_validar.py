from esteira.modelos import Corte, Palavra
from esteira.validar import validar_trecho


def frase(inicio=0.0, palavras=61):
    lista = [Palavra("Fim.", inicio, inicio + 0.5)]
    t = inicio + 2
    for i in range(palavras):
        texto = "fim." if i == palavras - 1 else "palavra"
        lista.append(Palavra(texto, t, t + 0.9))
        t += 1
    return lista + [Palavra("Depois", t + 1, t + 1.5)]


def corte(inicio, fim):
    return Corte(1, "t", inicio, fim, "leve")


def test_aceita_trecho_correto():
    p = frase()
    assert validar_trecho(p, corte(p[1].inicio, p[-2].fim), 500) == []


def test_recusa_duracao_fora_de_60_a_120():
    p = frase(palavras=30)
    assert any("duração" in x for x in validar_trecho(p, corte(p[1].inicio, p[-2].fim), 500))


def test_recusa_tempo_alem_do_video():
    p = frase()
    assert any("vídeo" in x for x in validar_trecho(p, corte(p[1].inicio, p[-2].fim), 10))


def test_recusa_fim_no_meio_da_frase():
    p = frase()
    assert any("fim" in x for x in validar_trecho(p, corte(p[1].inicio, p[-3].fim), 500))


def test_recusa_inicio_no_meio_da_frase():
    p = frase()
    assert any("início" in x for x in validar_trecho(p, corte(p[5].inicio, p[-2].fim), 500))


def test_recusa_trecho_sem_palavras():
    assert any("palavras" in x for x in validar_trecho([], corte(0, 70), 500))
