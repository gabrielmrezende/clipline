import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from esteira.cortar import IMAGENS_SUGERIDAS, pasta_do_corte
from esteira.fluxo_imagens import chave_momento
from esteira.modelos import Corte
from esteira.painel.app import criar_app
from esteira.pedidos import Momento, ler_pedidos
from esteira.wikimedia import Candidata
from tests.auxiliares_painel import criar_episodio

NOME = "Entre Assuntos 03 - Arthur Cerqueira (teste imagens)"
CORTE = Corte(1, "Um", 10, 40, "tenso")


def _candidata(i: int, largura_miniatura: int = 1280) -> dict:
    return {
        "titulo": f"File:Foto {i}.jpg",
        "pagina": f"https://commons.wikimedia.org/wiki/File:Foto_{i}.jpg",
        "miniatura": f"https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Foto_{i}.jpg/{largura_miniatura}px-Foto_{i}.jpg",
        "largura": 4000, "altura": 3000, "autor": f"Autor {i}", "licenca": "CC BY 4.0",
    }


def _foto() -> Momento:
    return Momento(
        inicio=12.0, fim=15.0, fala="o ministro disse", tipo="foto", nome="Ministro",
        busca="ministro da fazenda", candidatas=[_candidata(1), _candidata(2), _candidata(3)],
        escolhas=[1], url=["https://x/1.jpg"], bytes=[100], resumidas=[1],
    )


def _ia() -> Momento:
    return Momento(
        inicio=20.0, fim=23.0, fala="o país parou", tipo="ia", nome="País parado",
        prompt="Ruas vazias ao amanhecer, estilo documental, 9:16 com o Lula ao fundo",
    )


def _noticia() -> Momento:
    return Momento(
        inicio=30.0, fim=33.0, fala="saiu na imprensa", tipo="noticia", nome="Manchete",
        titulo="Governo anuncia", veiculo="Jornal", data="2026-11-01",
    )


class CofreFalso:
    def __init__(self):
        self.dados: dict[str, str] = {}

    def ler(self, campo):
        return self.dados.get(campo)

    def gravar(self, campo, valor):
        self.dados[campo] = valor


class Ocupada:
    """Fila falsa: só responde `ativo` e `parar`."""

    def __init__(self, ativos: set[str] | None = None) -> None:
        self.ativos = ativos or set()

    def ativo(self, episodio, numero, tipo="musica"):
        return object() if tipo in self.ativos else None

    def parar(self, timeout=5):
        pass


@pytest.fixture
def ambiente(tmp_path):
    cortes = tmp_path / "cortes"
    cortes.mkdir()
    pasta = criar_episodio(cortes, NOME, [CORTE], {1})
    destino = pasta_do_corte(pasta, CORTE)
    trabalho = destino / "trabalho"
    momentos = [_foto(), _ia(), _noticia()]
    texto = json.dumps({"momentos": [m.__dict__ for m in momentos]}, ensure_ascii=False, indent=2)
    (trabalho / "pedidos.json").write_text(texto, "utf-8")
    return cortes, destino, trabalho


def _cliente(cortes, **kwargs) -> TestClient:
    kwargs.setdefault("pessoas", lambda: ["Lula"])
    kwargs.setdefault("buscar_candidatas", lambda busca: [])
    return TestClient(criar_app(cortes, **kwargs))


def _url(sufixo: str = "") -> str:
    return f"/api/episodios/{quote(NOME)}/cortes/1/momentos{sufixo}"


CHAVE_FOTO = chave_momento(_foto())
CHAVE_IA = chave_momento(_ia())
CHAVE_NOTICIA = chave_momento(_noticia())


def _momento(dados: dict, chave: str) -> dict:
    return next(m for m in dados["momentos"] if m["chave"] == chave)


def test_get_reduz_miniatura_e_acha_pessoa(ambiente):
    cortes, _, _ = ambiente
    dados = _cliente(cortes).get(_url()).json()
    foto = _momento(dados, CHAVE_FOTO)
    assert [c["miniatura"].split("/")[-1] for c in foto["candidatas"]] == [
        "500px-Foto_1.jpg", "500px-Foto_2.jpg", "500px-Foto_3.jpg",
    ]
    assert set(foto["candidatas"][0]) == {"titulo", "miniatura", "autor", "licenca", "pagina", "largura", "altura"}
    assert foto["pessoa_citada"] is None
    assert _momento(dados, CHAVE_IA)["pessoa_citada"] == "Lula"
    assert len(dados["versao"]) == 64
    noticia = _momento(dados, CHAVE_NOTICIA)
    assert (noticia["titulo"], noticia["veiculo"], noticia["data"]) == ("Governo anuncia", "Jornal", "2026-11-01")


def test_get_mantem_miniatura_pequena_e_sem_padrao(ambiente):
    cortes, _, trabalho = ambiente
    foto = _foto()
    foto.candidatas = [_candidata(1, 320), {**_candidata(2), "miniatura": "https://x/sem-padrao.jpg"}]
    texto = json.dumps({"momentos": [foto.__dict__]})
    (trabalho / "pedidos.json").write_text(texto, "utf-8")
    candidatas = _cliente(cortes).get(_url()).json()["momentos"][0]["candidatas"]
    assert candidatas[0]["miniatura"].endswith("/320px-Foto_1.jpg")
    assert candidatas[1]["miniatura"] == "https://x/sem-padrao.jpg"


BASE_THUMB = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Doc.pdf"


@pytest.mark.parametrize("miniatura, esperada", [
    (f"{BASE_THUMB}/960px-Doc.pdf.jpg", f"{BASE_THUMB}/500px-Doc.pdf.jpg"),
    (f"{BASE_THUMB}/1280px-Doc.pdf.jpg", f"{BASE_THUMB}/500px-Doc.pdf.jpg"),
    (f"{BASE_THUMB}/330px-Doc.pdf.jpg", f"{BASE_THUMB}/330px-Doc.pdf.jpg"),
    (f"{BASE_THUMB}/lossy-page1-1280px-Doc.pdf.jpg", f"{BASE_THUMB}/lossy-page1-500px-Doc.pdf.jpg"),
    (f"{BASE_THUMB}/page1-960px-Doc.pdf.jpg", f"{BASE_THUMB}/page1-500px-Doc.pdf.jpg"),
    (f"{BASE_THUMB}/page2-330px-Doc.pdf.jpg", f"{BASE_THUMB}/page2-330px-Doc.pdf.jpg"),
])
def test_miniatura_vira_largura_padrao_do_wikimedia(ambiente, miniatura, esperada):
    # O Wikimedia só serve larguras padrão: /640px- dá HTTP 400; /500px- e /330px- dão 200.
    cortes, _, trabalho = ambiente
    foto = _foto()
    foto.candidatas = [{**_candidata(1), "miniatura": miniatura}]
    (trabalho / "pedidos.json").write_text(json.dumps({"momentos": [foto.__dict__]}), "utf-8")
    assert _cliente(cortes).get(_url()).json()["momentos"][0]["candidatas"][0]["miniatura"] == esperada


def test_get_sem_pedidos_e_ilegivel(ambiente):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    (trabalho / "pedidos.json").write_text("{ruim", "utf-8")
    resposta = cliente.get(_url())
    assert resposta.status_code == 422
    assert resposta.json()["detail"].startswith("pedidos.json ilegível: ")
    (trabalho / "pedidos.json").unlink()
    assert cliente.get(_url()).json() == {
        "versao": "", "momentos": [], "aviso_glossario": None, "no_corte": [], "montagem_desatualizada": False,
    }


