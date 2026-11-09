import os
from datetime import datetime

import pytest

from esteira.cortar import VIDEO_FINAL, pasta_do_corte
from esteira.modelos import Corte
from esteira.painel.leitura import (
    CaminhoProibido,
    NaoEncontrado,
    avisos_post,
    bloco_json,
    listar_episodios,
    resolver_arquivo,
    resolver_episodio,
    resumo_episodio,
    selo,
)
from esteira.revisao import BlocoRevisao, dados_revisao
from tests.auxiliares_painel import criar_episodio

NOME = "Entre Assuntos 03 - Arthur Cerqueira (teste capcut)"
OUTRO_CREDITO = "Música: Outra Faixa — Alguém."


def _bloco(**campos) -> BlocoRevisao:
    base = dict(numero=1, titulo="T", pasta="01-t", clima="leve", instagram=False,
                redes=["youtube", "tiktok"], data="")
    base.update(campos)
    return BlocoRevisao(**base)


def test_resolver_episodio_com_acento_e_parenteses(tmp_path):
    (tmp_path / NOME).mkdir()
    assert resolver_episodio(tmp_path, NOME) == (tmp_path / NOME).resolve()


@pytest.mark.parametrize("nome", ["..", "../Automacao", "a/b", "a\\b", "", "C:\\Windows", "/etc"])
def test_resolver_episodio_recusa(tmp_path, nome):
    with pytest.raises(CaminhoProibido):
        resolver_episodio(tmp_path, nome)


def test_resolver_episodio_inexistente(tmp_path):
    with pytest.raises(NaoEncontrado):
        resolver_episodio(tmp_path, "nao existe")


def test_resolver_episodio_link_para_fora(tmp_path):
    cortes = tmp_path / "cortes"
    cortes.mkdir()
    (tmp_path / "fora").mkdir()
    try:
        os.symlink(tmp_path / "fora", cortes / "atalho", target_is_directory=True)
    except OSError:
        pytest.skip("sem permissão para criar link simbólico")
    with pytest.raises(CaminhoProibido):
        resolver_episodio(cortes, "atalho")


def test_resolver_arquivo_extensao(tmp_path):
    (tmp_path / "VIDEO.MOV").write_bytes(b"")
    (tmp_path / "nota.md").write_text("x", "utf-8")
    assert resolver_arquivo(tmp_path, "VIDEO.MOV", {".mp4", ".mov"}) == (tmp_path / "VIDEO.MOV").resolve()
    with pytest.raises(CaminhoProibido):
        resolver_arquivo(tmp_path, "nota.md", {".mp4", ".mov"})
    with pytest.raises(CaminhoProibido):
        resolver_arquivo(tmp_path, "../x.mp4", {".mp4"})
    with pytest.raises(NaoEncontrado):
        resolver_arquivo(tmp_path, "falta.mp4", {".mp4"})


def test_selo_prioridade():
    assert selo(_bloco(erro="x", alertas=["a"], video_final=["v.mp4"]), []) == "erro"
    assert selo(_bloco(alertas=["a"]), []) == "com alerta"
    assert selo(_bloco(video_final=["v.mp4"]), ["post: x"]) == "com alerta"
    assert selo(_bloco(), []) == "sem vídeo final"
    assert selo(_bloco(video_final=["v.mp4"], video_final_desatualizado=True), []) == "vídeo final desatualizado"
    assert selo(_bloco(alertas=["a"], video_final=["v.mp4"], video_final_desatualizado=True), ["post: x"]) == (
        "vídeo final desatualizado"
    )
    assert selo(_bloco(erro="x", video_final=["v.mp4"], video_final_desatualizado=True), []) == "erro"
    assert selo(_bloco(video_final=["v.mp4"]), []) == "pronto"


