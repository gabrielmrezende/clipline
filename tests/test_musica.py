import json

from esteira import cli
from esteira.midia import executar_ffmpeg, pico_de_audio
from esteira.musica import (
    CLIMAS_VALIDOS, Faixa, baixar_musicas, clima_da_faixa, credito, escolher_musica, escrever_proposta,
    gravar_uso, ler_catalogo, ler_uso, propor,
)

PECAS = [
    {"title": "Alegre", "filename": "Alegre.mp3", "length": "00:02:30", "feel": "Bright, Bouncy", "instruments": "Piano, Guitar", "description": "x"},
    {"title": "Terror", "filename": "Terror.mp3", "length": "00:02:30", "feel": "Suspenseful, Eerie", "instruments": "Synth", "description": "x"},
    {"title": "Curta", "filename": "Curta.mp3", "length": "00:01:00", "feel": "Calming", "instruments": "Piano", "description": "x"},
    {"title": "Coro", "filename": "Coro.mp3", "length": "00:03:00", "feel": "Uplifting", "instruments": "Choir, Strings", "description": "x"},
    {"title": "Calma", "filename": "Calma.mp3", "length": "00:03:00", "feel": "Relaxed", "instruments": "Piano", "description": "x"},
]


def _peca(titulo, instrumentos, feel="Bright"):
    return {"title": titulo, "filename": f"{titulo}.mp3", "length": "00:02:30", "feel": feel, "instruments": instrumentos, "description": "x"}


def test_climas_validos():
    assert CLIMAS_VALIDOS == ("leve", "tenso", "inspirador", "reflexivo")


def test_clima_da_faixa():
    assert [clima_da_faixa(p) for p in PECAS] == ["leve", None, None, None, "reflexivo"]


def test_clima_da_faixa_sem_feel_ou_instrumentos():
    assert clima_da_faixa({"title": "X", "filename": "X.mp3", "length": "00:02:30"}) is None
    sem_instrumentos = {"title": "X", "filename": "X.mp3", "length": "00:02:30", "feel": "Bright"}
    assert clima_da_faixa(sem_instrumentos) == "leve"


def test_clima_da_faixa_limites_de_duracao():
    base = _peca("X", "Piano")
    assert clima_da_faixa({**base, "length": "00:01:30"}) == "leve"
    assert clima_da_faixa({**base, "length": "00:06:00"}) == "leve"
    assert clima_da_faixa({**base, "length": "00:01:29"}) is None
    assert clima_da_faixa({**base, "length": "00:06:01"}) is None


def test_propor_limita_e_prefere_instrumentacao_leve():
    pesadas = [_peca(f"A{n:02d}", "Drums, Brass") for n in range(6)]
    leves = [_peca(f"B{n:02d}", "Piano") for n in range(6)]
    selecao = propor(pesadas + leves, por_clima=10)
    titulos = [p["title"] for p in selecao["leve"]]
    assert len(titulos) == 10
    assert titulos[:6] == [f"B{n:02d}" for n in range(6)]
    assert selecao["tenso"] == []


def test_propor_cada_peca_em_um_so_clima():
    ambigua = _peca("Mista", "Piano", feel="Bright, Calming")
    selecao = propor([ambigua])
    assert [p["title"] for p in selecao["leve"]] == ["Mista"]
    assert selecao["reflexivo"] == []


def test_escrever_proposta_grava_md_e_aprovadas(tmp_path):
    pecas = [PECAS[0], PECAS[4]]
    pecas.append({**_peca("Clean Soul", "Piano", feel="Uplifting"), "filename": "Clean Soul.mp3", "description": "Suave"})
    escrever_proposta(propor(pecas), tmp_path)
    aprovadas = json.loads((tmp_path / "aprovadas.json").read_text("utf-8"))
    assert aprovadas == {"leve": ["Alegre.mp3"], "tenso": [], "inspirador": ["Clean Soul.mp3"], "reflexivo": ["Calma.mp3"]}
    texto = (tmp_path / "proposta.md").read_text("utf-8")
    assert "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Clean%20Soul.mp3" in texto
    assert "Alegre" in texto and "Piano, Guitar" in texto and "00:02:30" in texto


def test_cli_musicas_propor(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "MUSICAS", tmp_path)
    monkeypatch.setattr(cli, "baixar_catalogo", lambda: PECAS)
    assert cli.principal(["musicas", "propor"]) == 0
    assert (tmp_path / "proposta.md").exists()
    assert json.loads((tmp_path / "aprovadas.json").read_text("utf-8"))["leve"] == ["Alegre.mp3"]


