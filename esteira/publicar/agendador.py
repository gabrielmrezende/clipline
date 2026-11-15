"""Instala, remove e confere a tarefa de publicação no agendador de cada sistema.

Os comandos rodam por um `executar` injetado: os testes passam um falso e conferem os arquivos e os comandos sem
mexer no sistema. Os arquivos (unidades do systemd, plist do launchd) vão para a pasta do usuário, `casa`.
"""
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from esteira.caminhos import gravar_atomico
from esteira.publicar import tarefa

TEMPO = 60
TITULOS = {
    "windows": "no Agendador do Windows",
    "systemd": "no systemd do usuário (timer)",
    "cron": "no crontab do usuário",
    "launchd": "no launchd (LaunchAgent do usuário)",
}


class ErroTarefa(Exception):
    pass


@dataclass
class Execucao:
    codigo: int
    saida: str = ""


Executar = Callable[..., Execucao]


def executar_no_sistema(comando: list[str], entrada: str | None = None) -> Execucao:
    try:
        feito = subprocess.run(comando, input=entrada, capture_output=True, text=True, errors="replace", timeout=TEMPO)
    except FileNotFoundError:
        return Execucao(127, f"{comando[0]} não encontrado")
    except subprocess.TimeoutExpired:
        return Execucao(124, f"{comando[0]} não respondeu em {TEMPO} s")
    return Execucao(feito.returncode, (feito.stdout or "") + (feito.stderr or ""))


@dataclass
class Passo:
    """Um passo da instalação: gravar um arquivo, apagar um arquivo ou rodar um comando."""

    comando: list[str] | None = None
    entrada: str | None = None  # o que vai pelo stdin (o crontab novo)
    gravar: Path | None = None
    conteudo: str = ""
    apagar: Path | None = None
    tolerar: bool = False  # falha vira aviso: tirar o que já não estava lá, por exemplo


@dataclass
class Plano:
    sistema: str  # windows | systemd | cron | launchd
    passos: list[Passo] = field(default_factory=list)

    @property
    def onde(self) -> str:
        return TITULOS[self.sistema]


def sistema_atual(plataforma: str = sys.platform) -> str:
    """windows, launchd ou linux (que vira systemd ou cron conforme o que existir)."""
    if plataforma.startswith("win"):
        return "windows"
    if plataforma == "darwin":
        return "launchd"
    return "linux"


def _tem_systemd(executar: Executar) -> bool:
    return executar(["systemctl", "--user", "show-environment"]).codigo == 0


def _crontab_atual(executar: Executar) -> str:
    lido = executar(["crontab", "-l"])
    if lido.codigo == 127:
        raise ErroTarefa("sem systemd do usuário e sem crontab: instale o cron ou ligue o systemd")
    return lido.saida if lido.codigo == 0 else ""  # código 1: o usuário ainda não tem crontab


def _resolver(sistema: str, executar: Executar) -> str:
    if sistema != "linux":
        return sistema
    return "systemd" if _tem_systemd(executar) else "cron"


def _pasta_systemd(casa: Path) -> Path:
    return Path(casa) / ".config" / "systemd" / "user"


def _plist(casa: Path, canal: str) -> Path:
    return Path(casa) / "Library" / "LaunchAgents" / f"{tarefa.rotulo_launchd(canal)}.plist"


def _uid() -> int:
    return os.getuid() if hasattr(os, "getuid") else 0


def plano_instalar(sistema: str, python: Path, automacao: Path, canal: str, casa: Path,
                   executar: Executar, uid: int | None = None) -> Plano:
    sistema = _resolver(sistema, executar)
    if sistema == "windows":
        return Plano(sistema, [Passo(c) for c in tarefa.comandos_schtasks(python, automacao, canal)])
    if sistema == "systemd":
        pasta = _pasta_systemd(casa)
        passos = [Passo(gravar=pasta / nome, conteudo=texto)
                  for nome, texto in tarefa.arquivos_systemd(python, automacao, canal).items()]
        timer = f"{tarefa.unidade_systemd(canal)}.timer"
        passos += [Passo(["systemctl", "--user", "daemon-reload"]),
                   Passo(["systemctl", "--user", "enable", "--now", timer])]
        return Plano(sistema, passos)
    if sistema == "cron":
        novo = tarefa.crontab_com(_crontab_atual(executar), python, automacao, canal)
        return Plano(sistema, [Passo(["crontab", "-"], entrada=novo)])
    if sistema == "launchd":
        plist = _plist(casa, canal)
        dominio = f"gui/{_uid() if uid is None else uid}"
        return Plano(sistema, [
            Passo(gravar=plist, conteudo=tarefa.plist_launchd(python, automacao, canal)),
            Passo(["launchctl", "bootout", f"{dominio}/{tarefa.rotulo_launchd(canal)}"], tolerar=True),
            Passo(["launchctl", "bootstrap", dominio, str(plist)]),
        ])
    raise ErroTarefa(f"sistema desconhecido: {sistema}")


