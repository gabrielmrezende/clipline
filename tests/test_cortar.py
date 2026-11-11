import json

from esteira import cortar
from esteira.cortar import ler_aprovados, pasta_de_trabalho, preparar_episodio
from esteira.midia import ErroMidia
from esteira.modelos import Corte
from esteira.musica import Faixa, atualizar_musica, credito, gravar_catalogo, ler_uso
from esteira.planos import Plano, gravar_planos
from esteira.receita import gravar_receita, ler_receita
from tests.auxiliares import preparar_episodio_teste, preparar_teste

BOM = {"numero": 1, "titulo": "Bom corte", "inicio": 1.0, "fim": 62.9, "clima": "leve"}
RUIM = {"numero": 2, "titulo": "Ruim", "inicio": 1.0, "fim": 10.9, "clima": "tenso"}
SEM_ENQ = "sem enquadramento.json: rode planos"
SO_MUSICA = "ok com alertas: sem música para o clima leve"
SEM_MUSICA = f"ok com alertas: {SEM_ENQ}; sem música para o clima leve"


def test_le_aprovados(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    assert ler_aprovados(pasta) == [Corte(1, "Bom corte", 1.0, 62.9, "leve")]


def test_preparar_gera_receita_sem_video(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    assert preparar_teste(pasta) == {1: SEM_MUSICA}
    corte = pasta / "01-bom-corte"
    for nome in ("montagem.json", "legenda.srt", "edicoes.md", "registro.json"):
        assert (corte / "trabalho" / nome).exists(), nome
    assert not list(corte.glob("*.mp4"))
    receita = ler_receita(corte / "trabalho")
    assert receita.faixas and receita.legenda
    assert json.loads((corte / "trabalho" / "registro.json").read_text("utf-8"))["resultado"] == SEM_MUSICA


def test_preparar_grava_em_trabalho(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_teste(pasta)
    corte = pasta / "01-bom-corte"
    for nome in ("montagem.json", "legenda.srt", "edicoes.md", "registro.json"):
        assert (corte / "trabalho" / nome).exists(), nome
        assert not (corte / nome).exists(), nome
    assert pasta_de_trabalho(corte) == corte / "trabalho"


def test_preparar_nao_sobrescreve_receita(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_teste(pasta)
    corte = pasta / "01-bom-corte"
    receita = ler_receita(corte / "trabalho")
    receita.legenda[0].destaque = "fala"
    gravar_receita(corte / "trabalho", receita)
    assert preparar_teste(pasta)[1] == "erro: montagem.json já existe, use --forcar"
    assert ler_receita(corte / "trabalho").legenda[0].destaque == "fala"
    assert preparar_teste(pasta, forcar=True)[1] == SEM_MUSICA
    assert ler_receita(corte / "trabalho").legenda[0].destaque is None


def test_preparar_usa_enquadramento_gravado(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    corte = pasta / "01-bom-corte"
    (corte / "trabalho").mkdir(parents=True)
    gravar_planos(corte / "trabalho", [Plano(1.0, 62.9, x=0.3, zoom=2)])
    preparar_teste(pasta)
    assert ler_receita(corte / "trabalho").planos == [Plano(1.0, 62.9, x=0.3, zoom=2)]


def test_um_corte_invalido_nao_para_os_outros(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [RUIM, BOM])
    r = preparar_teste(pasta)
    assert r[1] == SEM_MUSICA and r[2].startswith("erro")
    assert (pasta / "02-ruim" / "trabalho" / "registro.json").exists()
    assert not (pasta / "02-ruim" / "trabalho" / "montagem.json").exists()


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
    assert (pasta / "01-bom-corte" / "trabalho" / "registro.json").exists()


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
    receita = pasta / "01-bom-corte" / "trabalho" / "montagem.json"
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
    assert not (pasta / "01-bom-corte" / "trabalho" / "montagem.json").exists()


def _catalogo(pasta_musicas, *titulos):
    gravar_catalogo(pasta_musicas, [Faixa(t, "leve", 200.0, f"leve/{t}.mp3", credito(t)) for t in titulos])


def test_preparar_preenche_musica_e_credito(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM, {**BOM, "numero": 2, "titulo": "Outro"}])
    musicas = tmp_path / "musicas"
    _catalogo(musicas, "Alegre", "Feliz")
    assert preparar_teste(pasta) == {1: f"ok com alertas: {SEM_ENQ}", 2: f"ok com alertas: {SEM_ENQ}"}
    musica = ler_receita(pasta / "01-bom-corte" / "trabalho").musica
    assert musica.arquivo == str(musicas / "leve/Alegre.mp3")
    assert (musica.volume_db, musica.titulo, musica.credito) == (-26.0, "Alegre", credito("Alegre"))
    assert ler_receita(pasta / "02-outro" / "trabalho").musica.titulo == "Feliz"
    uso = ler_uso(musicas)
    assert {k: v["arquivo"] for k, v in uso.items()} == {
        "ep/01-bom-corte": "leve/Alegre.mp3",
        "ep/02-outro": "leve/Feliz.mp3",
    }
    assert preparar_teste(pasta, {1}, forcar=True) == {1: f"ok com alertas: {SEM_ENQ}"}
    assert ler_receita(pasta / "01-bom-corte" / "trabalho").musica.titulo == "Alegre"


def test_preparar_sem_musica_registra_alerta(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    _catalogo(tmp_path / "musicas")
    assert preparar_teste(pasta) == {1: SEM_MUSICA}
    registro = json.loads((pasta / "01-bom-corte" / "trabalho" / "registro.json").read_text("utf-8"))
    assert registro["alertas"] == [SEM_ENQ, "sem música para o clima leve"]
    assert ler_receita(pasta / "01-bom-corte" / "trabalho").musica is None


def test_atualizar_musica_preserva_legenda(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM])
    preparar_teste(pasta)
    corte = pasta / "01-bom-corte"
    receita = ler_receita(corte / "trabalho")
    receita.legenda[0].destaque = "fala"
    gravar_receita(corte / "trabalho", receita)
    musicas = tmp_path / "musicas"
    _catalogo(musicas, "Alegre")
    assert atualizar_musica(corte / "trabalho", ler_aprovados(pasta)[0], "ep/01-bom-corte", musicas) == "Alegre"
    nova = ler_receita(corte / "trabalho")
    assert nova.legenda[0].destaque == "fala"
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
        assert texto.startswith(f"ok com alertas: {SEM_ENQ}; música: erro ")
    assert (pasta / "01-bom-corte" / "trabalho" / "montagem.json").exists()
    assert (pasta / "02-outro" / "trabalho" / "montagem.json").exists()
    assert ler_receita(pasta / "01-bom-corte" / "trabalho").musica is None
    registro = json.loads((pasta / "01-bom-corte" / "trabalho" / "registro.json").read_text("utf-8"))
    assert registro["alertas"][1].startswith("música: erro ")


def test_preparar_sem_enquadramento_alerta(tmp_path):
    pasta, _ = preparar_episodio_teste(tmp_path, [BOM, {**BOM, "numero": 2, "titulo": "Outro"}])
    trabalho = pasta / "02-outro" / "trabalho"
    trabalho.mkdir(parents=True)
    gravar_planos(trabalho, [Plano(1.0, 62.9)])
    r = preparar_teste(pasta)
    assert r[1] == "ok com alertas: sem enquadramento.json: rode planos; sem música para o clima leve"
    assert r[2] == SO_MUSICA
    registro = json.loads((pasta / "01-bom-corte" / "trabalho" / "registro.json").read_text("utf-8"))
    assert "sem enquadramento.json: rode planos" in registro["alertas_preparar"]


def test_preparar_poe_alertas_de_planos_no_tempo_do_corte(tmp_path):
    corte = {**BOM, "inicio": 1.0, "fim": 62.9}
    pasta, _ = preparar_episodio_teste(tmp_path, [corte])
    palavras = json.loads((pasta / "transcricao" / "palavras.json").read_text("utf-8"))
    palavras = [p for p in palavras if not 5 <= p["inicio"] < 15]  # pausa de 4,9 a 15 s
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(palavras), "utf-8")
    trabalho = pasta / "01-bom-corte" / "trabalho"
    trabalho.mkdir(parents=True)
    gravar_planos(trabalho, [Plano(1.0, 62.9)])
    alertas = ["00:02 voz V3 sem pessoa", "00:20 sem rosto", "00:08 fala sobreposta", "sem tempo"]
    (trabalho / "alertas-planos.json").write_text(json.dumps(alertas), "utf-8")
    # O vídeo de teste tem um tom contínuo: a pausa só sai se o áudio estiver em silêncio nela.
    preparar_episodio(pasta, None, False, [], pasta.parent / "musicas", medir_silencio=lambda v, a, b: [(4.9, 15.0)])
    faixas = ler_receita(trabalho).faixas
    assert faixas[0][1] < 5 and faixas[1][0] > 14  # a pausa saiu
    registro = json.loads((trabalho / "registro.json").read_text("utf-8"))
    # 00:20 -> 21 s no episódio; a pausa de ~10 s antes dele saiu do corte.mp4
    # 00:08 -> 9 s, dentro da pausa removida: vai para o próximo instante mantido (3,975 s)
    assert registro["alertas_preparar"][:4] == [
        "00:02 voz V3 sem pessoa", "00:10 sem rosto", "00:03 fala sobreposta", "sem tempo",
    ]


def test_pausa_com_som_no_audio_fica_no_corte(tmp_path):
    """A transcrição perdeu uma fala (riso, "uhum"): o tom do vídeo de teste segue na pausa, então ela fica."""
    corte = {**BOM, "inicio": 1.0, "fim": 62.9}
    pasta, _ = preparar_episodio_teste(tmp_path, [corte])
    palavras = json.loads((pasta / "transcricao" / "palavras.json").read_text("utf-8"))
    palavras = [p for p in palavras if not 5 <= p["inicio"] < 15]
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(palavras), "utf-8")
    preparar_teste(pasta)  # medição real, com ffmpeg: o tom de 440 Hz não é silêncio
    trabalho = pasta / "01-bom-corte" / "trabalho"
    assert len(ler_receita(trabalho).faixas) == 1
    assert "pausa com som mantida" in (trabalho / "edicoes.md").read_text("utf-8")


def test_sem_medir_silencio_avisa_e_corta_pela_transcricao(tmp_path):
    corte = {**BOM, "inicio": 1.0, "fim": 62.9}
    pasta, _ = preparar_episodio_teste(tmp_path, [corte])
    palavras = json.loads((pasta / "transcricao" / "palavras.json").read_text("utf-8"))
    palavras = [p for p in palavras if not 5 <= p["inicio"] < 15]
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(palavras), "utf-8")

    def quebrado(*_):
        raise ErroMidia("sem áudio")

    r = preparar_episodio(pasta, None, False, [], pasta.parent / "musicas", medir_silencio=quebrado)
    assert "não consegui medir o silêncio" in r[1]
    assert len(ler_receita(pasta / "01-bom-corte" / "trabalho").faixas) == 2
