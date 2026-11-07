from pathlib import Path

import pytest

from esteira.publicar.post import ErroPost, Textos, conferir_textos, ler_post

POST_CORTE_1 = (Path(__file__).parent / "dados_post_corte1.md").read_text("utf-8")
CREDITO = "Música: Ice Flow — Kevin MacLeod (incompetech.com), licença CC BY 4.0"
TODAS = {"youtube", "instagram", "tiktok"}


def _post(tmp_path: Path, texto: str) -> Path:
    caminho = tmp_path / "post.md"
    caminho.write_text(texto, "utf-8")
    return caminho


def test_le_secoes_do_post(tmp_path):
    textos = ler_post(_post(tmp_path, POST_CORTE_1))
    assert textos.youtube_titulo == "A Fórmula 1 faz sportswashing? 🏎️🌍 #Shorts"
    assert textos.youtube_descricao.startswith("A Fórmula 1 é usada por países")
    assert textos.youtube_descricao.endswith("#Sportswashing #Geopolítica #Shorts")
    assert textos.instagram.startswith("A Fórmula 1 é usada por países")
    assert textos.tiktok.endswith("#política")
    assert "## Música" not in textos.tiktok
    assert "Faixa:" not in textos.tiktok


def test_secao_faltando(tmp_path):
    with pytest.raises(ErroPost, match="seção ## TikTok"):
        ler_post(_post(tmp_path, POST_CORTE_1.split("## TikTok")[0]))


def test_sem_post(tmp_path):
    with pytest.raises(ErroPost, match="post.md não encontrado"):
        ler_post(tmp_path / "post.md")


def test_textos_bons_sem_problemas(tmp_path):
    assert conferir_textos(ler_post(_post(tmp_path, POST_CORTE_1)), CREDITO, TODAS) == []


def test_problemas_dos_textos():
    t = Textos("", "a < b " + CREDITO, "x" * 2201 + CREDITO, "sem crédito")
    assert conferir_textos(t, CREDITO, TODAS) == [
        "youtube: título vazio",
        "youtube: descrição com < ou >",
        "instagram: texto com mais de 2200 caracteres",
        "tiktok: falta o crédito da música",
    ]


def test_titulo_e_descricao_longos():
    t = Textos("x" * 101, "d" * 5001, "i", "t")
    assert conferir_textos(t, None, {"youtube"}) == [
        "youtube: título com mais de 100 caracteres",
        "youtube: descrição com mais de 5000 caracteres",
    ]


def test_confere_so_as_redes_pedidas():
    t = Textos("Título", "sem crédito", "sem crédito", "sem crédito")
    assert conferir_textos(t, CREDITO, {"tiktok"}) == ["tiktok: falta o crédito da música"]


def test_credito_com_ponto_final_aceita_texto_sem_ponto():
    t = Textos("T", CREDITO, CREDITO, CREDITO)
    assert conferir_textos(t, CREDITO + ".", TODAS) == []


def test_corte_sem_musica_nao_exige_credito():
    assert conferir_textos(Textos("T", "d", "i", "t"), None, {"youtube"}) == []


def test_instagram_com_mais_de_30_hashtags():
    t = Textos("T", "d", " ".join(f"#h{i}" for i in range(31)), "t")
    assert conferir_textos(t, None, {"instagram"}) == ["instagram: mais de 30 hashtags"]
