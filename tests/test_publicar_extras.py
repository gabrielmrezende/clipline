"""Tags, playlist e miniatura opcionais no post.md: leitura, conferência, resumo, assinatura e envio.

O post.md sem esses campos tem de continuar valendo e dando o mesmo resumo e a mesma assinatura de sempre."""
import hashlib
import json

import pytest

from esteira.publicar import envio, fila
from esteira.publicar.agendar import confirmar, preparar_pedido, resumo
from esteira.publicar.envio import assinatura
from esteira.publicar.fila import Item, gravar_fila, ler_fila
from esteira.publicar.http import Resultado
from esteira.publicar.post import (
    ExtrasYouTube,
    conferir_extras_youtube,
    gravar_textos,
    interpretar_extras_youtube,
    interpretar_post,
    ler_extras_youtube,
    ler_post,
    tamanho_das_tags,
)
from esteira.publicar.rodar import rodar_episodio
from tests.test_publicar_agendar import AGORA, MODOS, TODAS, episodio  # noqa: F401 (fixture)
from tests.test_publicar_post import POST_CORTE_1

TITULO = "Título: A Fórmula 1 faz sportswashing? 🏎️🌍 #Shorts\n"
EXTRAS = (
    "Tags: política, Fórmula 1, política, sportswashing\n"
    "Playlist: https://www.youtube.com/playlist?list=PLabc_123\n"
    "Miniatura: miniatura.jpg\n"
)
POST_COM_EXTRAS = POST_CORTE_1.replace(TITULO, TITULO + EXTRAS)


@pytest.fixture(autouse=True)
def _sem_restricao(monkeypatch):
    monkeypatch.setattr(fila, "garantir_escrita", lambda caminho: caminho)


class RedeComExtras:
    def __init__(self, resultado):
        self.resultado, self.chamadas = resultado, []

    def publicar(self, video, textos, data, modo, **extras):
        self.chamadas.append(extras)
        return self.resultado


def test_post_antigo_nao_tem_extras(tmp_path):
    assert interpretar_extras_youtube(POST_CORTE_1) == ((), "", "")
    post = tmp_path / "post.md"
    post.write_text(POST_CORTE_1, "utf-8")
    assert not ler_extras_youtube(post)


def test_le_os_campos_antes_da_descricao(tmp_path):
    assert POST_COM_EXTRAS != POST_CORTE_1
    tags, playlist, miniatura = interpretar_extras_youtube(POST_COM_EXTRAS)
    assert tags == ("política", "Fórmula 1", "sportswashing")  # repetida sai
    assert playlist == "PLabc_123"  # o link vira o ID
    assert miniatura == "miniatura.jpg"
    post = tmp_path / "corte" / "post.md"
    post.parent.mkdir()
    post.write_text(POST_COM_EXTRAS, "utf-8")
    assert ler_extras_youtube(post).miniatura == (tmp_path / "corte" / "miniatura.jpg").resolve()


def test_campos_na_descricao_sao_texto_da_descricao():
    texto = POST_CORTE_1.replace("#Fórmula1 #F1", "Tags: isso é descrição\n#Fórmula1 #F1")
    assert interpretar_extras_youtube(texto) == ((), "", "")
    assert "Tags: isso é descrição" in interpretar_post(texto).youtube_descricao


def test_os_textos_nao_mudam_com_os_extras():
    assert interpretar_post(POST_COM_EXTRAS) == interpretar_post(POST_CORTE_1)


def test_editar_pelo_painel_preserva_os_extras(tmp_path):
    post = tmp_path / "post.md"
    post.write_text(POST_COM_EXTRAS, "utf-8")
    textos = ler_post(post)
    textos.youtube_titulo = "Título novo #Shorts"
    gravar_textos(post, textos, base=tmp_path)
    assert ler_post(post).youtube_titulo == "Título novo #Shorts"
    assert EXTRAS in post.read_text("utf-8")


