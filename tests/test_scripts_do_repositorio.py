"""Scripts de instalação e da imagem Docker (scripts/): dependências em CPU, painel no contêiner e sintaxe."""

import importlib.util
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"scripts_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_requisitos_cpu_tira_cuda_e_troca_o_opencv():
    requisitos = _carregar("requisitos_cpu")
    projeto = {
        "dependencies": ["faster-whisper", "opencv-python>=4", "nvidia-cublas-cu12; platform_system != 'Darwin'", "keyring"],
        "optional-dependencies": {"painel": ["fastapi>=0.162"], "dev": ["pytest"]},
    }
    assert requisitos.requisitos_cpu(projeto, ["painel"]) == [
        "faster-whisper", "opencv-python-headless>=4", "keyring", "fastapi>=0.162",
    ]


def test_requisitos_cpu_recusa_extra_desconhecido():
    requisitos = _carregar("requisitos_cpu")
    with pytest.raises(SystemExit, match="Extra desconhecido: gpu"):
        requisitos.requisitos_cpu({"dependencies": [], "optional-dependencies": {"painel": []}}, ["gpu"])


def test_requisitos_cpu_do_pyproject_de_verdade():
    requisitos = _carregar("requisitos_cpu")
    projeto = tomllib.loads(requisitos.PYPROJECT.read_text("utf-8"))["project"]
    nomes = {requisitos.nome(r) for r in requisitos.requisitos_cpu(projeto, ["painel"])}
    assert not any(n.startswith("nvidia-") for n in nomes)
    assert "opencv-python" not in nomes
    assert {"opencv-python-headless", "faster-whisper", "fastapi", "uvicorn"} <= nomes


def test_painel_do_conteiner_recusa_rodar_fora_dele(monkeypatch, capsys):
    painel = _carregar("painel_conteiner")
    monkeypatch.setattr(painel, "dentro_de_conteiner", lambda: False)
    assert painel.principal([]) == 2
    assert "python -m esteira painel" in capsys.readouterr().err


def test_painel_do_conteiner_escuta_em_todas_as_interfaces(monkeypatch):
    uvicorn = pytest.importorskip("uvicorn")
    painel = _carregar("painel_conteiner")
    # registra o __init__ original para o monkeypatch devolvê-lo no fim do teste
    monkeypatch.setattr(uvicorn.Config, "__init__", uvicorn.Config.__init__)
    painel.escutar_em_todas_as_interfaces()
    assert uvicorn.Config(app=None, host="127.0.0.1", port=8765).host == "0.0.0.0"


def test_instalar_sh_tem_sintaxe_valida():
    bash = shutil.which("bash")
    if bash is None or Path(bash).parent.name.lower() == "system32":  # o bash.exe do System32 é o do WSL
        pytest.skip("sem bash")
    saida = subprocess.run([bash, "-n", str(SCRIPTS / "instalar.sh")], capture_output=True, text=True)
    assert saida.returncode == 0, saida.stderr


def test_instalar_ps1_tem_sintaxe_valida():
    powershell = shutil.which("pwsh") or (shutil.which("powershell") if sys.platform == "win32" else None)
    if powershell is None:
        pytest.skip("sem PowerShell")
    comando = (
        "$erros = $null; [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{SCRIPTS / 'instalar.ps1'}', [ref]$null, [ref]$erros) | Out-Null; "
        "$erros | ForEach-Object { $_.ToString() }; exit $erros.Count"
    )
    saida = subprocess.run([powershell, "-NoProfile", "-Command", comando], capture_output=True, text=True)
    assert saida.returncode == 0, saida.stdout + saida.stderr


def test_citation_cff_acompanha_a_versao_do_pyproject():
    raiz = SCRIPTS.parent
    versao = tomllib.loads((raiz / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    linhas = (raiz / "CITATION.cff").read_text("utf-8").splitlines()
    assert f"version: {versao}" in linhas, "atualize o version: do CITATION.cff junto com o pyproject.toml"