def _tres_cortes(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso", data="2026-11-06 18:00")
    b = Corte(2, "Dois", 10, 20, "tenso", data="2026-11-09 12:00")
    c = Corte(3, "Tres", 10, 20, "tenso")
    pasta = criar_episodio(tmp_path, "ep", [a, b, c], {1, 2, 3})
    final = pasta_do_corte(pasta, b) / VIDEO_FINAL
    final.mkdir()
    (final / "v.mp4").write_bytes(b"")
    return pasta


def test_resumo_episodio(tmp_path):
    pasta = _tres_cortes(tmp_path)
    r = resumo_episodio(pasta, datetime(2026, 11, 7, 10, 0))
    assert r["nome"] == "ep"
    assert r["total"] == 3
    assert r["prontos"] == 1
    assert r["proxima_data"] == "2026-11-09 12:00"
    assert r["aviso"] is None


def test_resumo_sem_aprovados(tmp_path):
    (tmp_path / "vazio").mkdir()
    r = resumo_episodio(tmp_path / "vazio", datetime(2026, 11, 7))
    assert r["total"] == 0
    assert r["aviso"] == "sem cortes aprovados"
    assert r["proxima_data"] is None


def test_listar_episodios_ordenado(tmp_path):
    (tmp_path / "b").mkdir()
    (tmp_path / "a").mkdir()
    (tmp_path / "arquivo.txt").write_text("x", "utf-8")
    assert [e["nome"] for e in listar_episodios(tmp_path, datetime(2026, 11, 7))] == ["a", "b"]


def test_avisos_post_sem_credito(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = criar_episodio(tmp_path, "ep", [a], {1}, credito=OUTRO_CREDITO)
    avisos = avisos_post(pasta_do_corte(pasta, a), ["youtube", "tiktok"])
    assert "youtube: falta o crédito da música" in avisos


def test_avisos_post_instagram_so_quando_marcado(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = criar_episodio(tmp_path, "ep", [a], {1}, credito=OUTRO_CREDITO)
    avisos = avisos_post(pasta_do_corte(pasta, a), ["youtube", "tiktok"])
    assert avisos and not any(x.startswith("instagram:") for x in avisos)
    com = avisos_post(pasta_do_corte(pasta, a), ["youtube", "tiktok", "instagram"])
    assert any(x.startswith("instagram:") for x in com)


def test_avisos_post_sem_arquivo(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = criar_episodio(tmp_path, "ep", [a], {1}, post=False)
    avisos = avisos_post(pasta_do_corte(pasta, a), ["youtube"])
    assert avisos == ["post: post.md não encontrado"]


def test_bloco_json(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = criar_episodio(tmp_path, "ep", [a], {1})
    bloco = dados_revisao(pasta)[0]
    dados = bloco_json(bloco, ["post: x"])
    assert dados["numero"] == 1 and dados["avisos_post"] == ["post: x"] and dados["selo"] == "com alerta"


def test_avisos_post_ilegivel(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = criar_episodio(tmp_path, "ep", [a], {1})
    (pasta_do_corte(pasta, a) / "post.md").write_bytes(b"\xff\xfe\x80 invalido")
    avisos = avisos_post(pasta_do_corte(pasta, a), ["youtube"])
    assert avisos == ["post: post.md ilegível: não está em UTF-8"]


def test_avisos_post_post_e_pasta(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = criar_episodio(tmp_path, "ep", [a], {1}, post=False)
    (pasta_do_corte(pasta, a) / "post.md").mkdir()
    avisos = avisos_post(pasta_do_corte(pasta, a), ["youtube"])
    assert avisos == ["post: post.md ilegível"]


def test_avisos_post_secao_faltando_sem_caminho(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = criar_episodio(tmp_path, "ep", [a], {1})
    post = pasta_do_corte(pasta, a) / "post.md"
    post.write_text(post.read_text("utf-8").split("## TikTok")[0], "utf-8")
    assert avisos_post(pasta_do_corte(pasta, a), ["youtube"]) == ["post: post.md sem a seção ## TikTok"]


def _com_video_final(tmp_path, corte_mp4_em, final_em):
    b = Corte(2, "Dois", 10, 20, "tenso")
    pasta = criar_episodio(tmp_path, "ep", [b], {2})
    destino = pasta_do_corte(pasta, b)
    final = destino / VIDEO_FINAL
    final.mkdir()
    velho, novo = final / "a.mp4", final / "b.mov"
    velho.write_bytes(b"")
    novo.write_bytes(b"")
    (final / "nota.txt").write_text("x", "utf-8")
    os.utime(velho, (final_em - 500, final_em - 500))
    os.utime(novo, (final_em, final_em))
    os.utime(final / "nota.txt", (final_em + 9000, final_em + 9000))  # outras extensões não contam
    os.utime(destino / "corte.mp4", (corte_mp4_em, corte_mp4_em))
    return pasta


def test_selo_video_final_desatualizado(tmp_path):
    pasta = _com_video_final(tmp_path, corte_mp4_em=2_000_000_000, final_em=1_900_000_000)
    [bloco] = dados_revisao(pasta)
    assert bloco.video_final_desatualizado is True
    assert bloco_json(bloco, [])["selo"] == "vídeo final desatualizado"
    assert bloco_json(bloco, [])["video_final_desatualizado"] is True


def test_selo_video_final_em_dia(tmp_path):
    pasta = _com_video_final(tmp_path, corte_mp4_em=1_900_000_000, final_em=2_000_000_000)
    [bloco] = dados_revisao(pasta)
    assert bloco.video_final_desatualizado is False
    assert bloco_json(bloco, [])["selo"] == "pronto"


def test_revisao_md_nao_muda_com_o_selo_novo(tmp_path):
    from esteira.revisao import escrever_revisao

    pasta = _com_video_final(tmp_path, corte_mp4_em=2_000_000_000, final_em=1_900_000_000)
    texto = escrever_revisao(pasta).read_text("utf-8")
    assert "desatualizado" not in texto