def test_conferir_extras(tmp_path):
    pasta = tmp_path / "corte"
    pasta.mkdir()
    (pasta / "boa.png").write_bytes(b"PNG")
    (tmp_path / "fora.jpg").write_bytes(b"JPG")
    assert conferir_extras_youtube(ExtrasYouTube(("a", "b c"), "PL1", (pasta / "boa.png").resolve()), pasta) == []
    assert tamanho_das_tags(("Foo-Baz", "Foo Baz")) == 7 + 9 + 1  # os exemplos da documentação do YouTube
    problemas = conferir_extras_youtube(ExtrasYouTube(("x" * 501,), "PL 1?", (tmp_path / "fora.jpg").resolve()), pasta)
    assert problemas == [
        "youtube: tags com mais de 500 caracteres",
        "youtube: playlist inválida; use o ID (PL...) ou o link da playlist",
        "youtube: a miniatura precisa estar na pasta do corte",
    ]
    assert conferir_extras_youtube(ExtrasYouTube(miniatura=(pasta / "falta.jpg").resolve()), pasta) == [
        "youtube: miniatura não encontrada: falta.jpg"]
    assert conferir_extras_youtube(ExtrasYouTube(miniatura=(pasta / "x.gif").resolve()), pasta) == [
        "youtube: a miniatura precisa ser .jpg ou .png"]
    assert conferir_extras_youtube(ExtrasYouTube(tags=("<b>",)), pasta) == ["youtube: tag com < ou >"]


def test_agendar_sem_extras_tem_o_resumo_de_sempre(episodio):  # noqa: F811
    pedido = preparar_pedido(episodio[0], 1, "2026-11-08 18:00", TODAS, AGORA)
    assert not pedido.extras
    t = pedido.textos
    cabecalho = "== YouTube (privado: você muda para agendado no Studio)"
    bloco = f"{cabecalho}\nTítulo: {t.youtube_titulo}\n\n{t.youtube_descricao}"
    assert bloco in resumo(pedido, MODOS)


def test_agendar_com_extras_mostra_no_resumo(episodio):  # noqa: F811
    pasta, corte, _ = episodio
    (corte / "post.md").write_text(POST_COM_EXTRAS, "utf-8")
    (corte / "miniatura.jpg").write_bytes(b"JPG")
    pedido = preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)
    assert pedido.extras.tags == ("política", "Fórmula 1", "sportswashing")
    texto = resumo(pedido, MODOS)
    assert "\nTags: política, Fórmula 1, sportswashing\n" in texto
    assert "\nPlaylist: PLabc_123 (o vídeo entra nela depois do envio)\n" in texto
    assert "\nMiniatura: miniatura.jpg (aplicada depois que o YouTube processa o vídeo)\n" in texto


def test_agendar_recusa_miniatura_que_falta_so_quando_vai_para_o_youtube(episodio):  # noqa: F811
    from esteira.publicar.agendar import ErroAgendar

    pasta, corte, _ = episodio
    (corte / "post.md").write_text(POST_COM_EXTRAS, "utf-8")
    with pytest.raises(ErroAgendar, match="youtube: miniatura não encontrada: miniatura.jpg"):
        preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)
    assert not preparar_pedido(pasta, 1, "2026-11-08 18:00", ["instagram"], AGORA).extras


def test_assinatura_sem_extras_e_a_de_sempre(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"VIDEO")
    textos = interpretar_post(POST_CORTE_1)
    antiga = hashlib.sha256(b"VIDEO" + (textos.youtube_titulo + "\n" + textos.youtube_descricao).encode()).hexdigest()
    assert assinatura(video, textos, "youtube") == antiga
    assert assinatura(video, textos, "youtube", ExtrasYouTube()) == antiga
    assert assinatura(video, textos, "youtube", ExtrasYouTube(tags=("a",))) != antiga
    assert assinatura(video, textos, "instagram", ExtrasYouTube(tags=("a",))) == assinatura(video, textos, "instagram")


