import json
import weakref
from types import SimpleNamespace as N

import pytest

from esteira.modelos import Palavra
from esteira.transcrever import carregar_glossario, ler_palavras, transcrever

SEG = N(words=[N(word=" Olá", start=1.0, end=1.4), N(word=" Brasil.", start=1.4, end=2.0)])


class Modelo:
    def __init__(self, segmentos):
        self.segmentos = segmentos

    def transcribe(self, video, **opcoes):
        self.opcoes = opcoes

        def gerar():
            for s in self.segmentos:
                if isinstance(s, Exception):
                    raise s
                yield s

        return gerar(), None


def fabrica(*modelos):
    fila = list(modelos)
    return lambda modo: fila.pop(0)


def test_grava_palavras_e_texto(tmp_path):
    palavras = transcrever(tmp_path / "v.mp4", tmp_path, ["Gripen"], fabrica(Modelo([SEG])))
    assert palavras == [Palavra("Olá", 1.0, 1.4), Palavra("Brasil.", 1.4, 2.0)]
    assert ler_palavras(tmp_path) == palavras
    assert "[00:00:01] Olá Brasil." in (tmp_path / "transcricao" / "texto.md").read_text("utf-8")


def test_nomes_viram_prompt_inicial(tmp_path):
    modelo = Modelo([SEG])
    transcrever(tmp_path / "v.mp4", tmp_path, ["Gripen", "Embraer"], fabrica(modelo))
    assert modelo.opcoes["initial_prompt"] == "Gripen, Embraer"
    assert modelo.opcoes["language"] == "pt"
    assert modelo.opcoes["word_timestamps"] is True


def test_oom_na_iteracao_repete_mais_leve_desde_o_inicio(tmp_path):
    outro = N(words=[N(word=" Certo.", start=0.0, end=0.5)])
    falha = Modelo([SEG, RuntimeError("CUDA failed: out of memory")])
    palavras = transcrever(tmp_path / "v.mp4", tmp_path, [], fabrica(falha, Modelo([outro])))
    assert [p.texto for p in palavras] == ["Certo."]


def test_libera_modelo_antes_de_carregar_o_proximo(tmp_path):
    vivo = []

    def criar(modo):
        if not vivo:
            modelo = Modelo([RuntimeError("out of memory")])
            vivo.append(weakref.ref(modelo))
            return modelo
        assert vivo[0]() is None
        return Modelo([SEG])

    assert transcrever(tmp_path / "v.mp4", tmp_path, [], criar)


def test_erro_de_alocacao_cublas_tenta_modo_leve(tmp_path):
    falha = Modelo([RuntimeError("cuDNN failed: CUDNN_STATUS_ALLOC_FAILED")])
    assert transcrever(tmp_path / "v.mp4", tmp_path, [], fabrica(falha, Modelo([SEG])))


def test_falha_total_nao_deixa_saida(tmp_path):
    oom = lambda: Modelo([RuntimeError("out of memory")])
    with pytest.raises(RuntimeError):
        transcrever(tmp_path / "v.mp4", tmp_path, [], fabrica(oom(), oom(), oom()))
    assert not (tmp_path / "transcricao" / "palavras.json").exists()


def test_outro_erro_nao_tenta_modo_leve(tmp_path):
    with pytest.raises(ValueError):
        transcrever(tmp_path / "v.mp4", tmp_path, [], fabrica(Modelo([ValueError("x")])))


def test_nao_sobrescreve_sem_forcar(tmp_path):
    transcrever(tmp_path / "v.mp4", tmp_path, [], fabrica(Modelo([SEG])))
    with pytest.raises(FileExistsError):
        transcrever(tmp_path / "v.mp4", tmp_path, [], fabrica(Modelo([SEG])))


def test_palavras_json_guarda_tempos(tmp_path):
    transcrever(tmp_path / "v.mp4", tmp_path, [], fabrica(Modelo([SEG])))
    dados = json.loads((tmp_path / "transcricao" / "palavras.json").read_text("utf-8"))
    assert dados[0] == {"texto": "Olá", "inicio": 1.0, "fim": 1.4}


def test_glossario_extrai_nomes(tmp_path):
    g = tmp_path / "g.md"
    g.write_text(
        "# Glossário\n\nGrafias corretas de nomes.\n\n## Convidados\nPio Pacelli, Juliano Viegas\n\n"
        "Os apresentadores também foram convidados do Por Trás do TCC.\n\n## Defesa\nGripen, Embraer,\nA-29\n",
        "utf-8",
    )
    assert carregar_glossario(g) == ["Pio Pacelli", "Juliano Viegas", "Gripen", "Embraer", "A-29"]