def test_get_fotos_prontas_e_ia(ambiente):
    cortes, destino, trabalho = ambiente
    imagens = destino / IMAGENS_SUGERIDAS
    imagens.mkdir()
    for nome in (f"{CHAVE_FOTO}-1.jpg", f"{CHAVE_NOTICIA}.png", f"{CHAVE_IA}-v1.png"):
        (imagens / nome).write_bytes(b"x")
    (trabalho / "sugeridas.json").write_text(json.dumps([f"{CHAVE_FOTO}-1.jpg", f"{CHAVE_NOTICIA}.png"]), "utf-8")
    (trabalho / "ia.json").write_text(json.dumps([
        {"momento": CHAVE_IA, "arquivo": f"{CHAVE_IA}-v2.png", "versao": 2, "provedor": "x", "data": "2026-11-09"},
        {"momento": CHAVE_IA, "arquivo": f"{CHAVE_IA}-v1.png", "versao": 1, "provedor": "x", "data": "2026-11-08"},
    ]), "utf-8")
    dados = _cliente(cortes).get(_url()).json()
    assert _momento(dados, CHAVE_FOTO)["fotos_prontas"] == [f"{CHAVE_FOTO}-1.jpg"]
    assert _momento(dados, CHAVE_NOTICIA)["fotos_prontas"] == [f"{CHAVE_NOTICIA}.png"]
    assert _momento(dados, CHAVE_IA)["ia"] == [
        {"arquivo": f"{CHAVE_IA}-v1.png", "versao": 1, "provedor": "x", "data": "2026-11-08"},
    ]


def test_ia_json_fora_do_formato_nao_derruba_o_get(ambiente):
    cortes, destino, trabalho = ambiente
    imagens = destino / IMAGENS_SUGERIDAS
    imagens.mkdir()
    (imagens / f"{CHAVE_IA}-v1.png").write_bytes(b"x")
    (trabalho / "ia.json").write_text(json.dumps([
        {"momento": CHAVE_IA, "versao": 2},
        {"momento": CHAVE_IA, "arquivo": ["lista"], "versao": 3},
        {"momento": CHAVE_IA, "arquivo": f"{CHAVE_IA}-v1.png", "versao": 1, "provedor": "x", "data": "2026-11-08"},
    ]), "utf-8")
    resposta = _cliente(cortes).get(_url())
    assert resposta.status_code == 200
    assert _momento(resposta.json(), CHAVE_IA)["ia"] == [
        {"arquivo": f"{CHAVE_IA}-v1.png", "versao": 1, "provedor": "x", "data": "2026-11-08"},
    ]


def test_foto_deixa_de_estar_pronta_quando_a_escolha_muda(ambiente):
    cortes, destino, trabalho = ambiente
    imagens = destino / IMAGENS_SUGERIDAS
    imagens.mkdir()
    (imagens / f"{CHAVE_FOTO}-1.jpg").write_bytes(b"x")
    (trabalho / "sugeridas.json").write_text(json.dumps([f"{CHAVE_FOTO}-1.jpg"]), "utf-8")
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    resposta = cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": versao, "escolhas": [2]})
    assert resposta.status_code == 200
    assert resposta.json()["momento"]["fotos_prontas"] == []


def _baixado_e_trocado(ambiente, com_creditos: bool):
    """Baixa a candidata 1; depois a escolha vira 2 e um resumo (o da CLI, por exemplo) marca resumidas=[2]."""
    cortes, destino, trabalho = ambiente
    imagens = destino / IMAGENS_SUGERIDAS
    imagens.mkdir()
    (imagens / f"{CHAVE_FOTO}-1.jpg").write_bytes(b"x")
    (trabalho / "sugeridas.json").write_text(json.dumps([f"{CHAVE_FOTO}-1.jpg"]), "utf-8")
    if com_creditos:
        c = _candidata(1)
        credito = {campo: c[campo] for campo in ("autor", "licenca", "pagina", "titulo")}
        (trabalho / "creditos.json").write_text(json.dumps({f"{CHAVE_FOTO}-1.jpg": credito}), "utf-8")
    foto = _foto()
    foto.escolhas, foto.resumidas = [2], [2]
    _gravar_momentos(trabalho, [foto])
    return _momento(_cliente(cortes).get(_url()).json(), CHAVE_FOTO)


def test_foto_baixada_de_outra_candidata_nao_fica_pronta(ambiente):
    assert _baixado_e_trocado(ambiente, com_creditos=True)["fotos_prontas"] == []


def test_foto_pronta_quando_a_procedencia_bate(ambiente):
    cortes, _, trabalho = ambiente
    _baixado_e_trocado(ambiente, com_creditos=True)
    foto = _foto()
    foto.escolhas, foto.resumidas = [1], [3]  # o resumo é antigo, mas o arquivo é da candidata 1
    _gravar_momentos(trabalho, [foto])
    assert _momento(_cliente(cortes).get(_url()).json(), CHAVE_FOTO)["fotos_prontas"] == [f"{CHAVE_FOTO}-1.jpg"]


def test_sem_creditos_vale_a_regra_do_resumo(ambiente):
    # Corte antigo, sem creditos.json: a posição conta como pronta quando o último resumo bate com a escolha.
    assert _baixado_e_trocado(ambiente, com_creditos=False)["fotos_prontas"] == [f"{CHAVE_FOTO}-1.jpg"]


def test_put_escolhas(ambiente):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    resposta = cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": versao, "escolhas": [2, 1]})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["momento"]["escolhas"] == [2, 1]
    assert corpo["versao"] != versao
    assert corpo["versao"] == cliente.get(_url()).json()["versao"]
    assert ler_pedidos(trabalho)[0].escolhas == [2, 1]


@pytest.mark.parametrize("escolhas, mensagem", [
    ([4], "Escolha fora da faixa."),
    ([0], "Escolha fora da faixa."),
    ([1, 1], "Escolha repetida."),
    ([1, 2, 3, 1], "No máximo 3 escolhas."),
])
def test_put_escolhas_invalidas(ambiente, escolhas, mensagem):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    dados = cliente.get(_url()).json()
    antes = (trabalho / "pedidos.json").read_bytes()
    resposta = cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": dados["versao"], "escolhas": escolhas})
    assert resposta.status_code == 422 and resposta.json()["detail"] == mensagem
    assert (trabalho / "pedidos.json").read_bytes() == antes


def test_put_escolhas_vazias_sao_aceitas(ambiente):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    resposta = cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": versao, "escolhas": []})
    assert resposta.status_code == 200
    assert ler_pedidos(trabalho)[0].escolhas == []


def test_put_prompt_desmarca_aprovado(ambiente):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    r = cliente.put(_url(f"/{CHAVE_IA}"), json={
        "versao": versao, "prompt": "Ruas vazias ao amanhecer", "aprovado": True,
    })
    assert r.status_code == 200 and r.json()["momento"]["aprovado"] is True
    r = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": r.json()["versao"], "prompt": "Ruas cheias"})
    assert r.status_code == 200
    assert r.json()["momento"]["aprovado"] is False and r.json()["momento"]["prompt"] == "Ruas cheias"
    assert ler_pedidos(trabalho)[1].aprovado is False


def test_aprovar_prompt_com_pessoa_real(ambiente):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    antes = (trabalho / "pedidos.json").read_bytes()
    r = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": versao, "aprovado": True})
    assert r.status_code == 422
    assert r.json()["detail"] == "Cita pessoa real (Lula): não pode gerar"
    r = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": versao, "prompt": "lula num palanque", "aprovado": True})
    assert r.status_code == 422 and r.json()["detail"] == "Cita pessoa real (Lula): não pode gerar"
    assert (trabalho / "pedidos.json").read_bytes() == antes


def test_aprovar_exige_prompt_e_ia(ambiente):
    cortes, _, _ = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    r = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": versao, "prompt": "  ", "aprovado": True})
    assert r.status_code == 422 and r.json()["detail"] == "Escreva o prompt antes de aprovar."
    r = cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": versao, "aprovado": True})
    assert r.status_code == 422 and r.json()["detail"] == "Só momentos de IA têm aprovação."


