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
    def criar():
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
