import json

from esteira import cortar
from esteira.cortar import atualizar_imagens, ler_aprovados, preparar_episodio
from esteira.modelos import Corte
from esteira.planos import Plano, gravar_planos
from esteira.receita import gravar_receita, ler_receita
from tests.auxiliares import preparar_episodio_teste

BOM = {"numero": 1, "titulo": "Bom corte", "inicio": 1.0, "fim": 62.9, "clima": "leve"}
RUIM = {"numero": 2, "titulo": "Ruim", "inicio": 1.0, "fim": 10.9, "clima": "tenso"}


def _escrever_imagem(corte):
    (corte / "imagens").mkdir(parents=True, exist_ok=True)
    (corte / "imagens" / "01-gripen.jpg").write_bytes(b"x")
    (corte / "imagens.md").write_text("## 1. 00:00:05 a 00:00:08 — Gripen\n", "utf-8")


def test_le_aprovados(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    assert ler_aprovados(pasta) == [Corte(1, "Bom corte", 1.0, 62.9, "leve")]


def test_preparar_gera_receita_sem_video(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    assert preparar_episodio(pasta, nomes=[]) == {1: "ok"}
    corte = pasta / "01-bom-corte"
    for nome in ("montagem.json", "legenda.srt", "edicoes.md", "registro.json"):
        assert (corte / nome).exists(), nome
    assert (corte / "imagens").is_dir()
    assert not list(corte.glob("*.mp4"))
    receita = ler_receita(corte)
    assert receita.faixas and receita.legenda and receita.imagens == []
    assert json.loads((corte / "registro.json").read_text("utf-8"))["resultado"] == "ok"


def test_preparar_nao_sobrescreve_receita(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_episodio(pasta, nomes=[])
    corte = pasta / "01-bom-corte"
    receita = ler_receita(corte)
    receita.legenda[0].destaque = "fala"
    gravar_receita(corte, receita)
    assert preparar_episodio(pasta, nomes=[])[1] == "erro: montagem.json já existe, use --forcar"
    assert ler_receita(corte).legenda[0].destaque == "fala"
    assert preparar_episodio(pasta, nomes=[], forcar=True)[1] == "ok"
    assert ler_receita(corte).legenda[0].destaque is None


def test_preparar_usa_enquadramento_gravado(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    corte = pasta / "01-bom-corte"
    corte.mkdir()
    gravar_planos(corte, [Plano(1.0, 62.9, x=0.3, zoom=2)])
    preparar_episodio(pasta, nomes=[])
    assert ler_receita(corte).planos == [Plano(1.0, 62.9, x=0.3, zoom=2)]


def test_preparar_inclui_imagens_aprovadas(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    corte = pasta / "01-bom-corte"
    _escrever_imagem(corte)
    preparar_episodio(pasta, nomes=[])
    assert [i.arquivo for i in ler_receita(corte).imagens] == ["imagens/01-gripen.jpg"]


def test_atualizar_imagens_preserva_destaques(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_episodio(pasta, nomes=[])
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
    r = preparar_episodio(pasta, nomes=[])
    assert r[1] == "ok" and r[2].startswith("erro")
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
    r = preparar_episodio(pasta, nomes=[])
    assert r[1].startswith("erro") and r[2] == "ok"
    assert (pasta / "01-bom-corte" / "registro.json").exists()


def test_encerramento_alterna_entre_os_quatro_videos():
    escolhidos = [cortar.escolher_encerramento(n).name for n in range(1, 6)]
    assert len(set(escolhidos[:4])) == 4
    assert escolhidos[4] == escolhidos[0]
    assert all(n.startswith("Final Corte") for n in escolhidos)


def test_filtra_por_numero(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [RUIM, BOM])
    assert list(preparar_episodio(pasta, {1}, nomes=[])) == [1]


def test_forcar_com_trecho_invalido_apaga_a_receita_antiga(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_episodio(pasta, nomes=[])
    receita = pasta / "01-bom-corte" / "montagem.json"
    assert receita.exists()
    json.dump({"cortes": [{**BOM, "fim": 10.9}]}, (pasta / "aprovados.json").open("w", encoding="utf-8"))
    assert preparar_episodio(pasta, forcar=True, nomes=[])[1].startswith("erro")
    assert not receita.exists()


def test_forcar_com_erro_de_sistema_apaga_a_receita_antiga(tmp_path, monkeypatch):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_episodio(pasta, nomes=[])

    def falhar(cues, caminho):
        raise PermissionError("arquivo aberto")

    monkeypatch.setattr(cortar, "escrever_srt", falhar)
    assert preparar_episodio(pasta, forcar=True, nomes=[])[1].startswith("erro")
    assert not (pasta / "01-bom-corte" / "montagem.json").exists()


def test_imagens_md_fora_de_utf8_nao_para_os_outros(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM, {**BOM, "numero": 2, "titulo": "Outro"}])
    corte = pasta / "01-bom-corte"
    (corte / "imagens").mkdir(parents=True)
    (corte / "imagens.md").write_bytes("## 1. 00:00:05 a 00:00:08 - Avião\n".encode("latin-1"))
    r = preparar_episodio(pasta, nomes=[])
    assert r[1].startswith("erro") and r[2] == "ok"
