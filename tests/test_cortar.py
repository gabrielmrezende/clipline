import json

from esteira import cortar
from esteira.cortar import atualizar_imagens, ler_aprovados
from esteira.modelos import Corte
from esteira.musica import Faixa, atualizar_musica, credito, gravar_catalogo, ler_uso
from esteira.planos import Plano, gravar_planos
from esteira.receita import gravar_receita, ler_receita
from tests.auxiliares import preparar_episodio_teste, preparar_teste

BOM = {"numero": 1, "titulo": "Bom corte", "inicio": 1.0, "fim": 62.9, "clima": "leve"}
RUIM = {"numero": 2, "titulo": "Ruim", "inicio": 1.0, "fim": 10.9, "clima": "tenso"}
SEM_MUSICA = "ok com alertas: sem música para o clima leve"


def _escrever_imagem(corte):
    (corte / "imagens").mkdir(parents=True, exist_ok=True)
    (corte / "imagens" / "01-gripen.jpg").write_bytes(b"x")
    (corte / "imagens.md").write_text("## 1. 00:00:05 a 00:00:08 — Gripen\n", "utf-8")


def test_le_aprovados(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    assert ler_aprovados(pasta) == [Corte(1, "Bom corte", 1.0, 62.9, "leve")]


def test_preparar_gera_receita_sem_video(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    assert preparar_teste(pasta) == {1: SEM_MUSICA}
    corte = pasta / "01-bom-corte"
    for nome in ("montagem.json", "legenda.srt", "edicoes.md", "registro.json"):
        assert (corte / nome).exists(), nome
    assert (corte / "imagens").is_dir()
    assert not list(corte.glob("*.mp4"))
    receita = ler_receita(corte)
    assert receita.faixas and receita.legenda and receita.imagens == []
    assert json.loads((corte / "registro.json").read_text("utf-8"))["resultado"] == SEM_MUSICA


def test_preparar_nao_sobrescreve_receita(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_teste(pasta)
    corte = pasta / "01-bom-corte"
    receita = ler_receita(corte)
    receita.legenda[0].destaque = "fala"
    gravar_receita(corte, receita)
    assert preparar_teste(pasta)[1] == "erro: montagem.json já existe, use --forcar"
    assert ler_receita(corte).legenda[0].destaque == "fala"
    assert preparar_teste(pasta, forcar=True)[1] == SEM_MUSICA
    assert ler_receita(corte).legenda[0].destaque is None


def test_preparar_usa_enquadramento_gravado(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    corte = pasta / "01-bom-corte"
    corte.mkdir()
    gravar_planos(corte, [Plano(1.0, 62.9, x=0.3, zoom=2)])
    preparar_teste(pasta)
    assert ler_receita(corte).planos == [Plano(1.0, 62.9, x=0.3, zoom=2)]


def test_preparar_inclui_imagens_aprovadas(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    corte = pasta / "01-bom-corte"
    _escrever_imagem(corte)
    preparar_teste(pasta)
    assert [i.arquivo for i in ler_receita(corte).imagens] == ["imagens/01-gripen.jpg"]


def test_atualizar_imagens_preserva_destaques(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_teste(pasta)
    corte = pasta / "01-bom-corte"
    receita = ler_receita(corte)
    receita.legenda[0].destaque = "fala"
    gravar_receita(corte, receita)
    _escrever_imagem(corte)
    assert atualizar_imagens(corte) == 1
    nova = ler_receita(corte)
    assert [i.arquivo for i in nova.imagens] == ["imagens/01-gripen.jpg"]
    assert nova.legenda[0].destaque == "fala"


def test_um_corte_invalido_nao_para_os_outros(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [RUIM, BOM])
    r = preparar_teste(pasta)
    assert r[1] == SEM_MUSICA and r[2].startswith("erro")
    assert (pasta / "02-ruim" / "registro.json").exists()
    assert not (pasta / "02-ruim" / "montagem.json").exists()


def test_erro_de_sistema_nao_para_os_outros(tmp_path, monkeypatch):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM, {**BOM, "numero": 2, "titulo": "Outro"}])
    original = cortar.escrever_srt

    def falhar_no_primeiro(cues, caminho):
        if "01-" in str(caminho):
            raise PermissionError("arquivo aberto")
        original(cues, caminho)

    monkeypatch.setattr(cortar, "escrever_srt", falhar_no_primeiro)
    r = preparar_teste(pasta)
    assert r[1].startswith("erro") and r[2] == SEM_MUSICA
    assert (pasta / "01-bom-corte" / "registro.json").exists()


def test_encerramento_alterna_entre_os_quatro_videos():
    escolhidos = [cortar.escolher_encerramento(n).name for n in range(1, 6)]
    assert len(set(escolhidos[:4])) == 4
    assert escolhidos[4] == escolhidos[0]
    assert all(n.startswith("Final Corte") for n in escolhidos)


def test_filtra_por_numero(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [RUIM, BOM])
    assert list(preparar_teste(pasta, {1})) == [1]


def test_forcar_com_trecho_invalido_apaga_a_receita_antiga(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_teste(pasta)
    receita = pasta / "01-bom-corte" / "montagem.json"
    assert receita.exists()
    json.dump({"cortes": [{**BOM, "fim": 10.9}]}, (pasta / "aprovados.json").open("w", encoding="utf-8"))
    assert preparar_teste(pasta, forcar=True)[1].startswith("erro")
    assert not receita.exists()


def test_forcar_com_erro_de_sistema_apaga_a_receita_antiga(tmp_path, monkeypatch):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_teste(pasta)

    def falhar(cues, caminho):
        raise PermissionError("arquivo aberto")

    monkeypatch.setattr(cortar, "escrever_srt", falhar)
    assert preparar_teste(pasta, forcar=True)[1].startswith("erro")
    assert not (pasta / "01-bom-corte" / "montagem.json").exists()


def test_imagens_md_fora_de_utf8_nao_para_os_outros(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM, {**BOM, "numero": 2, "titulo": "Outro"}])
    corte = pasta / "01-bom-corte"
    (corte / "imagens").mkdir(parents=True)
    (corte / "imagens.md").write_bytes("## 1. 00:00:05 a 00:00:08 - Avião\n".encode("latin-1"))
    r = preparar_teste(pasta)
    assert r[1].startswith("erro") and r[2] == SEM_MUSICA


def _catalogo(pasta_musicas, *titulos):
    gravar_catalogo(pasta_musicas, [Faixa(t, "leve", 200.0, f"leve/{t}.mp3", credito(t)) for t in titulos])


def test_preparar_preenche_musica_e_credito(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM, {**BOM, "numero": 2, "titulo": "Outro"}])
    musicas = tmp_path / "musicas"
    _catalogo(musicas, "Alegre", "Feliz")
    assert preparar_teste(pasta) == {1: "ok", 2: "ok"}
    musica = ler_receita(pasta / "01-bom-corte").musica
    assert musica.arquivo == str(musicas / "leve/Alegre.mp3")
    assert (musica.volume_db, musica.titulo, musica.credito) == (-20.0, "Alegre", credito("Alegre"))
    assert ler_receita(pasta / "02-outro").musica.titulo == "Feliz"
    uso = ler_uso(musicas)
    assert {k: v["arquivo"] for k, v in uso.items()} == {
        "ep/01-bom-corte": "leve/Alegre.mp3",
        "ep/02-outro": "leve/Feliz.mp3",
    }
    assert preparar_teste(pasta, {1}, forcar=True) == {1: "ok"}
    assert ler_receita(pasta / "01-bom-corte").musica.titulo == "Alegre"


def test_preparar_sem_musica_registra_alerta(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    _catalogo(tmp_path / "musicas")
    assert preparar_teste(pasta) == {1: SEM_MUSICA}
    registro = json.loads((pasta / "01-bom-corte" / "registro.json").read_text("utf-8"))
    assert registro["alertas"] == ["sem música para o clima leve"]
    assert ler_receita(pasta / "01-bom-corte").musica is None


def test_atualizar_musica_preserva_legenda(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_teste(pasta)
    corte = pasta / "01-bom-corte"
    _escrever_imagem(corte)
    atualizar_imagens(corte)
    receita = ler_receita(corte)
    receita.legenda[0].destaque = "fala"
    gravar_receita(corte, receita)
    musicas = tmp_path / "musicas"
    _catalogo(musicas, "Alegre")
    assert atualizar_musica(corte, ler_aprovados(pasta)[0], "ep/01-bom-corte", musicas) == "Alegre"
    nova = ler_receita(corte)
    assert nova.legenda[0].destaque == "fala" and len(nova.imagens) == 1
    assert nova.musica.titulo == "Alegre"
    assert ler_uso(musicas)["ep/01-bom-corte"]["arquivo"] == "leve/Alegre.mp3"


def test_preparar_falha_da_musica_vira_alerta_e_nao_para_os_outros(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM, {**BOM, "numero": 2, "titulo": "Outro"}])
    musicas = tmp_path / "musicas"
    _catalogo(musicas, "Alegre", "Feliz")
    (musicas / "uso.json").write_text('{"ep/x": {"arquivo": "leve/Alegre.mp3"}}', "utf-8")
    resultado = preparar_teste(pasta)
    assert set(resultado) == {1, 2}
    for texto in resultado.values():
        assert texto.startswith("ok com alertas: música: erro ")
    assert (pasta / "01-bom-corte" / "montagem.json").exists()
    assert (pasta / "02-outro" / "montagem.json").exists()
    assert ler_receita(pasta / "01-bom-corte").musica is None
    registro = json.loads((pasta / "01-bom-corte" / "registro.json").read_text("utf-8"))
    assert registro["alertas"][0].startswith("música: erro ")
