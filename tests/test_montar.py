import json

from esteira import montar
from esteira.cortar import preparar_episodio
from esteira.midia import ErroMidia, sondar
from esteira.montar import montar_episodio
from esteira.receita import Imagem, gravar_receita, ler_receita
from tests.auxiliares import preparar_episodio_teste

BOM = {"numero": 1, "titulo": "Bom corte", "inicio": 1.0, "fim": 62.9, "clima": "leve"}
OUTRO = {**BOM, "numero": 2, "titulo": "Outro"}


def _preparado(tmp_path, cortes=(BOM,)):
    pasta, cartao = preparar_episodio_teste(tmp_path, list(cortes))
    preparar_episodio(pasta, nomes=[])
    return pasta, cartao


def test_montar_gera_final(tmp_path):
    pasta, cartao = _preparado(tmp_path)
    assert montar_episodio(pasta, cartao=cartao) == {1: "ok com alertas: sem música"}
    corte = pasta / "01-bom-corte"
    assert sondar(corte / "final.mp4").duracao > 62
    registro = json.loads((corte / "registro.json").read_text("utf-8"))
    assert registro["resultado"] == "ok com alertas: sem música"
    assert registro["alertas"] == ["sem música"]
    assert registro["faixas"] and registro["corte"]["numero"] == 1


def test_receita_invalida_nao_para_os_outros(tmp_path):
    pasta, cartao = _preparado(tmp_path, [BOM, OUTRO])
    corte = pasta / "01-bom-corte"
    receita = ler_receita(corte)
    receita.imagens = [Imagem(1.0, 3.0, "imagens/nao-existe.jpg")]
    gravar_receita(corte, receita)
    r = montar_episodio(pasta, cartao=cartao)
    assert r[1].startswith("erro: ") and "não encontrada" in r[1]
    assert r[2].startswith("ok")
    assert not (corte / "final.mp4").exists()
    assert json.loads((corte / "registro.json").read_text("utf-8"))["resultado"] == r[1]


def test_corte_sem_receita(tmp_path):
    pasta, cartao = preparar_episodio_teste(tmp_path, [BOM])
    assert montar_episodio(pasta, cartao=cartao) == {1: "erro: montagem.json não encontrado, rode preparar"}


def test_nao_sobrescreve_final_sem_forcar(tmp_path):
    pasta, cartao = _preparado(tmp_path)
    montar_episodio(pasta, cartao=cartao)
    assert montar_episodio(pasta, cartao=cartao)[1] == "erro: final.mp4 já existe, use --forcar"
    assert montar_episodio(pasta, forcar=True, cartao=cartao)[1].startswith("ok")


def test_forcar_com_falha_nao_deixa_final_antigo(tmp_path, monkeypatch):
    pasta, cartao = _preparado(tmp_path)
    montar_episodio(pasta, cartao=cartao)

    def falhar(*args, **kwargs):
        raise ErroMidia("falhou")

    monkeypatch.setattr(montar, "renderizar_final", falhar)
    assert montar_episodio(pasta, forcar=True, cartao=cartao)[1] == "erro: falhou"
    assert not (pasta / "01-bom-corte" / "final.mp4").exists()


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