def test_assinatura_muda_se_a_miniatura_muda(tmp_path):
    video, imagem = tmp_path / "v.mp4", tmp_path / "m.jpg"
    video.write_bytes(b"VIDEO")
    imagem.write_bytes(b"A")
    textos = interpretar_post(POST_CORTE_1)
    antes = assinatura(video, textos, "youtube", ExtrasYouTube(miniatura=imagem))
    imagem.write_bytes(b"B")
    assert assinatura(video, textos, "youtube", ExtrasYouTube(miniatura=imagem)) != antes


def test_confirmar_manda_os_extras_so_ao_youtube_e_guarda_o_aviso(episodio):  # noqa: F811
    pasta, corte, _ = episodio
    (corte / "post.md").write_text(POST_COM_EXTRAS, "utf-8")
    (corte / "miniatura.jpg").write_bytes(b"JPG")
    pedido = preparar_pedido(pasta, 1, "2026-11-08 18:00", TODAS, AGORA)
    rede = RedeComExtras(Resultado("privado", "L", "I", aviso="playlist não aplicada (HTTP 403)"))
    itens = confirmar(pedido, MODOS, {"youtube": rede})
    assert rede.chamadas == [{"extras": pedido.extras}]
    youtube = itens[0]
    assert (youtube.estado, youtube.erro) == ("privado", "playlist não aplicada (HTTP 403)")
    assert youtube.assinatura == assinatura(pedido.video, pedido.textos, "youtube", pedido.extras)


def test_rodar_reenvia_o_youtube_com_os_extras(tmp_path):
    from tests.test_publicar_rodar import DATA, NA_HORA, _episodio

    pasta = _episodio(tmp_path)
    corte = pasta / "01-a-formula-1-faz-sportswashing"
    (corte / "post.md").write_text(POST_COM_EXTRAS, "utf-8")
    (corte / "miniatura.jpg").write_bytes(b"JPG")
    extras = ler_extras_youtube(corte / "post.md")
    marca = assinatura(corte / "video-final" / "Corte 1.mp4", ler_post(corte / "post.md"), "youtube", extras)
    gravar_fila(pasta, [Item(1, "youtube", DATA, tentativas=1, assinatura=marca)])
    rede = RedeComExtras(Resultado("privado", "L", "I"))
    rodar_episodio(pasta, NA_HORA, MODOS, {"youtube": rede})
    assert rede.chamadas == [{"extras": extras}]
    assert ler_fila(pasta)[0].estado == "privado"


def test_rodar_recusa_se_os_extras_mudaram_depois_do_sim(tmp_path):
    from tests.test_publicar_rodar import DATA, NA_HORA, _episodio

    pasta = _episodio(tmp_path)
    corte = pasta / "01-a-formula-1-faz-sportswashing"
    marca = assinatura(corte / "video-final" / "Corte 1.mp4", ler_post(corte / "post.md"), "youtube")
    gravar_fila(pasta, [Item(1, "youtube", DATA, tentativas=1, assinatura=marca)])
    (corte / "post.md").write_text(POST_CORTE_1.replace(TITULO, TITULO + "Tags: nova\n"), "utf-8")
    rede = RedeComExtras(Resultado("privado", "L", "I"))
    rodar_episodio(pasta, NA_HORA, MODOS, {"youtube": rede})
    assert rede.chamadas == [] and ler_fila(pasta)[0].estado == "erro"


def test_enviar_sem_extras_nao_passa_nada_a_mais(tmp_path, monkeypatch):
    monkeypatch.setattr(envio, "gravar_fila", lambda pasta, itens, base=None: None)
    rede = RedeComExtras(Resultado("publicado"))
    item = Item(1, "instagram", "2026-11-08T18:00:00-03:00")
    envio.enviar(tmp_path, [item], item, tmp_path / "v.mp4", interpretar_post(POST_CORTE_1), "", rede,
                 extras_youtube=ExtrasYouTube(tags=("a",)))
    assert rede.chamadas == [{}] and item.erro == ""
    json.dumps(rede.chamadas)  # nada além do que já ia