def test_conflito_quando_o_claude_regrava(ambiente):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    arquivo = trabalho / "pedidos.json"
    dados = json.loads(arquivo.read_text("utf-8"))
    dados["momentos"][0]["nome"] = "Ministro (Claude mudou)"
    arquivo.write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
    por_fora = arquivo.read_bytes()
    resposta = cliente.put(_url(f"/{chave_momento(_foto())}"), json={"versao": versao, "escolhas": [2]})
    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["detail"] == "O pedidos.json mudou desde que você abriu."
    assert corpo["versao_atual"] != versao and len(corpo["versao_atual"]) == 64
    assert arquivo.read_bytes() == por_fora


def test_put_chave_inexistente(ambiente):
    cortes, _, _ = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    assert cliente.put(_url("/9999-nada"), json={"versao": versao}).status_code == 404


def test_troca_de_tipo(ambiente):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    r = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": versao, "prompt": "Ruas vazias", "aprovado": True})
    r = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": r.json()["versao"], "tipo": "foto"})
    assert r.status_code == 200
    momento = r.json()["momento"]
    assert momento["tipo"] == "foto" and momento["busca"] == "País parado" and momento["aprovado"] is False
    r = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": r.json()["versao"], "tipo": "ia"})
    assert r.status_code == 200 and r.json()["momento"]["tipo"] == "ia"
    assert ler_pedidos(trabalho)[1].tipo == "ia"


def test_tipo_invalido_e_noticia(ambiente):
    cortes, _, _ = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    r = cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": versao, "tipo": "video"})
    assert r.status_code == 422 and r.json()["detail"] == "Tipo inválido."
    r = cliente.put(_url(f"/{CHAVE_NOTICIA}"), json={"versao": versao, "tipo": "foto"})
    assert r.status_code == 422 and r.json()["detail"] == "Notícia não troca de tipo pelo painel."


def test_put_descartar(ambiente):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    r = cliente.put(_url(f"/{CHAVE_NOTICIA}"), json={"versao": versao, "descartar": True})
    assert r.status_code == 200 and r.json()["momento"]["descartar"] is True
    assert ler_pedidos(trabalho)[2].descartar is True


def test_fotos_em_andamento_bloqueiam_put_e_buscar(ambiente):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes, fila=Ocupada({"fotos"}))
    versao = cliente.get(_url()).json()["versao"]
    antes = (trabalho / "pedidos.json").read_bytes()
    r = cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": versao, "escolhas": [2]})
    assert r.status_code == 409 and r.json() == {"detail": "Espere o download das fotos terminar."}
    r = cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"versao": versao, "busca": "outra"})
    assert r.status_code == 409 and r.json() == {"detail": "Espere o download das fotos terminar."}
    assert (trabalho / "pedidos.json").read_bytes() == antes


def test_buscar_troca_candidatas_e_zera_escolhas(ambiente):
    cortes, _, trabalho = ambiente
    pedidas = []

    def falsa(busca):
        pedidas.append(busca)
        return [Candidata("File:Nova.jpg", "https://p", "https://x/thumb/1000px-Nova.jpg", 2000, 1500, "Eu", "CC0")]

    cliente = _cliente(cortes, buscar_candidatas=falsa)
    versao = cliente.get(_url()).json()["versao"]
    r = cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"versao": versao, "busca": "  planalto  "})
    assert r.status_code == 200
    corpo = r.json()
    assert pedidas == ["planalto"]
    momento = corpo["momento"]
    assert momento["busca"] == "planalto" and momento["escolhas"] == []
    assert [c["titulo"] for c in momento["candidatas"]] == ["File:Nova.jpg"]
    assert momento["candidatas"][0]["miniatura"].endswith("/500px-Nova.jpg")
    gravado = ler_pedidos(trabalho)[0]
    assert gravado.escolhas == [] and gravado.url == [] and gravado.bytes == [] and gravado.resumidas == []
    assert gravado.candidatas[0]["titulo"] == "File:Nova.jpg"
    assert corpo["versao"] == cliente.get(_url()).json()["versao"]


def test_buscar_erros(ambiente):
    cortes, _, _ = ambiente

    def cai(busca):
        raise OSError("sem internet")

    cliente = _cliente(cortes, buscar_candidatas=cai)
    versao = cliente.get(_url()).json()["versao"]
    r = cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"versao": versao, "busca": "  "})
    assert r.status_code == 422 and r.json()["detail"] == "Escreva o que buscar."
    r = cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"versao": versao, "busca": "x"})
    assert r.status_code == 422 and r.json()["detail"] == "Não consegui buscar no Wikimedia: sem internet"
    r = cliente.post(_url(f"/{CHAVE_IA}/buscar"), json={"versao": versao, "busca": "x"})
    assert r.status_code == 422 and r.json()["detail"] == "Só momentos de foto buscam no Wikimedia."
    assert cliente.post(_url("/9999-nada/buscar"), json={"versao": versao, "busca": "x"}).status_code == 404
    assert cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"busca": "x"}).status_code == 422  # sem versão


def _claude_regrava_outro_momento(trabalho) -> bytes:
    arquivo = trabalho / "pedidos.json"
    dados = json.loads(arquivo.read_text("utf-8"))
    dados["momentos"][2]["titulo"] = "Governo anuncia (Claude mudou)"
    arquivo.write_text(json.dumps(dados, ensure_ascii=False), "utf-8")
    return arquivo.read_bytes()


def test_buscar_com_versao_antiga_da_409_sem_ir_a_rede(ambiente):
    cortes, _, trabalho = ambiente
    pedidas = []
    cliente = _cliente(cortes, buscar_candidatas=lambda busca: pedidas.append(busca) or [])
    versao = cliente.get(_url()).json()["versao"]
    por_fora = _claude_regrava_outro_momento(trabalho)
    r = cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"versao": versao, "busca": "planalto"})
    assert r.status_code == 409
    atual = cliente.get(_url()).json()["versao"]
    assert r.json() == {"detail": "O pedidos.json mudou desde que você abriu.", "versao_atual": atual}
    assert (trabalho / "pedidos.json").read_bytes() == por_fora and pedidas == []


def test_buscar_quando_o_claude_regrava_durante_a_busca_da_409(ambiente):
    cortes, _, trabalho = ambiente
    regravado = {}

    def busca_lenta(busca):
        regravado["bytes"] = _claude_regrava_outro_momento(trabalho)  # enquanto a rede responde
        return [Candidata("File:Nova.jpg", "https://p", "https://x/thumb/1000px-Nova.jpg", 2000, 1500, "Eu", "CC0")]

    cliente = _cliente(cortes, buscar_candidatas=busca_lenta)
    versao = cliente.get(_url()).json()["versao"]
    r = cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"versao": versao, "busca": "planalto"})
    assert r.status_code == 409 and r.json()["detail"] == "O pedidos.json mudou desde que você abriu."
    assert r.json()["versao_atual"] != versao
    assert (trabalho / "pedidos.json").read_bytes() == regravado["bytes"]  # a edição do Claude fica
    assert ler_pedidos(trabalho)[0].candidatas[0]["titulo"] == "File:Foto 1.jpg"  # as buscadas foram descartadas


def test_rede_sem_cookie_da_401(ambiente):
    cortes, _, _ = ambiente
    cliente = _cliente(cortes, rede=True, cofre=CofreFalso())
    assert cliente.get(_url()).status_code == 401
    assert cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": ""}).status_code == 401
    assert cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"versao": "", "busca": "x"}).status_code == 401


# ---------------------------------------------------------------------------
# Task 7: fotos, IA, orçamento e configurações
# ---------------------------------------------------------------------------

import io
import threading

from PIL import Image

from esteira.fluxo_imagens import ler_ia
from esteira.imagens_ia import chaves
from esteira.imagens_ia.provedor import ErroTemporario, SemChave
from esteira.painel.troca_musica import Resultado


