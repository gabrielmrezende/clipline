"""Travas do agente com a pasta de programas do clipline.toml e o próprio clipline.toml."""

import importlib.util
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "travas.py"


def _travas():
    """Uma cópia nova do hook por teste: proteger_pasta_de_programas mexe nas listas do módulo."""
    spec = importlib.util.spec_from_file_location("travas_canal", HOOK)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _bash(comando: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": comando}}


def _escrever(caminho: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": caminho}}


def test_le_a_pasta_de_programas_do_toml(tmp_path):
    travas = _travas()
    arquivo = tmp_path / "clipline.toml"
    assert travas.pasta_de_programas_configurada(arquivo) is None  # sem arquivo
    arquivo.write_text('[pastas]\nprogramas = "Gravações/Episódios"\n', "utf-8")
    assert travas.pasta_de_programas_configurada(arquivo) == "Episódios"
    arquivo.write_text('[pastas]\nprogramas = "1 - Programas"\n', "utf-8")
    assert travas.pasta_de_programas_configurada(arquivo) is None  # o padrão já está nas listas
    arquivo.write_text("[pastas\n", "utf-8")
    assert travas.pasta_de_programas_configurada(arquivo) is None


def test_pasta_de_programas_configurada_fica_so_leitura():
    travas = _travas()
    assert travas.decidir(_bash('Remove-Item "..\\Episódios (2026)\\ep.mp4"')) is None
    travas.proteger_pasta_de_programas("Episódios (2026)")
    assert "só leitura" in travas.decidir(_bash('Remove-Item "..\\Episódios (2026)\\ep.mp4"'))
    assert "só leitura" in travas.decidir(_escrever("C:/Canal/Episódios (2026)/ep.mp4"))
    assert travas.decidir(_bash('ls "../Episódios (2026)"')) is None
    assert travas.decidir(_escrever("C:/Canal/2 - Cortes/ep/aprovados.json")) is None


def test_clipline_toml_e_do_dono():
    travas = _travas()
    assert "do dono" in travas.decidir(_escrever("C:/Canal/Automacao/clipline.toml"))
    assert travas.decidir(_escrever("C:/Canal/Automacao/clipline.exemplo.toml")) is None