def _tom(destino, db=-12.0, segundos=5):
    executar_ffmpeg([
        "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}",
        "-af", f"volume={db}dB", "-c:a", "libmp3lame", "-f", "mp3", str(destino),
    ])


def _baixar_falso(urls=None, db=-12.0, falhar=()):
    def baixar(url, destino):
        if urls is not None:
            urls.append(url)
        if any(nome in url for nome in falhar):
            raise OSError("sem rede")
        _tom(destino, db)

    return baixar


def _aprovar(pasta, aprovadas):
    base = {clima: [] for clima in CLIMAS_VALIDOS}
    (pasta / "aprovadas.json").write_text(json.dumps({**base, **aprovadas}), "utf-8")


def test_credito_exato():
    assert credito("Carefree") == "Música: Carefree — Kevin MacLeod (incompetech.com), licença CC BY 4.0"


def test_baixar_normaliza_e_cataloga(tmp_path):
    _aprovar(tmp_path, {"leve": ["Alegre.mp3"]})
    erros = baixar_musicas(tmp_path, PECAS, _baixar_falso())
    assert erros == []
    catalogo = ler_catalogo(tmp_path)
    assert len(catalogo) == 1
    faixa = catalogo[0]
    assert (faixa.titulo, faixa.clima, faixa.arquivo, faixa.credito) == ("Alegre", "leve", "leve/Alegre.mp3", credito("Alegre"))
    assert abs(faixa.duracao - 5.0) < 0.5
    assert (tmp_path / "leve" / "Alegre.mp3").exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_url_com_espaco(tmp_path):
    _aprovar(tmp_path, {"inspirador": ["Clean Soul.mp3"]})
    pecas = [{**_peca("Clean Soul", "Piano", feel="Uplifting"), "filename": "Clean Soul.mp3"}]
    urls = []
    assert baixar_musicas(tmp_path, pecas, _baixar_falso(urls)) == []
    assert urls == ["https://incompetech.com/music/royalty-free/mp3-royaltyfree/Clean%20Soul.mp3"]
    assert (tmp_path / "inspirador" / "Clean Soul.mp3").exists()


def test_falha_em_uma_faixa_nao_para_as_outras(tmp_path):
    _aprovar(tmp_path, {"leve": ["Alegre.mp3"], "reflexivo": ["Calma.mp3"]})
    erros = baixar_musicas(tmp_path, PECAS, _baixar_falso(falhar=("Alegre",)))
    assert len(erros) == 1 and erros[0].startswith("falha em Alegre.mp3: ")
    assert [f.arquivo for f in ler_catalogo(tmp_path)] == ["reflexivo/Calma.mp3"]
    assert not (tmp_path / "leve" / "Alegre.mp3").exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_faixa_ja_catalogada_nao_baixa_de_novo(tmp_path):
    _aprovar(tmp_path, {"leve": ["Alegre.mp3"]})
    baixar_musicas(tmp_path, PECAS, _baixar_falso())
    urls = []
    assert baixar_musicas(tmp_path, PECAS, _baixar_falso(urls)) == []
    assert urls == []
    assert len(ler_catalogo(tmp_path)) == 1


def test_catalogo_ausente_e_ordem(tmp_path):
    assert ler_catalogo(tmp_path) == []
    _aprovar(tmp_path, {"leve": ["Alegre.mp3"], "reflexivo": ["Calma.mp3"]})
    baixar_musicas(tmp_path, PECAS, _baixar_falso())
    assert [f.clima for f in ler_catalogo(tmp_path)] == ["leve", "reflexivo"]


def test_volume_normalizado(tmp_path):
    _aprovar(tmp_path, {"leve": ["Alegre.mp3"], "reflexivo": ["Calma.mp3"]})
    baixar_musicas(tmp_path, PECAS, lambda url, destino: _tom(destino, -30.0 if "Alegre" in url else -6.0))
    picos = [pico_de_audio(tmp_path / f.arquivo) for f in ler_catalogo(tmp_path)]
    assert abs(picos[0] - picos[1]) < 3


