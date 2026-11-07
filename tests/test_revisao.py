import json
from pathlib import Path

from esteira.cortar import pasta_do_corte
from esteira.modelos import Corte, Palavra
from esteira.receita import Musica, Receita, gravar_receita
from esteira.revisao import contexto_do_trecho, dados_revisao, escrever_revisao, ler_nomes_suspeitos

PALAVRAS = [{"texto": f"p{i}", "inicio": i - 0.4, "fim": i + 0.4} for i in range(30)]


def _episodio(tmp_path: Path, cortes: list[Corte]) -> Path:
    pasta = tmp_path / "ep"
    (pasta / "transcricao").mkdir(parents=True)
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(PALAVRAS), "utf-8")
    (pasta / "aprovados.json").write_text(json.dumps({"cortes": [c.__dict__ for c in cortes]}), "utf-8")
    return pasta


def _montado(pasta: Path, corte: Corte, resultado="ok", alertas=None, musica=None) -> None:
    destino = pasta_do_corte(pasta, corte)
    (destino / "trabalho").mkdir(parents=True)
    (destino / "corte.mp4").write_bytes(b"")
    receita = Receita([(corte.inicio, corte.fim)], [], [], musica=musica)
    gravar_receita(destino / "trabalho", receita)
    registro = {"resultado": resultado, "alertas": alertas or []}
    (destino / "trabalho" / "registro.json").write_text(json.dumps(registro), "utf-8")


def test_contexto_do_trecho():
    palavras = [Palavra(**p) for p in PALAVRAS]
    assert contexto_do_trecho(palavras, 10, 20, n=3) == ("p7 p8 p9", "p21 p22 p23")


def test_contexto_do_trecho_no_comeco_e_no_fim():
    palavras = [Palavra(**p) for p in PALAVRAS]
    assert contexto_do_trecho(palavras, 0, 29, n=3) == ("", "")


def test_revisao_tem_bloco_por_corte(tmp_path):
    a = Corte(1, "Primeiro Corte", 10, 20, "tenso", instagram=True, data="2026-11-04 18:00")
    b = Corte(2, "Segundo", 12, 18, "leve")
    pasta = _episodio(tmp_path, [a, b])
    _montado(pasta, a, musica=Musica("m.mp3"))
    _montado(pasta, b, musica=Musica("m.mp3"))

    caminho = escrever_revisao(pasta)
    texto = caminho.read_text("utf-8")

    assert caminho == pasta / "revisao.md"
    assert "## 1. Primeiro Corte" in texto
    assert "## 2. Segundo" in texto
    assert "Vídeo: [corte.mp4](01-primeiro-corte/corte.mp4)" in texto
    assert "Redes: YouTube, TikTok e Instagram" in texto
    assert "Redes: YouTube e TikTok\n" in texto
    assert "Publicação sugerida: 2026-11-04 18:00" in texto
    assert "Publicação sugerida: sem data" in texto
    assert 'Antes: "... p0 p1 p2 p3 p4 p5 p6 p7 p8 p9"' in texto
    assert 'Depois: "p21 p22 p23 p24 p25 p26 p27 p28 p29 ..."' in texto
    assert "Alertas: nenhum" in texto
    assert texto.rstrip().endswith("Candidatos descartados: ver [candidatos.md](candidatos.md).")


def test_revisao_mostra_alertas_e_erros(tmp_path):
    a = Corte(1, "Com Alertas", 10, 20, "tenso")
    b = Corte(2, "Quebrado", 10, 20, "tenso")
    c = Corte(3, "Sem Registro", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a, b, c])
    _montado(pasta, a, "ok com alertas: sem música", ["sem música"])
    _montado(pasta, b, "erro: imagem 1 não encontrada")
    (pasta_do_corte(pasta, b) / "corte.mp4").unlink()
    pasta_do_corte(pasta, c).mkdir()

    texto = escrever_revisao(pasta).read_text("utf-8")
    blocos = texto.split("## ")

    assert "Alertas: sem música" in blocos[1]
    assert blocos[1].split("Alertas:")[1].count("sem música") == 1
    assert "Erro: imagem 1 não encontrada" in blocos[2]
    assert "Vídeo:" not in blocos[2]
    assert "Erro: corte não montado" in blocos[3]


def test_revisao_e_sobrescrita(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a])
    _montado(pasta, a)
    (pasta / "revisao.md").write_text("velho", "utf-8")
    assert "velho" not in escrever_revisao(pasta).read_text("utf-8")


def test_revisao_com_json_ilegivel_afeta_so_o_proprio_corte(tmp_path):
    a = Corte(1, "Registro Ruim", 10, 20, "tenso")
    b = Corte(2, "Montagem Ruim", 10, 20, "tenso")
    c = Corte(3, "Bom", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a, b, c])
    for corte in (a, b, c):
        _montado(pasta, corte)
    (pasta_do_corte(pasta, a) / "trabalho" / "registro.json").write_text("{quebrado", "utf-8")
    (pasta_do_corte(pasta, b) / "trabalho" / "montagem.json").write_text("{quebrado", "utf-8")

    blocos = escrever_revisao(pasta).read_text("utf-8").split("## ")

    assert "Erro: registro ilegível" in blocos[1] and "Vídeo:" not in blocos[1]
    assert "Erro: montagem ilegível" in blocos[2] and "Vídeo:" not in blocos[2]
    assert "Alertas: nenhum" in blocos[3] and "ilegível" not in blocos[3]


