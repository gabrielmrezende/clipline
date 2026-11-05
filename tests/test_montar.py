import json
from pathlib import Path

from esteira import montar
from esteira.midia import ErroMidia, sondar
from esteira.montar import montar_episodio
from esteira.receita import NOME_ARQUIVO, Musica, gravar_receita, ler_receita
from tests.auxiliares import preparar_episodio_teste, preparar_teste

BOM = {"numero": 1, "titulo": "Bom corte", "inicio": 1.0, "fim": 62.9, "clima": "leve"}
OUTRO = {**BOM, "numero": 2, "titulo": "Outro"}


def _preparado(tmp_path, cortes=(BOM,)):
    pasta, cartao = preparar_episodio_teste(tmp_path, list(cortes))
    preparar_teste(pasta)
    return pasta, cartao


def test_montar_gera_corte_mp4(tmp_path):
    pasta, cartao = _preparado(tmp_path)
    uniao = "sem música para o clima leve; sem música"
    assert montar_episodio(pasta, cartao=cartao) == {1: f"ok com alertas: {uniao}"}
    corte = pasta / "01-bom-corte"
    assert sondar(corte / "corte.mp4").duracao > 62
    assert not (corte / "final.mp4").exists()
    assert (corte / "imagens-sugeridas").is_dir() and (corte / "video-final").is_dir()
    registro = json.loads((corte / "trabalho" / "registro.json").read_text("utf-8"))
    assert registro["resultado"] == f"ok com alertas: {uniao}"
    assert registro["alertas"] == ["sem música para o clima leve", "sem música"]
    assert registro["faixas"] and registro["corte"]["numero"] == 1


def test_receita_invalida_nao_para_os_outros(tmp_path):
    pasta, cartao = _preparado(tmp_path, [BOM, OUTRO])
    corte = pasta / "01-bom-corte"
    receita = ler_receita(corte / "trabalho")
    receita.musica = Musica(str(tmp_path / "nao-existe.mp3"), -20.0)
    gravar_receita(corte / "trabalho", receita)
    r = montar_episodio(pasta, cartao=cartao)
    assert r[1].startswith("erro: ") and "não encontrada" in r[1]
    assert r[2].startswith("ok")
    assert not (corte / "corte.mp4").exists()
    assert json.loads((corte / "trabalho" / "registro.json").read_text("utf-8"))["resultado"] == r[1]


def test_corte_sem_receita(tmp_path):
    pasta, cartao = preparar_episodio_teste(tmp_path, [BOM])
    assert montar_episodio(pasta, cartao=cartao) == {1: "erro: montagem.json não encontrado, rode preparar"}


def test_montar_nao_sobrescreve_corte_sem_forcar(tmp_path):
    pasta, cartao = _preparado(tmp_path)
    montar_episodio(pasta, cartao=cartao)
    assert montar_episodio(pasta, cartao=cartao)[1] == "erro: corte.mp4 já existe, use --forcar"
    assert montar_episodio(pasta, forcar=True, cartao=cartao)[1].startswith("ok")


def test_montar_forcar_preserva_video_final(tmp_path):
    pasta, cartao = _preparado(tmp_path)
    montar_episodio(pasta, cartao=cartao)
    meu = pasta / "01-bom-corte" / "video-final" / "meu.mp4"
    meu.write_bytes(b"meu video editado 123")
    assert montar_episodio(pasta, forcar=True, cartao=cartao)[1].startswith("ok")
    assert meu.read_bytes() == b"meu video editado 123"


def test_forcar_com_falha_nao_deixa_corte_antigo(tmp_path, monkeypatch):
    pasta, cartao = _preparado(tmp_path)
    montar_episodio(pasta, cartao=cartao)

    def falhar(*args, **kwargs):
        raise ErroMidia("falhou")

    monkeypatch.setattr(montar, "renderizar_final", falhar)
    assert montar_episodio(pasta, forcar=True, cartao=cartao)[1] == "erro: falhou"
    assert not (pasta / "01-bom-corte" / "corte.mp4").exists()