def test_cli_musicas_baixar(tmp_path, monkeypatch, capsys):
    _aprovar(tmp_path, {"leve": ["Alegre.mp3"]})
    monkeypatch.setattr(cli, "MUSICAS", tmp_path)
    monkeypatch.setattr(cli, "baixar_catalogo", lambda: PECAS)
    monkeypatch.setattr(cli, "baixar_url", _baixar_falso())
    assert cli.principal(["musicas", "baixar"]) == 0
    assert "1 faixas no catálogo" in capsys.readouterr().out


def _faixa(titulo, clima="leve", duracao=200.0):
    return Faixa(titulo, clima, duracao, f"{clima}/{titulo}.mp3", credito(titulo))


def _uso(*arquivos, dia=1):
    return {
        f"ep/{n:02d}": {"arquivo": arquivo, "data": f"2026-10-{dia + n:02d}T10:00:00"}
        for n, arquivo in enumerate(arquivos)
    }


def test_escolhe_do_clima_e_prefere_mais_longa():
    catalogo = [_faixa("Tenso", "tenso"), _faixa("Curta", duracao=60.0), _faixa("Longa", duracao=200.0)]
    assert escolher_musica("leve", catalogo, {}, 90.0, "ep/novo").titulo == "Longa"
    assert escolher_musica("leve", catalogo[:2], {}, 90.0, "ep/novo").titulo == "Curta"


def test_prefere_a_ha_mais_tempo_sem_uso():
    catalogo = [_faixa(t) for t in "ABCDEFGHIJKL"]
    uso = _uso(*(f"leve/{t}.mp3" for t in "ABCDEFGHIJ"))
    uso["ep/velho"] = {"arquivo": "leve/L.mp3", "data": "2026-01-01T10:00:00"}
    assert escolher_musica("leve", catalogo, uso, 90.0, "ep/novo").titulo == "K"


def test_evita_as_ultimas_dez():
    catalogo = [_faixa(t) for t in "ABCDEFGHIJKL"]
    uso = _uso(*(f"leve/{t}.mp3" for t in "ABCDEFGHIJK"))
    assert escolher_musica("leve", catalogo, uso, 90.0, "ep/novo").titulo == "L"
    uso.pop("ep/10")
    uso["ep/antigo"] = {"arquivo": "leve/K.mp3", "data": "2026-01-01T10:00:00"}
    assert escolher_musica("leve", catalogo, uso, 90.0, "ep/novo").titulo == "L"
    uso["ep/zz"] = {"arquivo": "leve/L.mp3", "data": "2026-12-01T10:00:00"}
    assert escolher_musica("leve", catalogo, uso, 90.0, "ep/novo").titulo == "K"


def test_todas_recentes_volta_a_menos_recente():
    catalogo = [_faixa(t) for t in "ABC"]
    uso = _uso("leve/B.mp3", "leve/C.mp3", "leve/A.mp3", "leve/B.mp3")
    assert escolher_musica("leve", catalogo, uso, 90.0, "ep/novo").titulo == "C"


def test_mesmo_corte_de_novo_mantem_a_faixa():
    catalogo = [_faixa(t) for t in "AB"]
    primeira = escolher_musica("leve", catalogo, {}, 90.0, "ep/01")
    uso = {"ep/01": {"arquivo": primeira.arquivo, "data": "2026-11-02T10:00:00"}}
    assert escolher_musica("leve", catalogo, uso, 90.0, "ep/01") == primeira
    assert escolher_musica("leve", catalogo, uso, 90.0, "ep/02") != primeira


def test_clima_sem_faixas_retorna_none():
    assert escolher_musica("tenso", [_faixa("A")], {}, 90.0, "ep/01") is None
    assert escolher_musica("leve", [], {}, 90.0, "ep/01") is None


def test_uso_ida_e_volta(tmp_path):
    assert ler_uso(tmp_path / "nada") == {}
    uso = _uso("leve/Á b.mp3")
    gravar_uso(tmp_path / "musicas", uso)
    assert ler_uso(tmp_path / "musicas") == uso


def test_rodizio_com_datas_iguais():
    catalogo = [_faixa(t) for t in "ABCDE"]
    uso: dict[str, dict] = {}
    escolhidas = []
    for n in range(8):
        faixa = escolher_musica("leve", catalogo, uso, 90.0, f"ep/{n:02d}")
        uso[f"ep/{n:02d}"] = {"arquivo": faixa.arquivo, "data": "2026-11-02T10:00:00"}
        escolhidas.append(faixa.titulo)
    assert escolhidas == ["A", "B", "C", "D", "E", "A", "B", "C"]
