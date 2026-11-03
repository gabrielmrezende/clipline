import pytest

from esteira import wikimedia
from esteira.wikimedia import buscar_candidatas, licenca_aceita, tamanho, url_final


def _pagina(titulo, indice, licenca="CC BY-SA 4.0", mime="image/jpeg", largura=3000, altura=2000,
            thumb=True, artista="Fulano"):
    info = {
        "mime": mime, "width": largura, "height": altura,
        "extmetadata": {"LicenseShortName": {"value": licenca}, "Artist": {"value": artista}},
    }
    if thumb:
        info["thumburl"] = f"https://u/640px-{titulo}"
    return {"title": titulo, "index": indice, "imageinfo": [info]}


def _resposta(paginas):
    return {"query": {"pages": paginas}}


@pytest.mark.parametrize("nome,aceita", [
    ("CC BY-SA 4.0", True), ("CC BY 2.0", True), ("CC0", True), ("Public domain", True),
    ("PD-US", True), ("CC BY-NC 2.0", False), ("CC BY-NC-SA 4.0", False),
    ("cc-by-nd-3.0", False), ("Fair use", False), ("", False),
])
def test_licenca_aceita(nome, aceita):
    assert licenca_aceita(nome) is aceita


def test_filtra_licenca_formato_e_resolucao():
    paginas = [
        _pagina("File:Ok.jpg", 1),
        _pagina("File:Nc.jpg", 2, licenca="CC BY-NC 2.0"),
        _pagina("File:Vetor.svg", 3, mime="image/svg+xml"),
        _pagina("File:Pequena.jpg", 4, largura=1200, altura=700),
        _pagina("File:SemMiniatura.jpg", 5, thumb=False),
    ]
    assert [c.titulo for c in buscar_candidatas("x", lambda p: _resposta(paginas))] == ["File:Ok.jpg"]


def test_ordem_da_busca_e_limite():
    paginas = [_pagina(f"File:I{i}.jpg", i) for i in range(8, 0, -1)]
    candidatas = buscar_candidatas("x", lambda p: _resposta(paginas))
    assert [c.titulo for c in candidatas][:2] == ["File:I1.jpg", "File:I2.jpg"]
    assert len(candidatas) == 6


def test_autor_sem_html():
    paginas = [_pagina("File:A.jpg", 1, artista='<a href="//x">Fulano  de\nTal</a>')]
    assert buscar_candidatas("x", lambda p: _resposta(paginas))[0].autor == "Fulano de Tal"


def test_autor_vazio_vira_desconhecido():
    paginas = [_pagina("File:A.jpg", 1, artista="")]
    assert buscar_candidatas("x", lambda p: _resposta(paginas))[0].autor == "desconhecido"


def test_candidata_traz_dados_da_pagina():
    paginas = [_pagina("File:Ayrton Senna.jpg", 1)]
    c = buscar_candidatas("x", lambda p: _resposta(paginas))[0]
    assert c.pagina == "https://commons.wikimedia.org/wiki/File:Ayrton_Senna.jpg"
    assert (c.largura, c.altura, c.licenca) == (3000, 2000, "CC BY-SA 4.0")
    assert c.miniatura == "https://u/640px-File:Ayrton Senna.jpg"


def test_busca_sem_resultado():
    assert buscar_candidatas("x", lambda p: {}) == []


def test_consulta_pede_largura_640():
    params = {}

    def falso(p):
        params.update(p)
        return {}

    buscar_candidatas("Senna", falso)
    assert params["iiurlwidth"] == 640 and params["gsrnamespace"] == 6
    assert params["gsrsearch"] == "Senna" and params["gsrlimit"] == 20


def test_url_final_usa_thumburl():
    achou = {"query": {"pages": [{"imageinfo": [{"thumburl": "https://u/1920px-A.jpg", "url": "https://u/A.jpg"}]}]}}
    assert url_final("File:A.jpg", lambda p: achou) == "https://u/1920px-A.jpg"
    assert url_final("File:A.jpg", lambda p: {"query": {"pages": [{"missing": True}]}}) is None


def test_url_final_pede_largura_1920():
    params = {}

    def falso(p):
        params.update(p)
        return {}

    url_final("File:A.jpg", falso)
    assert params["iiurlwidth"] == 1920 and params["titles"] == "File:A.jpg"


class _Resposta:
    headers = {"Content-Length": "1234"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"query": {}}'


def test_consultar_monta_url_da_api(monkeypatch):
    chamadas = []
    monkeypatch.setattr(wikimedia, "abrir", lambda url, metodo="GET": chamadas.append(url) or _Resposta())
    assert wikimedia.consultar({"action": "query"}) == {"query": {}}
    assert chamadas[0].startswith("https://commons.wikimedia.org/w/api.php?")
    assert "format=json" in chamadas[0] and "formatversion=2" in chamadas[0]


def test_tamanho_le_content_length_e_trata_erro(monkeypatch):
    metodos = []
    monkeypatch.setattr(wikimedia, "abrir", lambda url, metodo="GET": metodos.append(metodo) or _Resposta())
    assert tamanho("https://u/a.jpg") == 1234 and metodos == ["HEAD"]

    def falha(url, metodo="GET"):
        raise OSError("sem rede")

    monkeypatch.setattr(wikimedia, "abrir", falha)
    assert tamanho("https://u/a.jpg") is None
