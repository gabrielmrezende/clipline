import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from esteira.caminhos import garantir_escrita

ARQUIVO = "postagens.json"


@dataclass
class Item:
    numero: int
    rede: str
    data: str
    estado: str = "agendado"
    tentativas: int = 0
    link: str = ""
    id_rede: str = ""
    erro: str = ""
    assinatura: str = ""
    ia: bool = False  # o vídeo tem imagem de IA: vai com o rótulo de conteúdo sintético das redes que têm um


class Ocupado(Exception):
    pass


def ler_fila(pasta_episodio: Path) -> list[Item]:
    caminho = Path(pasta_episodio) / ARQUIVO
    if not caminho.exists():
        return []
    dados = json.loads(caminho.read_text("utf-8"))
    return [Item(**item) for item in dados["itens"]]


def gravar_fila(pasta_episodio: Path, itens: list[Item], base: Path | None = None) -> None:
    destino = Path(pasta_episodio) / ARQUIVO
    caminho = garantir_escrita(destino, base_extra=base) if base is not None else garantir_escrita(destino)
    temporario = caminho.with_name(caminho.name + ".tmp")
    texto = json.dumps({"itens": [asdict(i) for i in itens]}, ensure_ascii=False, indent=2)
    temporario.write_text(texto, "utf-8")
    temporario.replace(caminho)


def achar(itens: list[Item], numero: int, rede: str) -> Item | None:
    for item in itens:
        if item.numero == numero and item.rede == rede and item.estado != "cancelado":
            return item
    return None


def _vivo_windows(pid: int) -> bool:
    """OpenProcess + GetExitCodeProcess. No Windows, os.kill(pid, 0) não testa: encerra o processo."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    alca = kernel32.OpenProcess(_CONSULTA_LIMITADA, False, pid)
    if not alca:
        return ctypes.get_last_error() == _ACESSO_NEGADO  # existe, mas é de outro usuário
    try:
        codigo = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(alca, ctypes.byref(codigo)):
            return True  # na dúvida, vivo: o limite de idade resolve
        return codigo.value == _AINDA_ATIVO
    finally:
        kernel32.CloseHandle(alca)


def _vivo_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # sinal 0 só testa se o processo existe
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe, mas é de outro usuário
    return True


_CONSULTA_LIMITADA = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
_ACESSO_NEGADO = 5  # ERROR_ACCESS_DENIED
_AINDA_ATIVO = 259  # STILL_ACTIVE


def processo_vivo(pid: int, plataforma: str = sys.platform) -> bool:
    if pid <= 0:
        return False  # 0 e negativos apontam grupos de processos no POSIX
    try:
        return _vivo_windows(pid) if plataforma.startswith("win") else _vivo_posix(pid)
    except (OSError, OverflowError, ValueError):
        return True  # sem como saber: vale o limite de idade


def _dono(caminho: Path) -> int | None:
    """O PID gravado na trava; None numa trava sem PID (versão antiga, ou outro processo no meio da criação)."""
    try:
        dados = json.loads(caminho.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    pid = dados.get("pid") if isinstance(dados, dict) else None
    return pid if isinstance(pid, int) and not isinstance(pid, bool) else None


def _abandonada(caminho: Path, idade_maxima: float, vivo) -> bool:
    try:
        idade = time.time() - caminho.stat().st_mtime
    except FileNotFoundError:
        return False
    if idade > idade_maxima:
        return True  # reserva: um PID reaproveitado por outro programa não segura a fila para sempre
    pid = _dono(caminho)
    return pid is not None and not vivo(pid)


@contextmanager
def trava(caminho: Path, idade_maxima: float = 7200, vivo=processo_vivo):
    """Uma execução por vez. A trava guarda o PID e a hora de início; vale enquanto o processo existir,
    e no máximo `idade_maxima` segundos (2 h)."""
    caminho = Path(caminho)
    if caminho.exists() and _abandonada(caminho, idade_maxima, vivo):
        caminho.unlink(missing_ok=True)
    try:
        descritor = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Ocupado(f"outra execução em andamento ({caminho.name})") from None
    try:
        dono = {"pid": os.getpid(), "inicio": datetime.now().astimezone().isoformat(timespec="seconds")}
        os.write(descritor, json.dumps(dono).encode("utf-8"))
    finally:
        os.close(descritor)
    try:
        yield
    finally:
        caminho.unlink(missing_ok=True)
