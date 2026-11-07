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


# --- gravar_textos / versão do post ---

from esteira.caminhos import EscritaProibida  # noqa: E402
from esteira.publicar.post import gravar_textos, secoes_somente_leitura, versao_post  # noqa: E402


def test_gravar_sem_mudar_e_identico(tmp_path):
    c = _post(tmp_path, POST_CORTE_1)
    antes = c.read_bytes()
    versao = gravar_textos(c, ler_post(c), base=tmp_path)
    assert c.read_bytes() == antes
    assert versao == versao_post(c)


def test_gravar_crlf_identico(tmp_path):
    c = tmp_path / "post.md"
    c.write_bytes(POST_CORTE_1.replace("\n", "\r\n").encode("utf-8"))
    antes = c.read_bytes()
    gravar_textos(c, ler_post(c), base=tmp_path)
    assert c.read_bytes() == antes
    textos = ler_post(c)
    textos.instagram = "Linha nova um\n\nLinha nova dois"
    gravar_textos(c, textos, base=tmp_path)
    dados = c.read_bytes()
    assert b"\n" not in dados.replace(b"\r\n", b"")
    assert ler_post(c).instagram == "Linha nova um\n\nLinha nova dois"


def test_gravar_troca_so_os_campos(tmp_path):
    c = _post(tmp_path, POST_CORTE_1)
    antes = secoes_somente_leitura(c)
    assert "Música" in antes
    novos = Textos("Novo título", "Nova descrição\n\nSegundo parágrafo", "Novo insta", "Novo tiktok")
    gravar_textos(c, novos, base=tmp_path)
    assert ler_post(c) == novos
    assert secoes_somente_leitura(c) == antes
    assert "Título: Novo título\n" in c.read_text("utf-8")


def test_gravar_e_atomico(tmp_path):
    c = _post(tmp_path, POST_CORTE_1)
    gravar_textos(c, Textos("T", "D", "I", "K"), base=tmp_path)
    assert list(tmp_path.glob("*.tmp")) == []


def test_gravar_fora_de_cortes_recusa(tmp_path):
    c = _post(tmp_path, POST_CORTE_1)
    with pytest.raises(EscritaProibida):
        gravar_textos(c, ler_post(c))
    assert list(tmp_path.glob("*.tmp")) == []


def test_gravar_sem_secoes_levanta_erro(tmp_path):
    c = _post(tmp_path, "# Textos\n\n## YouTube\nTítulo: x\n")
    with pytest.raises(ErroPost):
        gravar_textos(c, Textos("a", "b", "c", "d"), base=tmp_path)


def test_versao_muda_com_conteudo(tmp_path):
    a = _post(tmp_path, POST_CORTE_1)
    va = versao_post(a)
    b = tmp_path / "outro.md"
    b.write_text(POST_CORTE_1 + "x", "utf-8")
    assert va != versao_post(b)
    assert len(va) == 64 and int(va, 16) >= 0