def plano_desinstalar(sistema: str, canal: str, casa: Path, executar: Executar, uid: int | None = None) -> Plano:
    sistema = _resolver(sistema, executar)
    if sistema == "windows":
        return Plano(sistema, [Passo(c, tolerar=True) for c in tarefa.comandos_remover_schtasks(canal)])
    if sistema == "systemd":
        pasta = _pasta_systemd(casa)
        timer = f"{tarefa.unidade_systemd(canal)}.timer"
        passos = [Passo(["systemctl", "--user", "disable", "--now", timer], tolerar=True)]
        passos += [Passo(apagar=pasta / nome) for nome in tarefa.arquivos_systemd(Path(), Path(), canal)]
        passos.append(Passo(["systemctl", "--user", "daemon-reload"], tolerar=True))
        return Plano(sistema, passos)
    if sistema == "cron":
        return Plano(sistema, [Passo(["crontab", "-"], entrada=tarefa.crontab_sem(_crontab_atual(executar), canal))])
    if sistema == "launchd":
        dominio = f"gui/{_uid() if uid is None else uid}"
        return Plano(sistema, [
            Passo(["launchctl", "bootout", f"{dominio}/{tarefa.rotulo_launchd(canal)}"], tolerar=True),
            Passo(apagar=_plist(casa, canal)),
        ])
    raise ErroTarefa(f"sistema desconhecido: {sistema}")


def _linha_de_comando(comando: list[str], sistema: str) -> str:
    return subprocess.list2cmdline(comando) if sistema == "windows" else shlex.join(comando)


def descrever(plano: Plano) -> list[str]:
    """O plano em linhas para o terminal; no Windows, os comandos como sempre foram mostrados."""
    linhas = []
    for passo in plano.passos:
        if passo.gravar is not None:
            linhas += [f"gravar {passo.gravar}:", *(f"    {linha}" for linha in passo.conteudo.splitlines())]
        elif passo.apagar is not None:
            linhas.append(f"apagar {passo.apagar}")
        elif passo.entrada is not None:
            linhas += [f"{_linha_de_comando(passo.comando, plano.sistema)}  (crontab novo):",
                       *(f"    {linha}" for linha in passo.entrada.splitlines())]
        else:
            linhas.append(_linha_de_comando(passo.comando, plano.sistema))
    return linhas


def _resumo_da_saida(saida: str) -> str:
    texto = " ".join(saida.split())
    return f": {texto[:200]}" if texto else ""


def aplicar(plano: Plano, executar: Executar) -> list[str]:
    """Roda os passos em ordem. Um passo tolerado que falha vira aviso; os outros param tudo."""
    avisos = []
    for passo in plano.passos:
        if passo.gravar is not None:
            passo.gravar.parent.mkdir(parents=True, exist_ok=True)
            gravar_atomico(passo.gravar, passo.conteudo, newline="\n")
        elif passo.apagar is not None:
            passo.apagar.unlink(missing_ok=True)
        else:
            feito = executar(passo.comando, passo.entrada) if passo.entrada is not None else executar(passo.comando)
            if feito.codigo == 0:
                continue
            mensagem = f"{passo.comando[0]} falhou (código {feito.codigo}){_resumo_da_saida(feito.saida)}"
            if not passo.tolerar:
                raise ErroTarefa(mensagem)
            avisos.append(f"aviso: {mensagem}")
    return avisos


@dataclass
class Situacao:
    estado: str  # ok | aviso
    detalhe: str


REINSTALAR = "reinstale com publicar instalar-tarefa --confirmar"
TAREFA_ANTIGA = f"tarefa antiga: grava o log pelo cmd (>>), sem rotação; {REINSTALAR}"
NAO_INSTALADA = "não instalada: publicar instalar-tarefa mostra o que seria criado"


def situacao(sistema: str, canal: str, casa: Path, executar: Executar) -> Situacao:
    """A tarefa está instalada? É a antiga, que redireciona o log pelo cmd? Só lê; nunca muda nada."""
    if sistema == "windows":
        consultas = [executar(c) for c in tarefa.comandos_consultar_schtasks(canal)]
        if not any(c.codigo == 0 for c in consultas):
            return Situacao("aviso", NAO_INSTALADA)
        if any(c.codigo == 0 and tarefa.redireciona_log(c.saida) for c in consultas):
            return Situacao("aviso", TAREFA_ANTIGA)
        if not all(c.codigo == 0 for c in consultas):
            return Situacao("aviso", f"só uma das duas tarefas está instalada; {REINSTALAR}")
        return Situacao("ok", f"instalada {TITULOS['windows']}")
    if sistema == "launchd":
        if _plist(casa, canal).is_file():
            return Situacao("ok", f"instalada {TITULOS['launchd']}")
        return Situacao("aviso", NAO_INSTALADA)
    if (_pasta_systemd(casa) / f"{tarefa.unidade_systemd(canal)}.timer").is_file():
        return Situacao("ok", f"instalada {TITULOS['systemd']}")
    lido = executar(["crontab", "-l"])
    if lido.codigo == 0 and tarefa.marca_cron(canal) in lido.saida:
        return Situacao("ok", f"instalada {TITULOS['cron']}")
    return Situacao("aviso", NAO_INSTALADA)