def test_erro_de_sistema_nao_para_os_outros(tmp_path, monkeypatch):
    pasta, cartao = _preparado(tmp_path, [BOM, OUTRO])
    original = montar.renderizar_final

    def falhar_no_primeiro(receita, video, cartao, pasta_corte, saida, sobreposicao=None):
        if "01-" in str(saida):
            raise PermissionError("arquivo aberto")
        return original(receita, video, cartao, pasta_corte, saida, sobreposicao)

    monkeypatch.setattr(montar, "renderizar_final", falhar_no_primeiro)
    r = montar_episodio(pasta, cartao=cartao)
    assert r[1].startswith("erro") and r[2].startswith("ok")


def test_filtra_por_numero(tmp_path):
    pasta, cartao = _preparado(tmp_path, [BOM, OUTRO])
    assert list(montar_episodio(pasta, {2}, cartao=cartao)) == [2]


def test_corte_travado_com_forcar_nao_derruba_os_outros(tmp_path, monkeypatch):
    pasta, cartao = _preparado(tmp_path, [BOM, OUTRO])
    for nome in ("01-bom-corte", "02-outro"):
        (pasta / nome / "corte.mp4").write_bytes(b"")
    unlink = Path.unlink

    def travar(self, *args, **kwargs):
        if self.name == "corte.mp4" and "01-" in str(self):
            raise PermissionError("em uso por outro processo")
        return unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", travar)
    monkeypatch.setattr(montar, "renderizar_final", lambda *args, **kwargs: [])
    r = montar_episodio(pasta, forcar=True, cartao=cartao)
    assert r[1].startswith("erro: ") and "em uso" in r[1]
    assert r[2].startswith("ok")
    registro = json.loads((pasta / "01-bom-corte" / "trabalho" / "registro.json").read_text("utf-8"))
    assert registro["resultado"] == r[1]


def test_ler_receita_ignora_imagens_antigas(tmp_path):
    pasta, cartao = _preparado(tmp_path)
    trabalho = pasta / "01-bom-corte" / "trabalho"
    dados = json.loads((trabalho / NOME_ARQUIVO).read_text("utf-8"))
    dados["imagens"] = [{"inicio": 1.0, "fim": 3.0, "arquivo": "imagens/a.jpg", "licenca": ""}]
    (trabalho / NOME_ARQUIVO).write_text(json.dumps(dados), "utf-8")
    assert ler_receita(trabalho).faixas


def _gravar_alerta_do_preparar(corte: Path) -> None:
    arquivo = corte / "trabalho" / "registro.json"
    registro = json.loads(arquivo.read_text("utf-8")) if arquivo.exists() else {}
    registro["alertas"] = ["00:05 voz V3 sem pessoa"]
    arquivo.write_text(json.dumps(registro), "utf-8")


def test_montar_preserva_alertas_do_preparar(tmp_path):
    pasta, cartao = _preparado(tmp_path)
    corte = pasta / "01-bom-corte"
    _gravar_alerta_do_preparar(corte)
    resultado = montar_episodio(pasta, cartao=cartao)[1]
    registro = json.loads((corte / "trabalho" / "registro.json").read_text("utf-8"))
    assert registro["alertas"] == ["00:05 voz V3 sem pessoa", "sem música"]
    assert "00:05 voz V3 sem pessoa" in resultado and "sem música" in resultado
    montar_episodio(pasta, forcar=True, cartao=cartao)
    registro = json.loads((corte / "trabalho" / "registro.json").read_text("utf-8"))
    assert registro["alertas"] == ["00:05 voz V3 sem pessoa", "sem música"]


def test_montar_ignora_registro_ilegivel(tmp_path):
    pasta, cartao = _preparado(tmp_path)
    (pasta / "01-bom-corte" / "trabalho" / "registro.json").write_text("{quebrado", "utf-8")
    assert montar_episodio(pasta, cartao=cartao) == {1: "ok com alertas: sem música"}


def test_revisao_mostra_alertas_de_quem_fala(tmp_path):
    from esteira.revisao import escrever_revisao

    pasta, cartao = _preparado(tmp_path)
    _gravar_alerta_do_preparar(pasta / "01-bom-corte")
    montar_episodio(pasta, cartao=cartao)
    texto = escrever_revisao(pasta).read_text("utf-8")
    assert "Alertas: 00:05 voz V3 sem pessoa; sem música" in texto