def _png(tamanho=(1024, 1536)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", tamanho, (128, 128, 128)).save(buffer, "PNG")
    return buffer.getvalue()


def _consultar(params):
    return {"query": {"pages": [{"imageinfo": [{"thumburl": "https://x/final.jpg"}]}]}}


def _baixar(url, destino):
    destino.write_bytes(_png((1600, 900)))


def _esperar(condicao):
    for _ in range(200):
        valor = condicao()
        if valor:
            return valor
        threading.Event().wait(0.05)
    return condicao()


class ProvedorFalso:
    nome = "openai"

    def __init__(self, erro=None, entrou=None, solto=None):
        self.erro, self.entrou, self.solto = erro, entrou, solto
        self.prompts: list[str] = []

    def gerar(self, prompt, proporcao="9:16"):
        self.prompts.append(prompt)
        if self.entrou is not None:
            self.entrou.set()
            assert self.solto.wait(10)
        if self.erro:
            raise self.erro
        return _png()


def _fabricas(provedor):
    return {"openai": lambda dados: provedor, "google": lambda dados: provedor}


def _ia_aprovada(inicio: float, nome: str) -> Momento:
    return Momento(
        inicio=inicio, fim=inicio + 3, fala="fala", tipo="ia", nome=nome,
        prompt=f"Ruas vazias ao amanhecer {nome}", aprovado=True,
    )


def _gravar_momentos(trabalho, momentos):
    texto = json.dumps({"momentos": [m.__dict__ for m in momentos]}, ensure_ascii=False, indent=2)
    (trabalho / "pedidos.json").write_text(texto, "utf-8")


def _cliente_ia(cortes, **kwargs) -> TestClient:
    kwargs.setdefault("config_ia", cortes / "imagens-ia.json")
    kwargs.setdefault("consultar", _consultar)
    kwargs.setdefault("medir", lambda url: 2_621_440)
    kwargs.setdefault("baixar", _baixar)
    kwargs.setdefault("tem_chave", lambda provedor: False)
    return _cliente(cortes, **kwargs)


def _fechar(cliente):
    cliente.app.state.fila.parar(5)


def _fotos_url(sufixo: str = "") -> str:
    return f"/api/episodios/{quote(NOME)}/cortes/1/fotos{sufixo}"


def _ia_url(sufixo: str = "") -> str:
    return f"/api/episodios/{quote(NOME)}/cortes/1/ia{sufixo}"


def _pedido_pronto(cliente, id):
    def terminou():
        p = cliente.get(f"/api/tarefas/{id}").json()
        return p if p["estado"] in ("pronto", "erro") else None

    return _esperar(terminou)


CONFIRMADO = {"confirmado": True}
CHAVE_UM = chave_momento(_ia_aprovada(20.0, "Um"))
CHAVE_DOIS = chave_momento(_ia_aprovada(24.0, "Dois"))


def _confirmados(cliente, url_orcamento) -> dict:
    """O corpo que a tela manda: os itens do orçamento que o dono confirmou."""
    return {"itens": cliente.get(url_orcamento).json()["itens"]}


def test_resumo_de_fotos_nao_grava(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto()])
    cliente = _cliente_ia(cortes)
    antes = (trabalho / "pedidos.json").read_bytes()
    r = cliente.get(_fotos_url("/resumo"))
    assert r.status_code == 200
    assert r.json() == {"fotos": 1, "megabytes": 2.5, "origem": "Wikimedia Commons", "avisos": []}
    assert (trabalho / "pedidos.json").read_bytes() == antes
    r = cliente.get(f"/api/episodios/{quote(NOME)}/fotos/resumo")
    assert r.status_code == 200 and r.json()["fotos"] == 1
    _fechar(cliente)


def test_resumo_de_fotos_avisa_tamanho_desconhecido(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto()])
    cliente = _cliente_ia(cortes, medir=lambda url: None)
    dados = cliente.get(_fotos_url("/resumo")).json()
    assert dados["fotos"] == 1 and dados["megabytes"] == 0
    assert dados["avisos"] == ["Corte 1: ok com alertas: 0:12 Ministro: opção 1 com tamanho desconhecido"]
    _fechar(cliente)


def test_avisos_do_resumo_nomeiam_o_momento_como_o_cartao(ambiente):
    # "momento N" é a posição no arquivo, que o cartão não mostra: o painel usa o tempo e o nome.
    cortes, _, trabalho = ambiente
    foto = _foto()
    foto.escolhas, foto.url, foto.bytes, foto.resumidas = [], [], [], []
    sem_prompt = _ia_aprovada(20.0, "País parado")
    sem_prompt.prompt, sem_prompt.aprovado = "", False
    com_pessoa = _ia_aprovada(25.0, "Palanque")
    com_pessoa.prompt = "Lula num palanque"
    _gravar_momentos(trabalho, [foto, sem_prompt, com_pessoa])
    cliente = _cliente_ia(cortes)
    dados = cliente.get(_fotos_url("/resumo")).json()
    assert dados["fotos"] == 0
    assert dados["avisos"] == [
        "Corte 1: erro: 0:20 País parado: IA sem prompt (escreva o prompt ou descarte o momento); "
        "0:25 Palanque: prompt cita pessoa real (Lula)"
    ]
    _gravar_momentos(trabalho, [foto])
    dados = cliente.get(_fotos_url("/resumo")).json()
    assert dados["avisos"] == [
        "Corte 1: erro: 0:12 Ministro: nenhuma foto escolhida (escolha ao menos uma foto ou descarte o momento)"
    ]
    r = cliente.post(_fotos_url(), json=CONFIRMADO)
    final = _pedido_pronto(cliente, r.json()["id"])
    assert final["estado"] == "erro" and "momento 1" not in final["mensagem"]
    assert final["mensagem"] == (
        "Corte 1: erro: 0:12 Ministro: nenhuma foto escolhida (escolha ao menos uma foto ou descarte o momento)"
    )
    _fechar(cliente)


def test_avisos_do_download_nomeiam_o_momento_como_o_cartao(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto()])

    def cai(url, destino):
        raise OSError("sem internet")

    cliente = _cliente_ia(cortes, baixar=cai)
    r = cliente.post(_fotos_url(), json=CONFIRMADO)
    final = _pedido_pronto(cliente, r.json()["id"])
    assert final["estado"] == "pronto"
    assert final["avisos"] == ["Corte 1: ok com alertas: 0:12 Ministro: download falhou"]
    _fechar(cliente)


def test_post_fotos_baixa_e_bloqueia_edicao(ambiente):
    cortes, destino, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto()])
    entrou, solto = threading.Event(), threading.Event()

    def baixar(url, caminho):
        entrou.set()
        assert solto.wait(10)
        _baixar(url, caminho)

    cliente = _cliente_ia(cortes, baixar=baixar)
    versao = cliente.get(_url()).json()["versao"]
    r = cliente.post(_fotos_url(), json=CONFIRMADO)
    assert r.status_code == 202
    pedido = r.json()
    assert pedido["tipo"] == "fotos" and pedido["cortes"] == [1]
    assert entrou.wait(10)
    r = cliente.post(_fotos_url(), json=CONFIRMADO)
    assert r.status_code == 409
    assert r.json() == {"detail": "Já há um pedido de fotos em andamento para este corte."}
    r = cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": versao, "escolhas": [2]})
    assert r.status_code == 409 and r.json() == {"detail": "Espere o download das fotos terminar."}
    assert cliente.get(f"/api/tarefas/{pedido['id']}").json()["progresso"] == "Baixando 1 de 1…"
    solto.set()
    final = _pedido_pronto(cliente, pedido["id"])
    assert final["estado"] == "pronto" and final["avisos"] == []
    momento = _momento(cliente.get(_url()).json(), CHAVE_FOTO)
    assert momento["fotos_prontas"] == [f"{CHAVE_FOTO}-1.jpg"]
    assert (destino / IMAGENS_SUGERIDAS / f"{CHAVE_FOTO}-1.jpg").is_file()
    _fechar(cliente)


