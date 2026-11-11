import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "travas.py"
_spec = importlib.util.spec_from_file_location("travas", HOOK)
travas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(travas)


def _bash(comando: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": comando}}


@pytest.mark.parametrize("comando", [
    '.venv\\Scripts\\python.exe -m esteira publicar agendar "x" --numero 1 --data "2026-12-01 18:00" --confirmar',
    'python -m esteira imagens gerar "x" --confirmar',
    'python -m esteira montar "x" --numero 2 --forcar',
    'python -m esteira planos "x" --religar',
    'python -m esteira publicar conectar youtube',
    'python -m esteira publicar marcar "x" --numero 1 --rede tiktok feito',
    'python -m esteira painel codigo',
    'python -c "import keyring; print(keyring.get_password(1,2))"',
    'echo $env:HF_TOKEN',
    'rm "../2 - Cortes/Ep 01/01-x/video-final/corte-aprovado.mp4"',
    'Remove-Item "..\\1 - Programas\\Ep.mp4"',
    'copy corte.mp4 "video-final\\meu.mp4"',
    'schtasks /Create /TN x',
    'git push --force origin master',
])
def test_nega_o_que_e_do_dono(comando):
    assert travas.decidir(_bash(comando))


@pytest.mark.parametrize("comando", [
    'python -m esteira publicar agendar "x" --numero 1 --data "2026-12-01 18:00"',
    'python -m esteira imagens gerar "x"',
    'python -m esteira montar "x" --numero 2',
    'python -m esteira validar "x" --json',
    'python -m esteira trecho "x" --de 10 --ate 20',
    'ls "../1 - Programas"',
    'python -m pytest',
])
def test_deixa_o_trabalho_normal(comando):
    assert travas.decidir(_bash(comando)) is None


@pytest.mark.parametrize("caminho", [
    "C:/Canal/2 - Cortes/Ep/01-x/video-final/corte.mp4",
    "C:\\Canal\\1 - Programas\\Ep.mp4",
    "C:/Canal/2 - Cortes/Ep/postagens.json",
    "C:/Canal/Automacao/.claude/settings.json",
    "C:/Canal/Automacao/.claude/hooks/travas.py",
    "C:/Canal/Automacao/publicacao.json",
])
def test_nega_escrita_em_arquivo_protegido(caminho):
    assert travas.decidir({"tool_name": "Write", "tool_input": {"file_path": caminho, "content": ""}})


def test_deixa_escrever_os_arquivos_do_agente():
    for nome in ("aprovados.json", "01-x/trabalho/pedidos.json", "01-x/post.md", "calendario.md"):
        chamada = {"tool_name": "Edit", "tool_input": {"file_path": f"C:/Canal/2 - Cortes/Ep/{nome}"}}
        assert travas.decidir(chamada) is None


def _rodar(entrada: bytes) -> str:
    return subprocess.run([sys.executable, str(HOOK)], input=entrada, capture_output=True, check=True).stdout.decode("utf-8")


def test_saida_no_formato_do_claude_code():
    saida = json.loads(_rodar(json.dumps(_bash("esteira montar x --forcar")).encode("utf-8")))
    assert saida["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert saida["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_chamada_permitida_nao_imprime_nada():
    assert _rodar(json.dumps(_bash("esteira validar x")).encode("utf-8")) == ""


def test_falha_fechada_com_json_ilegivel():
    saida = json.loads(_rodar(b"{isto nao e json"))
    assert saida["hookSpecificOutput"]["permissionDecision"] == "deny"
