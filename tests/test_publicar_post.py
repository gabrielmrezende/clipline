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


MISTO = (
    "## YouTube\r\nTítulo: T\r\n\r\nDescrição:\r\nD\r\n\r\n"
    "## Instagram\r\nInsta\n\n## TikTok\nTik\r\n\r\n## Música\r\nCrédito: c\r\n"
)
SIMPLES = "## YouTube\nTítulo: T\n\nDescrição:\nD\n\n## Instagram\nI\n\n## TikTok\nTik\n"
QUEBRAS = ["\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]


def _bruto(tmp_path: Path, texto: str) -> Path:
    caminho = tmp_path / "post.md"
    caminho.write_bytes(texto.encode("utf-8"))
    return caminho


def test_gravar_fins_de_linha_mistos_mantem_as_outras_secoes(tmp_path):
    c = _bruto(tmp_path, MISTO)
    antes = ler_post(c)
    somente_leitura = secoes_somente_leitura(c)
    antes.instagram = "Insta NOVO"
    gravar_textos(c, antes, base=tmp_path)
    assert c.read_bytes() == MISTO.replace("Insta\n", "Insta NOVO\n").encode("utf-8")
    depois = ler_post(c)
    assert (depois.instagram, depois.tiktok) == ("Insta NOVO", "Tik")
    assert secoes_somente_leitura(c) == somente_leitura == {"Música": "Crédito: c"}


def test_gravar_fins_mistos_linhas_novas_usam_o_fim_predominante(tmp_path):
    c = _bruto(tmp_path, MISTO)
    textos = ler_post(c)
    textos.instagram = "A\n\nB"
    gravar_textos(c, textos, base=tmp_path)
    esperado = MISTO.replace("Insta\n", "A\r\n\r\nB\n")
    assert c.read_bytes() == esperado.encode("utf-8")
    assert ler_post(c).tiktok == "Tik"


@pytest.mark.parametrize("nome", ["YouTube", "Instagram", "TikTok"])
def test_gravar_secao_obrigatoria_repetida_recusa_sem_gravar(tmp_path, nome):
    repetida = {"YouTube": "Título: X\n\nDescrição:\nY\n", "Instagram": "Segundo\n", "TikTok": "Outro\n"}
    c = _bruto(tmp_path, SIMPLES + f"\n## {nome}\n" + repetida[nome])
    antes = c.read_bytes()
    textos = ler_post(c)
    textos.instagram = "NOVO"
    with pytest.raises(ErroPost, match=f"seção ## {nome} repetida"):
        gravar_textos(c, textos, base=tmp_path)
    assert c.read_bytes() == antes
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("quebra", QUEBRAS, ids=[repr(q) for q in QUEBRAS])
def test_gravar_titulo_com_quebra_de_linha_recusa_sem_gravar(tmp_path, quebra):
    c = _bruto(tmp_path, SIMPLES)
    antes = c.read_bytes()
    textos = ler_post(c)
    textos.youtube_titulo = f"abc{quebra}def"
    with pytest.raises(ErroPost, match="não gravado"):
        gravar_textos(c, textos, base=tmp_path)
    assert c.read_bytes() == antes
    assert list(tmp_path.glob("*.tmp")) == []


def test_gravar_que_mudaria_secao_so_de_leitura_recusa(tmp_path):
    c = _bruto(tmp_path, SIMPLES + "\n## Música\nCrédito: c\n")
    antes = c.read_bytes()
    textos = ler_post(c)
    textos.tiktok = "Tik\u2028## Música\u2028Crédito: falso"
    with pytest.raises(ErroPost, match="não gravado"):
        gravar_textos(c, textos, base=tmp_path)
    assert c.read_bytes() == antes


def test_gravar_normaliza_como_o_leitor(tmp_path):
    c = _bruto(tmp_path, SIMPLES)
    textos = ler_post(c)
    textos.instagram = "\n  I  \n"
    gravar_textos(c, textos, base=tmp_path)
    assert c.read_bytes() == SIMPLES.encode("utf-8")
    textos.tiktok = "  Novo\r\nfim  \n\n"
    gravar_textos(c, textos, base=tmp_path)
    assert ler_post(c).tiktok == "Novo\nfim"
    assert c.read_bytes() == SIMPLES.replace("Tik\n", "Novo\nfim\n").encode("utf-8")


def test_gravar_secao_vazia_no_fim_sem_quebra(tmp_path):
    c = _bruto(tmp_path, "## YouTube\r\nTítulo: T\r\n\r\nDescrição:\r\nD\r\n\r\n## Instagram\r\nI\r\n\r\n## TikTok")
    textos = ler_post(c)
    assert textos.tiktok == ""
    textos.tiktok = "Tik"
    gravar_textos(c, textos, base=tmp_path)
    assert c.read_bytes().endswith("## TikTok\r\nTik".encode("utf-8"))
    assert ler_post(c).tiktok == "Tik"


def _falhar(*_args, **_kwargs):
    raise OSError("disco cheio")


def _escrever_metade_e_falhar(self, dados):
    with open(self, "wb") as arquivo:
        arquivo.write(dados[: len(dados) // 2])
    raise OSError("disco cheio")


@pytest.mark.parametrize("onde", ["replace", "escrita"])
def test_gravar_apaga_tmp_se_falhar(tmp_path, monkeypatch, onde):
    c = _post(tmp_path, POST_CORTE_1)
    antes = c.read_bytes()
    if onde == "replace":
        monkeypatch.setattr("esteira.publicar.post.os.replace", _falhar)
    else:
        monkeypatch.setattr(Path, "write_bytes", _escrever_metade_e_falhar)
    with pytest.raises(OSError, match="disco cheio"):
        gravar_textos(c, Textos("T", "D", "I", "K"), base=tmp_path)
    assert list(tmp_path.glob("*.tmp")) == []
    assert c.read_bytes() == antes


def test_versao_muda_com_conteudo(tmp_path):
    a = _post(tmp_path, POST_CORTE_1)
    va = versao_post(a)
    b = tmp_path / "outro.md"
    b.write_text(POST_CORTE_1 + "x", "utf-8")
    assert va != versao_post(b)
    assert len(va) == 64 and int(va, 16) >= 0