def test_post_fotos_do_episodio(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto()])
    cliente = _cliente_ia(cortes)
    r = cliente.post(f"/api/episodios/{quote(NOME)}/fotos", json=CONFIRMADO)
    assert r.status_code == 202 and r.json()["tipo"] == "fotos"
    assert _pedido_pronto(cliente, r.json()["id"])["estado"] == "pronto"
    _fechar(cliente)


def test_post_fotos_sem_pedidos_da_422(ambiente):
    cortes, _, trabalho = ambiente
    (trabalho / "pedidos.json").unlink()
    cliente = _cliente_ia(cortes)
    for url in (_fotos_url(), f"/api/episodios/{quote(NOME)}/fotos"):
        r = cliente.post(url, json=CONFIRMADO)
        assert r.status_code == 422 and r.json()["detail"] == "Nenhum corte com momentos de imagem."
    _fechar(cliente)


def test_fotos_com_wikimedia_fora_termina_em_erro(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto()])

    def cai(params):
        raise OSError("sem internet")

    cliente = _cliente_ia(cortes, consultar=cai)
    r = cliente.post(_fotos_url(), json=CONFIRMADO)
    final = _pedido_pronto(cliente, r.json()["id"])
    assert final["estado"] == "erro" and "Wikimedia indisponível" in final["mensagem"]
    _fechar(cliente)


def test_orcamento_de_dois_aprovados(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto(), _ia_aprovada(20.0, "Um"), _ia_aprovada(24.0, "Dois"), _noticia()])
    (cortes / "imagens-ia.json").write_text(json.dumps({
        "provedor": "openai", "provedores": {"openai": {"preco_usd": 0.05}},
    }), "utf-8")
    cliente = _cliente_ia(cortes)
    esperado = {
        "imagens": 2, "provedor": "openai", "modelo": "gpt-image-2", "custo_usd": 0.10,
        "itens": [{"corte": 1, "chave": CHAVE_UM}, {"corte": 1, "chave": CHAVE_DOIS}],
    }
    assert cliente.get(_ia_url("/orcamento")).json() == esperado
    assert cliente.get(f"/api/episodios/{quote(NOME)}/ia/orcamento").json() == esperado
    _fechar(cliente)


def test_orcamento_com_config_ilegivel(ambiente):
    cortes, _, _ = ambiente
    (cortes / "imagens-ia.json").write_text("{ruim", "utf-8")
    cliente = _cliente_ia(cortes)
    r = cliente.get(_ia_url("/orcamento"))
    assert r.status_code == 422 and r.json()["detail"] == "imagens-ia.json ilegível"
    _fechar(cliente)


def test_post_ia_gera_e_bloqueia_repetido(ambiente):
    cortes, destino, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto(), _ia_aprovada(20.0, "Um"), _ia_aprovada(24.0, "Dois"), _noticia()])
    entrou, solto = threading.Event(), threading.Event()
    provedor = ProvedorFalso(entrou=entrou, solto=solto)
    cliente = _cliente_ia(cortes, provedores=_fabricas(provedor))
    r = cliente.post(_ia_url(), json=_confirmados(cliente, _ia_url("/orcamento")))
    assert r.status_code == 202 and r.json()["tipo"] == "ia"
    assert entrou.wait(10)
    r2 = cliente.post(_ia_url(), json=_confirmados(cliente, _ia_url("/orcamento")))
    assert r2.status_code == 409
    assert r2.json() == {"detail": "Já há um pedido de imagens em andamento para este corte."}
    solto.set()
    final = _pedido_pronto(cliente, r.json()["id"])
    assert final["estado"] == "pronto" and final["avisos"] == [] and "2" in final["mensagem"]
    assert len(list((destino / IMAGENS_SUGERIDAS).glob("*-ia-1.jpg"))) == 2
    dados = cliente.get(_url()).json()
    assert [len(m["ia"]) for m in dados["momentos"] if m["tipo"] == "ia"] == [1, 1]
    r = cliente.post(_ia_url(), json=_confirmados(cliente, _ia_url("/orcamento")))
    assert r.status_code == 422 and r.json()["detail"] == "Nenhuma imagem aprovada para gerar."
    _fechar(cliente)


def test_post_ia_do_episodio(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto(), _ia_aprovada(20.0, "Um")])
    cliente = _cliente_ia(cortes, provedores=_fabricas(ProvedorFalso()))
    r = cliente.post(f"/api/episodios/{quote(NOME)}/ia", json=_confirmados(cliente, f"/api/episodios/{quote(NOME)}/ia/orcamento"))
    assert r.status_code == 202
    assert _pedido_pronto(cliente, r.json()["id"])["estado"] == "pronto"
    r = cliente.post(f"/api/episodios/{quote(NOME)}/ia", json={"itens": [{"corte": 1, "chave": CHAVE_UM}]})
    assert r.status_code == 422 and r.json()["detail"] == "Nenhuma imagem aprovada para gerar."
    _fechar(cliente)


def test_sem_chave_termina_com_aviso(ambiente):
    cortes, destino, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto(), _ia_aprovada(20.0, "Um"), _ia_aprovada(24.0, "Dois")])
    cliente = _cliente_ia(cortes, provedores=_fabricas(ProvedorFalso(erro=SemChave("openai"))))
    r = cliente.post(_ia_url(), json=_confirmados(cliente, _ia_url("/orcamento")))
    final = _pedido_pronto(cliente, r.json()["id"])
    assert final["estado"] == "pronto"
    assert len(final["avisos"]) == 2
    assert all("Rode python -m esteira imagens conectar openai" in a for a in final["avisos"])
    imagens = destino / IMAGENS_SUGERIDAS
    assert not imagens.exists() or not list(imagens.glob("*-ia-*"))
    _fechar(cliente)


def test_gerar_de_novo_cria_a_versao_2(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto(), _ia_aprovada(20.0, "Um")])
    chave = chave_momento(_ia_aprovada(20.0, "Um"))
    cliente = _cliente_ia(cortes, provedores=_fabricas(ProvedorFalso()))
    r = cliente.post(_ia_url(), json=_confirmados(cliente, _ia_url("/orcamento")))
    _pedido_pronto(cliente, r.json()["id"])
    r = cliente.post(_url(f"/{chave}/ia"), json=CONFIRMADO)
    assert r.status_code == 202 and r.json()["tipo"] == "ia"
    final = _pedido_pronto(cliente, r.json()["id"])
    assert final["estado"] == "pronto" and final["mensagem"] == f"{chave}-ia-2.jpg"
    momento = _momento(cliente.get(_url()).json(), chave)
    assert [i["versao"] for i in momento["ia"]] == [1, 2]
    _fechar(cliente)


def test_gerar_de_novo_com_erro_do_provedor(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto(), _ia_aprovada(20.0, "Um")])
    chave = chave_momento(_ia_aprovada(20.0, "Um"))
    erro = ErroTemporario("openai", "limite")
    cliente = _cliente_ia(cortes, provedores=_fabricas(ProvedorFalso(erro=erro)))
    r = cliente.post(_url(f"/{chave}/ia"), json=CONFIRMADO)
    final = _pedido_pronto(cliente, r.json()["id"])
    assert final["estado"] == "erro" and final["mensagem"] == str(erro)
    assert cliente.post(_url("/9999-nada/ia"), json=CONFIRMADO).status_code == 404
    _fechar(cliente)


