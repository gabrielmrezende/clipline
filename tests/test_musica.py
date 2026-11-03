import json

from esteira import cli
from esteira.musica import CLIMAS_VALIDOS, clima_da_faixa, escrever_proposta, propor

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
