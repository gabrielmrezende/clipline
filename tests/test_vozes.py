import json
import sys
import types

import pytest

from esteira import cli, vozes
from esteira.enquadrar import TrechoVoz
from esteira.vozes import ErroVozes, ler_vozes, separar_vozes


def _ffmpeg_falso(monkeypatch):
    chamadas = []

    def falso(args, cwd=None):
        chamadas.append(args)
        # cria o WAV temporário como o ffmpeg faria
        from pathlib import Path
        Path(args[-1]).write_bytes(b"RIFF")

    monkeypatch.setattr(vozes, "executar_ffmpeg", falso)
    return chamadas


def _criar_falso(registro):
    def criar(dispositivo="auto"):
        def pipeline(wav, pessoas):
            registro.append((wav.name, pessoas))
            return [(0.0, 5.0, "SPEAKER_01"), (5.0, 9.0, "SPEAKER_00"), (9.0, 12.0, "SPEAKER_01")]

        return pipeline

    return criar


def test_separar_vozes_grava_e_renomeia(tmp_path, monkeypatch):
    chamadas = _ffmpeg_falso(monkeypatch)
    registro = []
    trechos = separar_vozes(tmp_path / "v.mp4", tmp_path, 2, criar=_criar_falso(registro))
    assert trechos == [TrechoVoz(0.0, 5.0, "V1"), TrechoVoz(5.0, 9.0, "V2"), TrechoVoz(9.0, 12.0, "V1")]
    assert registro == [("audio.wav", 2)]
    assert "16000" in chamadas[0] and "1" in chamadas[0]
    arquivo = tmp_path / "transcricao" / "vozes.json"
    assert json.loads(arquivo.read_text("utf-8"))["trechos"][1] == {"inicio": 5.0, "fim": 9.0, "voz": "V2"}
    assert not list((tmp_path / "transcricao").glob("*.tmp"))
    assert ler_vozes(tmp_path) == trechos


def test_nao_sobrescreve_sem_forcar(tmp_path, monkeypatch):
    _ffmpeg_falso(monkeypatch)
    separar_vozes(tmp_path / "v.mp4", tmp_path, 2, criar=_criar_falso([]))
    with pytest.raises(FileExistsError):
        separar_vozes(tmp_path / "v.mp4", tmp_path, 2, criar=_criar_falso([]))
    assert separar_vozes(tmp_path / "v.mp4", tmp_path, 2, criar=_criar_falso([]), forcar=True)


def test_sem_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(ErroVozes) as erro:
        vozes.criar_pipeline()
    assert "HF_TOKEN não definido" in str(erro.value)


def test_sem_token_nao_vaza_valor(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "")
    with pytest.raises(ErroVozes) as erro:
        vozes.criar_pipeline()
    assert "hf_" not in str(erro.value)


def test_ler_vozes_sem_arquivo(tmp_path):
    with pytest.raises(ErroVozes):
        ler_vozes(tmp_path)


def test_cli_vozes_sem_token_retorna_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    _ffmpeg_falso(monkeypatch)
    assert cli.principal(["vozes", str(tmp_path / "v.mp4"), str(tmp_path), "--pessoas", "3"]) == 1
    saida = capsys.readouterr()
    assert "HF_TOKEN não definido" in saida.out + saida.err
    assert not (tmp_path / "transcricao" / "vozes.json").exists()


def test_cli_vozes_imprime_contagem(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    _ffmpeg_falso(monkeypatch)
    monkeypatch.setattr(vozes, "criar_pipeline", _criar_falso([]))
    assert cli.principal(["vozes", str(tmp_path / "v.mp4"), str(tmp_path), "--pessoas", "2"]) == 0
    assert "2 vozes, 3 trechos" in capsys.readouterr().out


def _modulos_falsos(monkeypatch, pipeline):
    class Pipeline:
        @staticmethod
        def from_pretrained(modelo, use_auth_token=None):
            return pipeline

    torch = types.ModuleType("torch")
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    audio = types.ModuleType("pyannote.audio")
    audio.Pipeline = Pipeline
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "pyannote", types.ModuleType("pyannote"))
    monkeypatch.setitem(sys.modules, "pyannote.audio", audio)