def test_revisao_mostra_musica(tmp_path):
    a = Corte(1, "Com Música", 10, 20, "tenso", data="2026-11-04 18:00")
    b = Corte(2, "Sem Música", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a, b])
    _montado(pasta, a, musica=Musica("m.mp3", titulo="Carefree"))
    _montado(pasta, b)

    blocos = escrever_revisao(pasta).read_text("utf-8").split("## ")

    assert "Publicação sugerida: 2026-11-04 18:00\nMúsica: Carefree\n" in blocos[1]
    assert "Publicação sugerida: sem data\nMúsica: nenhuma (sem música para o clima tenso)\n" in blocos[2]


def test_revisao_mostra_corte_e_guia(tmp_path):
    a = Corte(1, "Com Guia", 10, 20, "tenso")
    b = Corte(2, "Sem Guia", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a, b])
    _montado(pasta, a)
    _montado(pasta, b)
    guia = pasta_do_corte(pasta, a) / "imagens-sugeridas" / "guia.md"
    guia.parent.mkdir()
    guia.write_text("# guia", "utf-8")

    blocos = escrever_revisao(pasta).read_text("utf-8").split("## ")

    assert "Vídeo: [corte.mp4](01-com-guia/corte.mp4)" in blocos[1]
    assert "Guia de imagens: [guia.md](01-com-guia/imagens-sugeridas/guia.md)" in blocos[1]
    assert "Guia de imagens: não gerado" in blocos[2]


def test_revisao_video_final_vazio_e_preenchido(tmp_path):
    a = Corte(1, "Vazio", 10, 20, "tenso")
    b = Corte(2, "Um", 10, 20, "tenso")
    c = Corte(3, "Varios", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a, b, c])
    for corte in (a, b, c):
        _montado(pasta, corte)
    (pasta_do_corte(pasta, b) / "video-final").mkdir()
    (pasta_do_corte(pasta, b) / "video-final" / "Editado.MP4").write_bytes(b"x")
    (pasta_do_corte(pasta, b) / "video-final" / "nota.txt").write_text("x", "utf-8")
    pasta_c = pasta_do_corte(pasta, c) / "video-final"
    pasta_c.mkdir()
    (pasta_c / "b.mov").write_bytes(b"x")
    (pasta_c / "a.mp4").write_bytes(b"x")

    blocos = escrever_revisao(pasta).read_text("utf-8").split("## ")

    assert "Vídeo final: vazio" in blocos[1]
    assert not (pasta_do_corte(pasta, a) / "video-final").exists()
    assert "Vídeo final: Editado.MP4\n" in blocos[2]
    assert "Vídeo final: a.mp4, b.mov\n" in blocos[3]
    assert blocos[3].index("Vídeo final:") < blocos[3].index("Alertas:")


def test_revisao_corte_nao_montado(tmp_path):
    a = Corte(1, "Sem Corte", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a])
    destino = pasta_do_corte(pasta, a)
    (destino / "trabalho").mkdir(parents=True)
    (destino / "trabalho" / "registro.json").write_text(json.dumps({"resultado": "ok"}), "utf-8")

    texto = escrever_revisao(pasta).read_text("utf-8")

    assert "Erro: corte não montado" in texto


def test_dados_revisao_campos(tmp_path):
    a = Corte(1, "Primeiro Corte", 10, 20, "tenso", instagram=True, data="2026-11-04 18:00")
    pasta = _episodio(tmp_path, [a])
    _montado(pasta, a, musica=Musica("m.mp3", titulo="Ice Flow"))

    (bloco,) = dados_revisao(pasta)

    assert bloco.numero == 1
    assert bloco.titulo == "Primeiro Corte"
    assert bloco.pasta == "01-primeiro-corte"
    assert bloco.redes == ["youtube", "tiktok", "instagram"]
    assert bloco.musica == "Ice Flow"
    assert bloco.antes == "p0 p1 p2 p3 p4 p5 p6 p7 p8 p9"
    assert bloco.video_final == []
    assert bloco.tem_guia is False
    assert bloco.erro is None


def test_dados_revisao_nao_montado(tmp_path):
    a = Corte(1, "Sem Corte", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a])

    (bloco,) = dados_revisao(pasta)

    assert bloco.erro == "corte não montado"


def test_dados_revisao_video_final_ordenado(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a])
    _montado(pasta, a)
    final = pasta_do_corte(pasta, a) / "video-final"
    final.mkdir()
    (final / "b.MOV").write_bytes(b"x")
    (final / "A.mp4").write_bytes(b"x")

    (bloco,) = dados_revisao(pasta)

    assert bloco.video_final == ["A.mp4", "b.MOV"]


def test_nomes_suspeitos_entram_nos_alertas(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a])
    _montado(pasta, a, alertas=["fora de quadro"])
    (pasta / "nomes-suspeitos.json").write_text(
        json.dumps({"1": ["Massa: conferir 'Felipe Massa'"]}), "utf-8"
    )

    (bloco,) = dados_revisao(pasta)
    texto = escrever_revisao(pasta).read_text("utf-8")

    assert bloco.alertas == ["fora de quadro", "Massa: conferir 'Felipe Massa'"]
    assert "Alertas: fora de quadro; Massa: conferir 'Felipe Massa'" in texto


def test_nomes_suspeitos_ilegivel(tmp_path):
    a = Corte(1, "Um", 10, 20, "tenso")
    b = Corte(2, "Dois", 10, 20, "tenso")
    pasta = _episodio(tmp_path, [a, b])
    _montado(pasta, a)
    _montado(pasta, b)
    (pasta / "nomes-suspeitos.json").write_text("{quebrado", "utf-8")

    blocos = dados_revisao(pasta)

    assert len(blocos) == 2
    assert all("nomes-suspeitos.json ilegível" in b.alertas for b in blocos)


def test_nomes_suspeitos_ausente(tmp_path):
    pasta = _episodio(tmp_path, [])
    assert ler_nomes_suspeitos(pasta) == ({}, None)
