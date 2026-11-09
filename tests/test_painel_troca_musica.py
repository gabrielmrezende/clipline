import json
from pathlib import Path

import pytest

from esteira.cortar import TRABALHO, pasta_do_corte
from esteira.modelos import Corte
from esteira.musica import Faixa, ler_uso
from esteira.painel.troca_musica import Resultado, trocar_musica
from esteira.receita import NOME_ARQUIVO, Musica, ler_receita
from tests.auxiliares_painel import criar_episodio

CORTE = Corte(1, "A Fórmula 1 faz sportswashing", 2.0, 20.0, "")
CREDITO_ANTIGO = "Música: Ice Flow — Kevin MacLeod (incompetech.com), licença CC BY 4.0"
NOVA = Faixa("Nova Faixa", "tensao", 120.0, "nova.mp3", "Música: Nova Faixa — Kevin MacLeod (incompetech.com), licença CC BY 4.0")


@pytest.fixture
def cenario(tmp_path):
    musicas = tmp_path / "musicas"
    musicas.mkdir()
    antiga = Musica(str(musicas / "ice.mp3"), -24.0, "Ice Flow", CREDITO_ANTIGO)
    pasta = criar_episodio(tmp_path / "cortes", "ep1", [CORTE], {1}, musica=antiga)
    corte = pasta_do_corte(pasta, CORTE)
    return pasta, corte, musicas, antiga, tmp_path


def _chamar(cenario, montar, faixa=NOVA, volume=-20.0, **extra):
    pasta, _, musicas, _, tmp = cenario
    return trocar_musica(pasta, 1, faixa, volume, montar, base=tmp, pasta_musicas=musicas, **extra)


def test_troca_ok(cenario):
    pasta, corte, musicas, antiga, _ = cenario
    vistas = []

    def montar(p, n):
        receita = ler_receita(corte / TRABALHO)
        vistas.append((p, n, receita.musica))
        return "ok"

    resultado = _chamar(cenario, montar)
    assert resultado == Resultado("pronto", resultado.mensagem, [], antiga)
    assert vistas == [(pasta, 1, Musica(str(musicas / "nova.mp3"), -20.0, "Nova Faixa", NOVA.credito))]
    post = (corte / "post.md").read_text("utf-8")
    assert NOVA.credito in post and CREDITO_ANTIGO not in post
    uso = ler_uso(musicas)
    assert uso[f"ep1/{corte.name}"]["arquivo"] == "nova.mp3"


def test_troca_erro_restaura(cenario):
    _, corte, musicas, _, _ = cenario
    montagem = corte / TRABALHO / NOME_ARQUIVO
    original, post = montagem.read_bytes(), (corte / "post.md").read_bytes()
    resultado = _chamar(cenario, lambda p, n: "erro: ffmpeg falhou")
    assert resultado.estado == "erro" and resultado.mensagem == "erro: ffmpeg falhou"
    assert montagem.read_bytes() == original
    assert (corte / "post.md").read_bytes() == post
    assert not (musicas / "uso.json").exists()


def test_troca_excecao_restaura(cenario):
    _, corte, _, _, _ = cenario
    montagem = corte / TRABALHO / NOME_ARQUIVO
    original = montagem.read_bytes()

    def montar(p, n):
        raise RuntimeError("x")

    resultado = _chamar(cenario, montar)
    assert resultado.estado == "erro" and "x" in resultado.mensagem
    assert montagem.read_bytes() == original


def test_troca_so_volume(cenario):
    _, corte, musicas, antiga, _ = cenario
    post = (corte / "post.md").read_bytes()
    faixa = Faixa("Ice Flow", "calma", 100.0, "ice.mp3", CREDITO_ANTIGO)
    resultado = _chamar(cenario, lambda p, n: "ok", faixa=faixa, volume=-20.0)
    assert resultado.estado == "pronto" and resultado.avisos == []
    assert ler_receita(corte / TRABALHO).musica.volume_db == -20.0
    assert (corte / "post.md").read_bytes() == post
    assert not (musicas / "uso.json").exists()


def test_troca_sem_musica_antiga(tmp_path):
    musicas = tmp_path / "musicas"
    pasta = criar_episodio(tmp_path / "cortes", "ep1", [CORTE], {1})
    corte = pasta_do_corte(pasta, CORTE)
    assert ler_receita(corte / TRABALHO).musica is None
    resultado = trocar_musica(pasta, 1, NOVA, -20.0, lambda p, n: "ok", base=tmp_path, pasta_musicas=musicas)
    assert resultado.estado == "pronto" and resultado.anterior is None
    assert "youtube: crédito antigo não encontrado; confira o crédito" in resultado.avisos
    assert ler_receita(corte / TRABALHO).musica.titulo == "Nova Faixa"
    assert ler_uso(musicas)


def test_troca_credito_falha(cenario):
    _, corte, _, _, _ = cenario
    post = corte / "post.md"
    post.write_bytes(post.read_bytes().replace(b"## TikTok", b"## Outra"))
    resultado = _chamar(cenario, lambda p, n: "ok")
    assert resultado.estado == "pronto"
    assert "crédito não atualizado: post.md sem a seção ## TikTok" in resultado.avisos


def test_troca_sem_post(cenario):
    _, corte, _, _, _ = cenario
    (corte / "post.md").unlink()
    resultado = _chamar(cenario, lambda p, n: "ok")
    assert resultado.estado == "pronto"
    assert resultado.avisos == ["post.md não encontrado: crédito não atualizado"]


def test_corte_inexistente(cenario):
    pasta, _, musicas, _, tmp = cenario
    resultado = trocar_musica(pasta, 9, NOVA, -20.0, lambda p, n: "ok", base=tmp, pasta_musicas=musicas)
    assert resultado == Resultado("erro", "corte 9 não encontrado", [], None)