def test_termos_nao_aceitos_erro_orientado(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_SENTINELA")
    _modulos_falsos(monkeypatch, None)
    with pytest.raises(ErroVozes) as erro:
        vozes.criar_pipeline()
    assert "segmentation-3.0" in str(erro.value)
    assert "hf_SENTINELA" not in str(erro.value)


def test_pacote_ausente_erro_orientado(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_SENTINELA")
    monkeypatch.setitem(sys.modules, "pyannote", None)
    with pytest.raises(ErroVozes) as erro:
        vozes.criar_pipeline()
    assert "extra vozes" in str(erro.value)
    assert "hf_SENTINELA" not in str(erro.value)


def test_erro_da_pipeline_em_execucao_vira_erro_vozes(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_SENTINELA")
    _ffmpeg_falso(monkeypatch)

    def criar():
        def pipeline(wav, pessoas):
            raise RuntimeError("CUDA out of memory (token hf_SENTINELA)")

        return pipeline

    with pytest.raises(ErroVozes) as erro:
        separar_vozes(tmp_path / "v.mp4", tmp_path, 2, criar=criar)
    assert "out of memory" in str(erro.value)
    assert "hf_SENTINELA" not in str(erro.value)
    assert not (tmp_path / "transcricao" / "vozes.json").exists()


def test_erro_ao_baixar_o_modelo_vira_erro_vozes(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_SENTINELA")
    _modulos_falsos(monkeypatch, None)

    def quebra(modelo, use_auth_token=None):
        raise OSError(f"401 Client Error para {use_auth_token}")

    monkeypatch.setattr(sys.modules["pyannote.audio"].Pipeline, "from_pretrained", staticmethod(quebra))
    with pytest.raises(ErroVozes) as erro:
        vozes.criar_pipeline()
    assert "401 Client Error" in str(erro.value) and vozes.MODELO in str(erro.value)
    assert "hf_SENTINELA" not in str(erro.value)


def test_cli_vozes_erro_com_prefixo_e_sem_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    monkeypatch.setenv("HF_TOKEN", "hf_SENTINELA")
    _ffmpeg_falso(monkeypatch)

    def criar(dispositivo="auto"):
        def pipeline(wav, pessoas):
            raise RuntimeError("sem memória")

        return pipeline

    monkeypatch.setattr(vozes, "criar_pipeline", criar)
    assert cli.principal(["vozes", str(tmp_path / "v.mp4"), str(tmp_path)]) == 1
    saida = capsys.readouterr()
    assert saida.err.startswith("Erro: ") and "sem memória" in saida.err
    assert "Traceback" not in saida.err and "hf_SENTINELA" not in saida.err


def test_cli_vozes_ja_existe_com_prefixo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    _ffmpeg_falso(monkeypatch)
    monkeypatch.setattr(vozes, "criar_pipeline", _criar_falso([]))
    cli.principal(["vozes", str(tmp_path / "v.mp4"), str(tmp_path)])
    assert cli.principal(["vozes", str(tmp_path / "v.mp4"), str(tmp_path)]) == 1
    assert capsys.readouterr().err.startswith("Erro: Vozes já existem")


def test_cli_vozes_pessoas_padrao_3(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    _ffmpeg_falso(monkeypatch)
    registro = []
    monkeypatch.setattr(vozes, "criar_pipeline", _criar_falso(registro))
    assert cli.principal(["vozes", str(tmp_path / "v.mp4"), str(tmp_path)]) == 0
    assert registro == [("audio.wav", 3)]


@pytest.mark.parametrize("valor", ["0", "-2"])
def test_cli_vozes_recusa_pessoas_nao_positivo(tmp_path, monkeypatch, capsys, valor):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    with pytest.raises(SystemExit) as saida:
        cli.principal(["vozes", str(tmp_path / "v.mp4"), str(tmp_path), "--pessoas", valor])
    assert saida.value.code == 2
    assert "--pessoas" in capsys.readouterr().err


@pytest.mark.parametrize("pedido,tem_gpu,esperado", [
    ("auto", True, "cuda"), ("auto", False, "cpu"), ("cpu", True, "cpu"), ("cpu", False, "cpu"), ("cuda", True, "cuda"),
])
def test_escolher_dispositivo(pedido, tem_gpu, esperado):
    assert vozes.escolher_dispositivo(pedido, tem_gpu) == esperado


def test_cuda_sem_gpu_e_erro_claro():
    with pytest.raises(ErroVozes, match="--dispositivo cpu"):
        vozes.escolher_dispositivo("cuda", False)


class _PipelineFalsa:
    def __init__(self):
        self.destino = None

    def to(self, destino):
        self.destino = destino


def _torch_com_gpu(monkeypatch, tem_gpu: bool):
    torch = sys.modules["torch"]
    torch.cuda = types.SimpleNamespace(is_available=lambda: tem_gpu)
    torch.device = lambda nome: f"device:{nome}"


@pytest.mark.parametrize("pedido,tem_gpu,destino,avisou", [
    ("auto", True, "device:cuda", False),
    ("auto", False, None, True),
    ("cpu", True, None, True),
])
def test_criar_pipeline_respeita_o_dispositivo(monkeypatch, pedido, tem_gpu, destino, avisou):
    monkeypatch.setenv("HF_TOKEN", "hf_SENTINELA")
    pipeline = _PipelineFalsa()
    _modulos_falsos(monkeypatch, pipeline)
    _torch_com_gpu(monkeypatch, tem_gpu)
    avisos = []
    vozes.criar_pipeline(pedido, avisar=avisos.append)
    assert pipeline.destino == destino
    assert bool(avisos) is avisou


def test_cuda_sem_gpu_nao_baixa_o_modelo(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_SENTINELA")
    _modulos_falsos(monkeypatch, _PipelineFalsa())
    _torch_com_gpu(monkeypatch, False)
    baixou = []
    sys.modules["pyannote.audio"].Pipeline.from_pretrained = lambda *a, **k: baixou.append(a)
    with pytest.raises(ErroVozes):
        vozes.criar_pipeline("cuda")
    assert baixou == []


def test_cli_vozes_repassa_o_dispositivo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "garantir_escrita", lambda caminho: caminho)
    _ffmpeg_falso(monkeypatch)
    pedidos = []

    def criar(dispositivo="auto"):
        pedidos.append(dispositivo)
        return _criar_falso([])()

    monkeypatch.setattr(vozes, "criar_pipeline", criar)
    assert cli.principal(["vozes", str(tmp_path / "v.mp4"), str(tmp_path), "--dispositivo", "cpu"]) == 0
    assert cli.principal(["vozes", str(tmp_path / "v.mp4"), str(tmp_path), "--forcar"]) == 0
    assert pedidos == ["cpu", "auto"]