def test_gerar_de_novo_repetido_da_409(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto(), _ia_aprovada(20.0, "Um")])
    chave = chave_momento(_ia_aprovada(20.0, "Um"))
    entrou, solto = threading.Event(), threading.Event()
    cliente = _cliente_ia(cortes, provedores=_fabricas(ProvedorFalso(entrou=entrou, solto=solto)))
    r = cliente.post(_url(f"/{chave}/ia"), json=CONFIRMADO)
    assert entrou.wait(10)
    r2 = cliente.post(_url(f"/{chave}/ia"), json=CONFIRMADO)
    assert r2.status_code == 409
    assert r2.json() == {"detail": "Já há um pedido de imagens em andamento para este corte."}
    solto.set()
    _pedido_pronto(cliente, r.json()["id"])
    _fechar(cliente)


def test_gera_so_o_que_foi_confirmado(ambiente):
    cortes, destino, trabalho = ambiente
    dois = _ia_aprovada(24.0, "Dois")
    dois.aprovado = False
    _gravar_momentos(trabalho, [_foto(), _ia_aprovada(20.0, "Um"), dois])
    provedor = ProvedorFalso()
    cliente = _cliente_ia(cortes, provedores=_fabricas(provedor))
    mostrado = cliente.get(_ia_url("/orcamento")).json()
    assert mostrado["imagens"] == 1 and mostrado["itens"] == [{"corte": 1, "chave": CHAVE_UM}]
    versao = cliente.get(_url()).json()["versao"]
    r = cliente.put(_url(f"/{CHAVE_DOIS}"), json={"versao": versao, "aprovado": True})  # depois do orçamento
    assert r.status_code == 200
    r = cliente.post(_ia_url(), json={"itens": mostrado["itens"]})
    assert r.status_code == 202
    final = _pedido_pronto(cliente, r.json()["id"])
    assert final["estado"] == "pronto" and final["mensagem"] == "1 imagem gerada."
    assert provedor.prompts == ["Ruas vazias ao amanhecer Um"]
    assert sorted(p.name for p in (destino / IMAGENS_SUGERIDAS).glob("*-ia-*")) == [f"{CHAVE_UM}-ia-1.jpg"]
    assert cliente.get(_ia_url("/orcamento")).json()["itens"] == [{"corte": 1, "chave": CHAVE_DOIS}]
    _fechar(cliente)


@pytest.mark.parametrize("itens", [
    [],
    [{"corte": 2, "chave": CHAVE_UM}],
    [{"corte": 1, "chave": "9999-nada"}],
])
def test_post_ia_sem_nenhum_pendente_confirmado(ambiente, itens):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_ia_aprovada(20.0, "Um")])
    provedor = ProvedorFalso()
    cliente = _cliente_ia(cortes, provedores=_fabricas(provedor))
    for url in (_ia_url(), f"/api/episodios/{quote(NOME)}/ia"):
        r = cliente.post(url, json={"itens": itens})
        assert r.status_code == 422 and r.json()["detail"] == "Nenhuma imagem aprovada para gerar."
    assert provedor.prompts == [] and cliente.get("/api/tarefas").json() == []
    _fechar(cliente)


def test_posts_que_custam_exigem_corpo_json(ambiente):
    # Sem corpo JSON, uma página qualquer aberta no navegador do dono não dispara o pedido (CSRF).
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_foto(), _ia_aprovada(20.0, "Um")])
    provedor = ProvedorFalso()
    cliente = _cliente_ia(cortes, provedores=_fabricas(provedor))
    itens = {"itens": [{"corte": 1, "chave": CHAVE_UM}]}
    corpos = {
        _ia_url(): itens,
        f"/api/episodios/{quote(NOME)}/ia": itens,
        _url(f"/{CHAVE_UM}/ia"): CONFIRMADO,
        _fotos_url(): CONFIRMADO,
        f"/api/episodios/{quote(NOME)}/fotos": CONFIRMADO,
    }
    for url, corpo in corpos.items():
        assert cliente.post(url).status_code == 422, url
        for tipo in ("text/plain", "application/x-www-form-urlencoded", None):
            cabecalhos = {"Content-Type": tipo} if tipo else {}
            r = cliente.post(url, content=json.dumps(corpo), headers=cabecalhos)
            assert r.status_code == 422, (url, tipo)
    for url in (_url(f"/{CHAVE_UM}/ia"), _fotos_url(), f"/api/episodios/{quote(NOME)}/fotos"):
        assert cliente.post(url, json={"confirmado": False}).status_code == 422, url
        assert cliente.post(url, json={}).status_code == 422, url
    assert provedor.prompts == [] and cliente.get("/api/tarefas").json() == []
    _fechar(cliente)


def test_gerar_de_novo_com_registro_falho_termina_pronto_com_aviso(ambiente, monkeypatch):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_ia_aprovada(20.0, "Um")])

    def falha(*args, **kwargs):
        raise OSError("ia.json travado")

    monkeypatch.setattr("esteira.imagens_ia.gerar.registrar_ia", falha)
    cliente = _cliente_ia(cortes, provedores=_fabricas(ProvedorFalso()))
    r = cliente.post(_url(f"/{CHAVE_UM}/ia"), json=CONFIRMADO)
    final = _pedido_pronto(cliente, r.json()["id"])
    assert final["estado"] == "pronto" and final["mensagem"] == f"{CHAVE_UM}-ia-1.jpg"
    assert final["avisos"] == ["imagem salva, mas não consegui atualizar o registro: ia.json travado"]
    momento = _momento(cliente.get(_url()).json(), CHAVE_UM)
    assert [(i["arquivo"], i["versao"]) for i in momento["ia"]] == [(f"{CHAVE_UM}-ia-1.jpg", 1)]  # a imagem paga aparece
    assert cliente.get(_ia_url("/orcamento")).json()["imagens"] == 0
    _fechar(cliente)


def test_fechar_o_painel_no_meio_nao_comeca_a_proxima_geracao(ambiente):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_ia_aprovada(20.0, "Um"), _ia_aprovada(24.0, "Dois")])
    entrou, solto = threading.Event(), threading.Event()
    provedor = ProvedorFalso(entrou=entrou, solto=solto)
    cliente = _cliente_ia(cortes, provedores=_fabricas(provedor))
    r = cliente.post(_ia_url(), json=_confirmados(cliente, _ia_url("/orcamento")))
    assert entrou.wait(10)
    fila = cliente.app.state.fila
    parada = threading.Thread(target=fila.parar, kwargs={"timeout": 10})
    parada.start()
    assert _esperar(fila._parando.is_set)
    solto.set()
    parada.join(10)
    assert not parada.is_alive()
    final = fila.pedido(r.json()["id"])
    assert final.estado == "erro" and final.mensagem == "o painel foi fechado no meio deste pedido"
    assert provedor.prompts == ["Ruas vazias ao amanhecer Um"]  # a segunda geração paga não começou
    assert [i["arquivo"] for i in ler_ia(trabalho)] == [f"{CHAVE_UM}-ia-1.jpg"]  # a primeira ficou registrada


GLOSSARIO = "Não consegui ler o glossário (Contexto/glossario.md): nada foi aprovado nem gerado."


def _sem_permissao():
    raise PermissionError("glossario.md travado")


def _utf8_ruim():
    raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "byte inválido")


@pytest.mark.parametrize("pessoas", [_sem_permissao, _utf8_ruim])
def test_glossario_ilegivel_recusa_aprovar_e_gerar(ambiente, pessoas):
    cortes, _, trabalho = ambiente
    dois = _ia_aprovada(24.0, "Dois")
    dois.aprovado = False
    _gravar_momentos(trabalho, [_foto(), _ia_aprovada(20.0, "Um"), dois])
    provedor = ProvedorFalso()
    cliente = _cliente_ia(cortes, pessoas=pessoas, provedores=_fabricas(provedor))
    r = cliente.get(_url())
    assert r.status_code == 200
    dados = r.json()
    assert dados["aviso_glossario"] == GLOSSARIO
    assert [m["pessoa_citada"] for m in dados["momentos"]] == [None, None, None]
    antes = (trabalho / "pedidos.json").read_bytes()
    r = cliente.put(_url(f"/{CHAVE_DOIS}"), json={"versao": dados["versao"], "aprovado": True})
    assert r.status_code == 422 and r.json()["detail"] == GLOSSARIO
    assert (trabalho / "pedidos.json").read_bytes() == antes
    r = cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": dados["versao"], "escolhas": [2]})
    assert r.status_code == 200 and r.json()["momento"]["pessoa_citada"] is None  # o resto da revisão segue
    itens = {"itens": [{"corte": 1, "chave": CHAVE_UM}]}
    for url, corpo in ((_ia_url(), itens), (f"/api/episodios/{quote(NOME)}/ia", itens), (_url(f"/{CHAVE_UM}/ia"), CONFIRMADO)):
        r = cliente.post(url, json=corpo)
        assert r.status_code == 422 and r.json()["detail"] == GLOSSARIO, url
    assert provedor.prompts == [] and cliente.get("/api/tarefas").json() == []
    _fechar(cliente)


