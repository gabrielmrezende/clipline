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


def test_consulta_pede_largura_500():
    # 500 é a largura padrão do Wikimedia até 640 px (limite das miniaturas sem confirmação no CLAUDE.md).
    params = {}

    def falso(p):
        params.update(p)
        return {}

    buscar_candidatas("Senna", falso)
    assert params["iiurlwidth"] == 500 and params["gsrnamespace"] == 6
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


def test_autor_desescapa_entidades_html():
    paginas = [_pagina("File:A.jpg", 1, artista="Tom &amp; Jerry&#160;Silva")]
    assert buscar_candidatas("x", lambda p: _resposta(paginas))[0].autor == "Tom & Jerry Silva"


def test_consultar_levanta_valueerror_com_chave_error(monkeypatch):
    class Erro(_Resposta):
        def read(self):
            return b'{"error": {"code": "badvalue", "info": "devagar"}}'

    monkeypatch.setattr(wikimedia, "abrir", lambda url, metodo="GET": Erro())
    with pytest.raises(ValueError, match="Wikimedia: badvalue: devagar"):
        wikimedia.consultar({"action": "query"})


def test_consultar_espaca_consultas_seguidas(monkeypatch):
    relogio = [100.0]
    esperas = []
    monkeypatch.setattr(wikimedia.time, "monotonic", lambda: relogio[0])
    monkeypatch.setattr(wikimedia.time, "sleep", lambda s: esperas.append(s) or relogio.__setitem__(0, relogio[0] + s))
    monkeypatch.setattr(wikimedia, "_ultima_consulta", 0.0)
    monkeypatch.setattr(wikimedia, "abrir", lambda url, metodo="GET": _Resposta())
    wikimedia.consultar({"action": "query"})
    relogio[0] += 0.3
    wikimedia.consultar({"action": "query"})
    assert esperas[0] == 0.0
    assert esperas[1] == pytest.approx(wikimedia.INTERVALO_CONSULTAS - 0.3)


def test_consultar_repete_quando_busca_esta_ocupada(monkeypatch):
    class Ocupada(_Resposta):
        def read(self):
            return b'{"error": {"code": "cirrussearch-too-busy-error", "info": "ocupada"}}'

    respostas = [Ocupada(), Ocupada(), _Resposta()]
    esperas = []
    monkeypatch.setattr(wikimedia.time, "sleep", esperas.append)
    monkeypatch.setattr(wikimedia, "abrir", lambda url, metodo="GET": respostas.pop(0))
    assert wikimedia.consultar({"action": "query"}) == {"query": {}}
    assert [e for e in esperas if e >= wikimedia.ESPERA_OCUPADA] == [wikimedia.ESPERA_OCUPADA, 2 * wikimedia.ESPERA_OCUPADA]


def test_consultar_desiste_se_busca_continua_ocupada(monkeypatch):
    class Ocupada(_Resposta):
        def read(self):
            return b'{"error": {"code": "cirrussearch-too-busy-error", "info": "ocupada"}}'

    monkeypatch.setattr(wikimedia.time, "sleep", lambda s: None)
    monkeypatch.setattr(wikimedia, "abrir", lambda url, metodo="GET": Ocupada())
    with pytest.raises(ValueError, match="too-busy"):
        wikimedia.consultar({"action": "query"})


@pytest.mark.parametrize("nome,tipo", [
    ("CC0", "cc0"), ("Public domain", "dominio-publico"), ("PD-US", "dominio-publico"), ("CC BY 2.0", "cc-by"),
    ("CC BY-SA 4.0", "cc-by-sa"), ("CC-BY-SA-3.0", "cc-by-sa"), ("CC BY-NC-SA 4.0", None), ("Fair use", None),
])
def test_tipo_de_licenca(nome, tipo):
    assert wikimedia.tipo_de_licenca(nome) == tipo


def test_lista_de_licencas_explicita():
    assert licenca_aceita("CC BY-SA 4.0", ("cc0", "dominio-publico", "cc-by")) is False
    assert licenca_aceita("CC BY 4.0", ("cc0", "dominio-publico", "cc-by")) is True
    assert licenca_aceita("CC0", ("cc-by-sa",)) is False


