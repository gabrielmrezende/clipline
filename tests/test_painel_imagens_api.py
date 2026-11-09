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
        "640px-Foto_1.jpg", "640px-Foto_2.jpg", "640px-Foto_3.jpg",
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


def test_get_sem_pedidos_e_ilegivel(ambiente):
    cortes, _, trabalho = ambiente
    cliente = _cliente(cortes)
    (trabalho / "pedidos.json").write_text("{ruim", "utf-8")
    resposta = cliente.get(_url())
    assert resposta.status_code == 422
    assert resposta.json()["detail"].startswith("pedidos.json ilegível: ")
    (trabalho / "pedidos.json").unlink()
    assert cliente.get(_url()).json() == {"versao": "", "momentos": []}


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
    r = cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"busca": "outra"})
    assert r.status_code == 409 and r.json() == {"detail": "Espere o download das fotos terminar."}
    assert (trabalho / "pedidos.json").read_bytes() == antes


def test_buscar_troca_candidatas_e_zera_escolhas(ambiente):
    cortes, _, trabalho = ambiente
    pedidas = []

    def falsa(busca):
        pedidas.append(busca)
        return [Candidata("File:Nova.jpg", "https://p", "https://x/thumb/1000px-Nova.jpg", 2000, 1500, "Eu", "CC0")]

    cliente = _cliente(cortes, buscar_candidatas=falsa)
    r = cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"busca": "  planalto  "})
    assert r.status_code == 200
    corpo = r.json()
    assert pedidas == ["planalto"]
    momento = corpo["momento"]
    assert momento["busca"] == "planalto" and momento["escolhas"] == []
    assert [c["titulo"] for c in momento["candidatas"]] == ["File:Nova.jpg"]
    assert momento["candidatas"][0]["miniatura"].endswith("/640px-Nova.jpg")
    gravado = ler_pedidos(trabalho)[0]
    assert gravado.escolhas == [] and gravado.url == [] and gravado.bytes == [] and gravado.resumidas == []
    assert gravado.candidatas[0]["titulo"] == "File:Nova.jpg"
    assert corpo["versao"] == cliente.get(_url()).json()["versao"]


def test_buscar_erros(ambiente):
    cortes, _, _ = ambiente

    def cai(busca):
        raise OSError("sem internet")

    cliente = _cliente(cortes, buscar_candidatas=cai)
    r = cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"busca": "  "})
    assert r.status_code == 422 and r.json()["detail"] == "Escreva o que buscar."
    r = cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"busca": "x"})
    assert r.status_code == 422 and r.json()["detail"] == "Não consegui buscar no Wikimedia: sem internet"
    r = cliente.post(_url(f"/{CHAVE_IA}/buscar"), json={"busca": "x"})
    assert r.status_code == 422 and r.json()["detail"] == "Só momentos de foto buscam no Wikimedia."
    assert cliente.post(_url("/9999-nada/buscar"), json={"busca": "x"}).status_code == 404


def test_rede_sem_cookie_da_401(ambiente):
    cortes, _, _ = ambiente
    cliente = _cliente(cortes, rede=True, cofre=CofreFalso())
    assert cliente.get(_url()).status_code == 401
    assert cliente.put(_url(f"/{CHAVE_FOTO}"), json={"versao": ""}).status_code == 401
    assert cliente.post(_url(f"/{CHAVE_FOTO}/buscar"), json={"busca": "x"}).status_code == 401