def test_padrao_do_painel_fecha_sem_glossario(ambiente, monkeypatch, tmp_path):
    from esteira.painel import app as modulo_app

    cortes, _, trabalho = ambiente
    contexto = tmp_path / "contexto"
    contexto.mkdir()
    monkeypatch.setattr(modulo_app, "CONTEXTO", contexto)  # sem glossario.md
    dois = _ia_aprovada(24.0, "Dois")
    dois.aprovado = False
    _gravar_momentos(trabalho, [dois])
    cliente = TestClient(criar_app(cortes, buscar_candidatas=lambda busca: []))
    dados = cliente.get(_url()).json()
    assert dados["aviso_glossario"] == GLOSSARIO
    r = cliente.put(_url(f"/{CHAVE_DOIS}"), json={"versao": dados["versao"], "aprovado": True})
    assert r.status_code == 422 and r.json()["detail"] == GLOSSARIO
    (contexto / "glossario.md").write_bytes(b"## Pessoas\n- Dois\n")
    dados = cliente.get(_url()).json()
    assert dados["aviso_glossario"] is None and dados["momentos"][0]["pessoa_citada"] == "Dois"
    (contexto / "glossario.md").write_bytes(b"## Pessoas\n- Dois\xff\n")
    assert cliente.get(_url()).json()["aviso_glossario"] == GLOSSARIO
    cliente.app.state.fila.parar(5)


def test_get_com_glossario_legivel_nao_tem_aviso(ambiente):
    cortes, _, _ = ambiente
    assert _cliente(cortes).get(_url()).json()["aviso_glossario"] is None


@pytest.mark.parametrize("sufixo", ["", "/{chave}/ia"])
def test_trabalhador_recusa_gerar_se_o_glossario_ficar_ilegivel(ambiente, sufixo):
    cortes, _, trabalho = ambiente
    _gravar_momentos(trabalho, [_ia_aprovada(20.0, "Um")])
    legivel = {"sim": True}

    def pessoas():
        if not legivel["sim"]:
            _utf8_ruim()
        return ["Lula"]

    provedor = ProvedorFalso()
    cliente = _cliente_ia(cortes, pessoas=pessoas, provedores=_fabricas(provedor))
    ocupada, solta = threading.Event(), threading.Event()

    def segura(progresso):  # ocupa o trabalhador até o glossário ficar ilegível
        ocupada.set()
        assert solta.wait(10)
        return Resultado("pronto", "ok", [], None)

    cliente.app.state.fila.pedir_tarefa("fotos", trabalho.parent.parent, [1], segura)
    assert ocupada.wait(10)
    if sufixo:
        r = cliente.post(_url(sufixo.format(chave=CHAVE_UM)), json=CONFIRMADO)
    else:
        r = cliente.post(_ia_url(), json={"itens": [{"corte": 1, "chave": CHAVE_UM}]})
    assert r.status_code == 202
    legivel["sim"] = False
    solta.set()
    final = _pedido_pronto(cliente, r.json()["id"])
    assert final["estado"] == "erro" and final["mensagem"] == GLOSSARIO
    assert provedor.prompts == []
    _fechar(cliente)


class KeyringFalso:
    def __init__(self):
        self.dados = {(chaves.SERVICO, "openai:chave"): "sk-segredo"}

    def get_password(self, servico, usuario):
        return self.dados.get((servico, usuario))


def test_configuracoes_get_nao_vaza_a_chave(ambiente, monkeypatch):
    cortes, _, _ = ambiente
    monkeypatch.setattr(chaves, "_keyring", lambda: KeyringFalso())
    cliente = _cliente_ia(cortes, tem_chave=chaves.tem_chave)
    r = cliente.get("/api/configuracoes/imagens")
    assert r.status_code == 200
    assert "sk-segredo" not in r.text
    dados = r.json()
    assert dados["provedor"] == "openai"
    assert dados["chaves"] == {"openai": True, "google": False}
    assert set(dados["provedores"]) == {"openai", "google"}
    assert dados["provedores"]["openai"]["preco_usd"] == 0.041
    _fechar(cliente)


def test_configuracoes_put(ambiente):
    cortes, _, _ = ambiente
    cliente = _cliente_ia(cortes, tem_chave=lambda p: p == "google")
    atual = cliente.get("/api/configuracoes/imagens").json()
    novos = {**atual["provedores"], "google": {**atual["provedores"]["google"], "preco_usd": 0.07}}
    r = cliente.put("/api/configuracoes/imagens", json={"provedor": "google", "provedores": novos})
    assert r.status_code == 200
    assert r.json()["provedor"] == "google" and r.json()["provedores"]["google"]["preco_usd"] == 0.07
    assert r.json()["chaves"] == {"openai": False, "google": True}
    assert cliente.get("/api/configuracoes/imagens").json() == r.json()
    assert json.loads((cortes / "imagens-ia.json").read_text("utf-8"))["provedor"] == "google"
    _fechar(cliente)


def test_configuracoes_put_nunca_grava_campo_extra(ambiente):
    cortes, _, _ = ambiente
    cliente = _cliente_ia(cortes)
    atual = cliente.get("/api/configuracoes/imagens").json()
    novos = {**atual["provedores"], "openai": {**atual["provedores"]["openai"], "chave": "sk-x"}}
    r = cliente.put("/api/configuracoes/imagens", json={"provedor": "openai", "provedores": novos, "token": "sk-x"})
    assert r.status_code in (200, 422)
    assert "sk-x" not in r.text
    arquivo = cortes / "imagens-ia.json"
    assert not arquivo.exists() or "sk-x" not in arquivo.read_text("utf-8")
    _fechar(cliente)


@pytest.mark.parametrize("corpo, mensagem", [
    ({"provedor": "dall-e", "provedores": {}}, "Provedor desconhecido: dall-e"),
    ({"provedor": "openai", "provedores": {"openai": {"preco_usd": -1}}}, "Preço de openai não pode ser negativo"),
    ({"provedor": "openai", "provedores": {"openai": {"preco_usd": "caro"}}}, "Preço de openai deve ser um número"),
])
def test_configuracoes_put_invalido(ambiente, corpo, mensagem):
    cortes, _, _ = ambiente
    cliente = _cliente_ia(cortes)
    r = cliente.put("/api/configuracoes/imagens", json=corpo)
    assert r.status_code == 422 and r.json()["detail"] == mensagem
    assert not (cortes / "imagens-ia.json").exists()
    _fechar(cliente)


def test_configuracoes_pedem_sessao_na_rede(ambiente):
    cortes, _, _ = ambiente
    cliente = _cliente_ia(cortes, rede=True, cofre=CofreFalso())
    assert cliente.get("/api/configuracoes/imagens").status_code == 401
    assert cliente.post(_fotos_url()).status_code == 401
    assert cliente.post(_ia_url()).status_code == 401
    _fechar(cliente)