def test_busca_usa_as_licencas_do_clipline_toml(monkeypatch):
    from esteira import config

    paginas = [_pagina("File:Sa.jpg", 1), _pagina("File:By.jpg", 2, licenca="CC BY 4.0"),
               _pagina("File:Zero.jpg", 3, licenca="CC0")]
    todas = buscar_candidatas("x", lambda p: _resposta(paginas))
    assert [c.titulo for c in todas] == ["File:Sa.jpg", "File:By.jpg", "File:Zero.jpg"]  # padrão: como sempre
    monkeypatch.setattr(config, "atual", lambda: config.Config(imagens_licencas=("cc0", "cc-by")))
    assert [c.titulo for c in buscar_candidatas("x", lambda p: _resposta(paginas))] == ["File:By.jpg", "File:Zero.jpg"]
    so_zero = buscar_candidatas("x", lambda p: _resposta(paginas), aceitas=("cc0",))
    assert [c.titulo for c in so_zero] == ["File:Zero.jpg"]


def test_aviso_compartilha_igual_so_com_foto_cc_by_sa():
    by = {"autor": "Fulano", "licenca": "CC BY 4.0", "pagina": "https://c/A1"}
    sa = {"autor": "Beltrana", "licenca": "CC BY-SA 4.0", "pagina": "https://c/A2"}
    assert wikimedia.aviso_compartilha_igual([by]) is None
    assert wikimedia.aviso_compartilha_igual([]) is None
    aviso = wikimedia.aviso_compartilha_igual([by, sa])
    assert "CC BY-SA" in aviso and "mesma licença" in aviso


def _momento_com_fotos(tmp_path, licencas):
    from esteira.pedidos import Momento

    candidatas = [{"titulo": f"File:A{i}.jpg", "pagina": f"https://c/A{i}", "autor": f"Autor{i}", "licenca": licenca}
                  for i, licenca in enumerate(licencas, 1)]
    m = Momento(12.0, 15.0, "fala", "foto", "Yas Marina", busca="x", candidatas=candidatas,
                escolhas=list(range(1, len(licencas) + 1)))
    nomes = [f"0012-yas-marina-{k}.jpg" for k in range(1, len(licencas) + 1)]
    for nome in nomes:
        (tmp_path / nome).write_bytes(b"jpg")
    return m, set(nomes)


def test_guia_traz_o_aviso_depois_dos_creditos_cc_by_sa(tmp_path):
    from esteira.fluxo_imagens import _bloco_guia

    m, geradas = _momento_com_fotos(tmp_path, ["CC BY 4.0", "CC BY-SA 4.0"])
    linhas = _bloco_guia(tmp_path, m, "0012-yas-marina", geradas, [], {}).splitlines()
    i = linhas.index("Créditos:")
    assert linhas[i + 1:] == [
        "1. Autor1, CC BY 4.0, https://c/A1",
        "2. Autor2, CC BY-SA 4.0, https://c/A2",
        wikimedia.AVISO_COMPARTILHA_IGUAL,
    ]


def test_guia_sem_cc_by_sa_fica_como_sempre(tmp_path):
    from esteira.fluxo_imagens import _bloco_guia

    m, geradas = _momento_com_fotos(tmp_path, ["CC BY 4.0", "CC0"])
    texto = _bloco_guia(tmp_path, m, "0012-yas-marina", geradas, [], {})
    assert texto.endswith("Créditos:\n1. Autor1, CC BY 4.0, https://c/A1\n2. Autor2, CC0, https://c/A2")


def test_resumo_da_publicacao_traz_o_aviso(tmp_path):
    from esteira.publicar.agendar import _creditos_das_fotos

    sa = {"autor": "F", "licenca": "CC BY-SA 4.0", "pagina": "p"}
    zero = {"autor": "B", "licenca": "CC0", "pagina": "q"}
    imagens = [
        {"tipo": "foto", "arquivo": "imagens-sugeridas/a-1.jpg", "credito": sa},
        {"tipo": "foto", "arquivo": "imagens-sugeridas/b-1.jpg", "credito": zero},
    ]
    esperado = ["- F, CC BY-SA 4.0, p", "- B, CC0, q", wikimedia.AVISO_COMPARTILHA_IGUAL]
    assert _creditos_das_fotos(tmp_path, imagens) == esperado
    assert _creditos_das_fotos(tmp_path, imagens[1:]) == ["- B, CC0, q"]
