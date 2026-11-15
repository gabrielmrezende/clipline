import json
import sys
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


def test_glossario_inteiro_vai_em_hotwords_e_prompt_nao_corta_nome():
    from esteira.transcrever import LIMITE_PROMPT, opcoes_de_nomes

    nomes = [f"Pessoa Número {i}" for i in range(40)]

    def transcribe(audio, language=None, hotwords=None, initial_prompt=None, **_):
        pass

    opcoes = opcoes_de_nomes(transcribe, nomes)
    assert opcoes["hotwords"] == ", ".join(nomes)
    assert len(opcoes["initial_prompt"]) <= LIMITE_PROMPT
    assert all(parte.strip() in nomes for parte in opcoes["initial_prompt"].split(","))


def test_versao_antiga_sem_hotwords():
    from esteira.transcrever import opcoes_de_nomes

    def transcribe(audio, language=None, initial_prompt=None):
        pass

    assert "hotwords" not in opcoes_de_nomes(transcribe, ["Ana"])
    assert opcoes_de_nomes(transcribe, [])["initial_prompt"] is None


def _sem_chamar():
    raise AssertionError("não devia perguntar pela GPU")


@pytest.mark.parametrize("dispositivo,tem_gpu,primeiro", [
    ("auto", True, ("large-v3", "cuda", "float16")),
    ("auto", False, ("medium", "cpu", "int8")),
    ("cpu", True, ("medium", "cpu", "int8")),
    ("cuda", False, ("large-v3", "cuda", "float16")),  # como sempre: o erro, se houver, vem do CTranslate2
])
def test_escolher_modos(dispositivo, tem_gpu, primeiro):
    from esteira.transcrever import escolher_modos

    assert escolher_modos(dispositivo, lambda: tem_gpu)[0] == primeiro


def test_cpu_e_cuda_explicitos_nao_consultam_a_gpu():
    from esteira.transcrever import MODOS, MODOS_CPU, escolher_modos

    assert escolher_modos("cpu", _sem_chamar) == MODOS_CPU
    assert escolher_modos("cuda", _sem_chamar) == MODOS


def test_dispositivo_desconhecido():
    from esteira.transcrever import escolher_modos

    with pytest.raises(ValueError, match="auto, cuda, cpu"):
        escolher_modos("tpu", lambda: True)


def test_aviso_so_na_cpu():
    from esteira.transcrever import MODOS, MODOS_CPU, aviso_de_dispositivo

    assert aviso_de_dispositivo(MODOS) is None
    assert "CPU" in aviso_de_dispositivo(MODOS_CPU) and "medium" in aviso_de_dispositivo(MODOS_CPU)


def test_na_cpu_carrega_int8_e_recua_para_o_small_sem_memoria(tmp_path):
    from esteira.transcrever import MODOS_CPU

    pedidos = []

    def criar(modo):
        pedidos.append(modo)
        return Modelo([MemoryError()]) if len(pedidos) == 1 else Modelo([SEG])

    assert transcrever(tmp_path / "v.mp4", tmp_path, [], criar, modos=MODOS_CPU)
    assert pedidos == [("medium", "cpu", "int8"), ("small", "cpu", "int8")]


def test_bad_alloc_da_cpu_conta_como_falta_de_memoria(tmp_path):
    from esteira.transcrever import MODOS_CPU

    falha = Modelo([RuntimeError("std::bad_alloc")])
    assert transcrever(tmp_path / "v.mp4", tmp_path, [], fabrica(falha, Modelo([SEG])), modos=MODOS_CPU)


def test_sem_modos_usa_os_de_cuda_como_sempre(tmp_path):
    from esteira.transcrever import MODOS

    pedidos = []

    def criar(modo):
        pedidos.append(modo)
        return Modelo([SEG])

    transcrever(tmp_path / "v.mp4", tmp_path, [], criar)
    assert pedidos == [MODOS[0]]


def test_idioma_vai_para_o_whisper(tmp_path):
    modelo = Modelo([SEG])
    transcrever(tmp_path / "v.mp4", tmp_path, [], fabrica(modelo), idioma="es")
    assert modelo.opcoes["language"] == "es"


def test_cli_transcrever_escolhe_dispositivo_e_idioma(tmp_path, monkeypatch, capsys):
    from esteira import cli, config

    chamada = {}
    monkeypatch.setattr(cli, "criar_episodio", lambda video, quadro, numero, convidado: tmp_path)
    monkeypatch.setattr(cli, "carregar_glossario", lambda caminho: [])
    monkeypatch.setattr(config, "atual", lambda: config.Config(transcricao_idioma="en"))

    def falso(video, pasta, nomes, forcar=False, modos=None, idioma="pt"):
        chamada.update(modos=modos, idioma=idioma)
        return []

    monkeypatch.setattr(cli, "transcrever", falso)
    argv = ["transcrever", str(tmp_path / "v.mp4"), "--quadro", "Q", "--numero", "1", "--convidado", "C"]
    assert cli.principal(argv + ["--dispositivo", "cpu"]) == 0
    assert chamada["modos"][0] == ("medium", "cpu", "int8") and chamada["idioma"] == "en"
    assert "CPU" in capsys.readouterr().out


def test_auto_com_gpu_guarda_a_cpu_de_reserva():
    from esteira.transcrever import MODOS, MODOS_CPU, escolher_modos

    assert escolher_modos("auto", lambda: True) == MODOS + MODOS_CPU


def test_sem_cublas_o_auto_pula_para_a_cpu(tmp_path, capsys):
    from esteira.transcrever import MODOS, MODOS_CPU

    usados = []
    modelos = [Modelo([RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")]), Modelo([SEG])]

    def criar(modo):
        usados.append(modo)
        return modelos.pop(0)

    assert transcrever(tmp_path / "v.mp4", tmp_path, [], criar, modos=MODOS + MODOS_CPU)
    assert usados == [MODOS[0], MODOS_CPU[0]]  # não tenta os outros modos de CUDA
    assert "CPU" in capsys.readouterr().err


def test_sem_cublas_e_cuda_explicito_o_erro_continua(tmp_path):
    from esteira.transcrever import MODOS

    falha = Modelo([RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")])
    with pytest.raises(RuntimeError, match="cublas"):
        transcrever(tmp_path / "v.mp4", tmp_path, [], fabrica(falha), modos=MODOS)


def test_gpu_visivel_sem_cublas_nao_conta_como_cuda(monkeypatch):
    from esteira import transcrever as modulo

    monkeypatch.setattr(modulo, "_cublas_carrega", lambda: False)
    monkeypatch.setitem(sys.modules, "ctranslate2", N(get_cuda_device_count=lambda: 1))
    assert modulo.cuda_disponivel() is False