def test_candidata_que_nao_e_dict_nao_derruba_o_get(ambiente):
    cortes, _, trabalho = ambiente
    foto = _foto()
    foto.candidatas = [_candidata(1), "lixo", None]
    _gravar_momentos(trabalho, [foto])
    r = _cliente(cortes).get(_url())
    assert r.status_code == 200
    candidatas = r.json()["momentos"][0]["candidatas"]
    assert len(candidatas) == 3 and candidatas[0]["titulo"] == "File:Foto 1.jpg"
    assert candidatas[1]["titulo"] is None and candidatas[1]["miniatura"] == ""


def test_gravar_travado_da_422_e_apaga_o_temporario(ambiente, monkeypatch):
    from esteira.painel import rotas_imagens

    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    antes = (trabalho / "pedidos.json").read_bytes()

    def travado(origem, destino):
        raise PermissionError("arquivo em uso")

    monkeypatch.setattr(rotas_imagens.os, "replace", travado)
    r = cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": versao, "escolhas": [2]})
    assert r.status_code == 422
    assert r.json()["detail"].startswith("Não consegui gravar o pedidos.json: ")
    assert "arquivo em uso" in r.json()["detail"]
    assert not (trabalho / "pedidos.json.tmp").exists()
    assert (trabalho / "pedidos.json").read_bytes() == antes


# --- imagens no vídeo ------------------------------------------------------------


def _prontas_no_disco(destino, trabalho):
    imagens = destino / IMAGENS_SUGERIDAS
    imagens.mkdir(exist_ok=True)
    for nome in (f"{CHAVE_FOTO}-1.jpg", f"{CHAVE_NOTICIA}.png", f"{CHAVE_IA}-ia-1.jpg", f"{CHAVE_IA}-ia-2.jpg"):
        (imagens / nome).write_bytes(b"x")
    (trabalho / "sugeridas.json").write_text(json.dumps([f"{CHAVE_FOTO}-1.jpg", f"{CHAVE_NOTICIA}.png"]), "utf-8")
    c = _candidata(1)
    credito = {campo: c[campo] for campo in ("autor", "licenca", "pagina", "titulo")}
    (trabalho / "creditos.json").write_text(json.dumps({f"{CHAVE_FOTO}-1.jpg": credito}), "utf-8")
    (trabalho / "ia.json").write_text(json.dumps([
        {"momento": CHAVE_IA, "arquivo": f"{CHAVE_IA}-ia-{v}.jpg", "versao": v, "provedor": "x", "data": "2026-11-09"}
        for v in (1, 2)
    ]), "utf-8")


def test_momentos_traz_no_video_prontas_e_tempo_de_tela(ambiente):
    cortes, destino, trabalho = ambiente
    _prontas_no_disco(destino, trabalho)
    dados = _cliente(cortes).get(_url()).json()
    foto, ia, noticia = (_momento(dados, c) for c in (CHAVE_FOTO, CHAVE_IA, CHAVE_NOTICIA))
    assert (foto["no_video"], foto["prontas"]) == (f"{CHAVE_FOTO}-1.jpg", [f"{CHAVE_FOTO}-1.jpg"])
    assert (foto["inicio_tela"], foto["fim_tela"]) == (12.0, 15.0)
    assert (ia["no_video"], ia["prontas"]) == (f"{CHAVE_IA}-ia-2.jpg", [f"{CHAVE_IA}-ia-2.jpg", f"{CHAVE_IA}-ia-1.jpg"])
    assert noticia["no_video"] == f"{CHAVE_NOTICIA}.png"
    assert dados["no_corte"] == [] and dados["montagem_desatualizada"] is True


def test_momentos_sem_nada_pronto(ambiente):
    cortes, _, _ = ambiente
    dados = _cliente(cortes).get(_url()).json()
    assert _momento(dados, CHAVE_FOTO)["no_video"] is None and _momento(dados, CHAVE_FOTO)["prontas"] == []
    assert dados["montagem_desatualizada"] is False  # corte antigo sem "imagens" no registro e nada pronto


def test_put_no_video_valido_grava(ambiente):
    cortes, destino, trabalho = ambiente
    _prontas_no_disco(destino, trabalho)
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    resposta = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": versao, "no_video": f"{CHAVE_IA}-ia-1.jpg"})
    assert resposta.status_code == 200 and resposta.json()["momento"]["no_video"] == f"{CHAVE_IA}-ia-1.jpg"
    assert ler_pedidos(trabalho)[1].no_video == f"{CHAVE_IA}-ia-1.jpg"
    resposta = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": resposta.json()["versao"], "no_video": ""})
    assert resposta.json()["momento"]["no_video"] == f"{CHAVE_IA}-ia-2.jpg"  # vazio volta ao padrão
    assert ler_pedidos(trabalho)[1].no_video == ""


@pytest.mark.parametrize("arquivo", ["../x.jpg", "sub/x.jpg", f"{CHAVE_FOTO}-1.jpg", "nao-existe.jpg"])
def test_put_no_video_invalido_422(ambiente, arquivo):
    cortes, destino, trabalho = ambiente
    _prontas_no_disco(destino, trabalho)
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    antes = (trabalho / "pedidos.json").read_bytes()
    resposta = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": versao, "no_video": arquivo})
    assert resposta.status_code == 422 and resposta.json()["detail"] == "Essa imagem não está pronta para este momento."
    assert (trabalho / "pedidos.json").read_bytes() == antes


def test_trocar_o_tipo_zera_o_no_video(ambiente):
    cortes, destino, trabalho = ambiente
    _prontas_no_disco(destino, trabalho)
    cliente = _cliente(cortes)
    versao = cliente.get(_url()).json()["versao"]
    versao = cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": versao, "no_video": f"{CHAVE_IA}-ia-1.jpg"}).json()["versao"]
    cliente.put(_url(f"/{CHAVE_IA}"), json={"versao": versao, "tipo": "foto"})
    assert ler_pedidos(trabalho)[1].no_video == ""


def _montar_url() -> str:
    return f"/api/episodios/{quote(NOME)}/cortes/1/montar"


def test_montar_202_e_executa_remontar(ambiente):
    cortes, destino, _ = ambiente
    chamadas = []

    def montar(pasta, numero):
        chamadas.append((pasta.name, numero))
        return "ok com alertas: imagem 0:20 País parado fora do vídeo: IA ainda não gerada"

    cliente = _cliente(cortes, montar=montar)
    try:
        resposta = cliente.post(_montar_url(), json=CONFIRMADO)
        assert resposta.status_code == 202
        assert (resposta.json()["tipo"], resposta.json()["cortes"]) == ("montar", [1])
        pedido = _pedido_pronto(cliente, resposta.json()["id"])
        assert pedido["estado"] == "pronto"
        assert pedido["avisos"] == ["imagem 0:20 País parado fora do vídeo: IA ainda não gerada"]
        assert chamadas == [(NOME, 1)]
    finally:
        _fechar(cliente)


def test_montar_repetido_409(ambiente):
    cortes, _, _ = ambiente
    entrou, solto = threading.Event(), threading.Event()

    def montar(pasta, numero):
        entrou.set()
        assert solto.wait(10)
        return "ok"

    cliente = _cliente(cortes, montar=montar)
    try:
        assert cliente.post(_montar_url(), json=CONFIRMADO).status_code == 202
        assert entrou.wait(10)
        resposta = cliente.post(_montar_url(), json=CONFIRMADO)
        assert resposta.status_code == 409 and resposta.json()["detail"] == "Este corte já está sendo montado."
    finally:
        solto.set()
        _fechar(cliente)


def test_montar_sem_confirmacao_422(ambiente):
    cortes, _, _ = ambiente
    cliente = _cliente(cortes, montar=lambda p, n: pytest.fail("não devia montar"))
    try:
        assert cliente.post(_montar_url()).status_code == 422
        assert cliente.post(_montar_url(), json={"confirmado": False}).status_code == 422
    finally:
        _fechar(cliente)
