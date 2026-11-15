"""O que a tarefa de publicação instala em cada sistema. Só monta textos e listas: nada roda aqui.

Windows: duas tarefas no Agendador (a cada 15 min e ao entrar). Linux: um timer de usuário do systemd ou, sem ele,
duas linhas no crontab. macOS: um LaunchAgent. Os nomes vêm do nome do canal (`clipline.toml`); com o padrão, são
os mesmos de sempre.
"""
import plistlib
import re
import shlex
import unicodedata
from pathlib import Path

CANAL_PADRAO = "Tudo é Política"
MINUTOS = 15


def nomes(canal: str = CANAL_PADRAO) -> tuple[str, str]:
    """Nomes das duas tarefas no Agendador do Windows. A barra invertida criaria uma pasta: sai."""
    base = re.sub(r'[\\/:*?"<>|]', "-", canal).strip() or "clipline"
    return (f"{base} - publicar", f"{base} - publicar ao entrar")


NOMES = nomes()


def apelido(canal: str = CANAL_PADRAO) -> str:
    """O canal em minúsculas, sem acento e com hífens ("tudo-e-politica"): nome de arquivo e de unidade."""
    sem_acento = unicodedata.normalize("NFKD", canal).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-") or "clipline"


# --- Windows ----------------------------------------------------------------------------------------------


def linha_windows(python: Path, automacao: Path) -> str:
    """Sem `>> logs\\publicar.log`: o próprio `publicar rodar` grava o log, com rotação."""
    return f'cmd /c cd /d "{automacao}" && "{python}" -m esteira publicar rodar'


def comandos_schtasks(python: Path, automacao: Path, canal: str = CANAL_PADRAO) -> list[list[str]]:
    linha = linha_windows(python, automacao)
    a_cada, ao_entrar = nomes(canal)
    return [
        ["schtasks", "/Create", "/F", "/TN", a_cada, "/SC", "MINUTE", "/MO", str(MINUTOS), "/TR", linha],
        ["schtasks", "/Create", "/F", "/TN", ao_entrar, "/SC", "ONLOGON", "/TR", linha],
    ]


def comandos_remover_schtasks(canal: str = CANAL_PADRAO) -> list[list[str]]:
    return [["schtasks", "/Delete", "/F", "/TN", nome] for nome in nomes(canal)]


def comandos_consultar_schtasks(canal: str = CANAL_PADRAO) -> list[list[str]]:
    return [["schtasks", "/Query", "/TN", nome, "/V", "/FO", "LIST"] for nome in nomes(canal)]


def redireciona_log(descricao_da_tarefa: str) -> bool:
    """A tarefa instalada antes da rotação manda a saída para o log pelo cmd (`>> logs\\publicar.log`)."""
    return "publicar.log" in descricao_da_tarefa


# --- Linux: systemd do usuário ----------------------------------------------------------------------------


def unidade_systemd(canal: str = CANAL_PADRAO) -> str:
    return f"{apelido(canal)}-publicar"


def _sem_especificador(texto: str) -> str:
    """No systemd, % abre um especificador (%h, %u...): um % de verdade é %%."""
    return texto.replace("%", "%%")


def _argumento_systemd(texto: str) -> str:
    escapado = texto.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + _sem_especificador(escapado) + '"'


def arquivos_systemd(python: Path, automacao: Path, canal: str = CANAL_PADRAO) -> dict[str, str]:
    """{nome do arquivo: conteúdo} do serviço e do timer, para ~/.config/systemd/user/."""
    nome = unidade_systemd(canal)
    descricao = _sem_especificador(f"{canal}: publicar os cortes agendados")
    servico = (
        "[Unit]\n"
        f"Description={descricao}\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"WorkingDirectory={_sem_especificador(str(automacao))}\n"
        f"ExecStart={_argumento_systemd(str(python))} -m esteira publicar rodar\n"
    )
    # OnActiveSec conta da ativação do timer (ao entrar, ou logo depois de instalar); OnUnitActiveSec repete a
    # cada 15 min contados da última rodada. Um OnStartupSec sozinho nunca dispararia num timer ligado no meio
    # da sessão, porque o instante dele já passou.
    timer = (
        "[Unit]\n"
        f"Description={descricao} (a cada {MINUTOS} min e ao entrar)\n"
        "\n"
        "[Timer]\n"
        "OnActiveSec=1min\n"
        f"OnUnitActiveSec={MINUTOS}min\n"
        f"Unit={nome}.service\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    return {f"{nome}.service": servico, f"{nome}.timer": timer}


# --- Linux: cron (reserva) --------------------------------------------------------------------------------


def marca_cron(canal: str = CANAL_PADRAO) -> str:
    return f"# clipline: {unidade_systemd(canal)}"


def linhas_cron(python: Path, automacao: Path, canal: str = CANAL_PADRAO) -> list[str]:
    """A cada 15 min e no boot (o cron não sabe quando o usuário entra). No crontab, % vira quebra de linha."""
    comando = f"cd {shlex.quote(str(automacao))} && {shlex.quote(str(python))} -m esteira publicar rodar >/dev/null"
    comando = comando.replace("%", "\\%")
    marca = marca_cron(canal)
    return [f"*/{MINUTOS} * * * * {comando} {marca}", f"@reboot {comando} {marca}"]


def crontab_sem(atual: str, canal: str = CANAL_PADRAO) -> str:
    """O crontab sem as linhas desta tarefa; o resto fica como estava."""
    marca = marca_cron(canal)
    linhas = [linha for linha in atual.splitlines() if not linha.rstrip().endswith(marca)]
    return "".join(linha + "\n" for linha in linhas)


def crontab_com(atual: str, python: Path, automacao: Path, canal: str = CANAL_PADRAO) -> str:
    """O crontab com as linhas desta tarefa no fim (trocando as de uma instalação anterior)."""
    return crontab_sem(atual, canal) + "".join(linha + "\n" for linha in linhas_cron(python, automacao, canal))


# --- macOS: launchd ---------------------------------------------------------------------------------------


def rotulo_launchd(canal: str = CANAL_PADRAO) -> str:
    return f"clipline.{apelido(canal)}.publicar"


def plist_launchd(python: Path, automacao: Path, canal: str = CANAL_PADRAO) -> str:
    """LaunchAgent: roda ao carregar (ao entrar na sessão) e a cada 15 min."""
    dados = {
        "Label": rotulo_launchd(canal),
        "ProgramArguments": [str(python), "-m", "esteira", "publicar", "rodar"],
        "WorkingDirectory": str(automacao),
        "StartInterval": MINUTOS * 60,
        "RunAtLoad": True,
        "ProcessType": "Background",
    }
    return plistlib.dumps(dados, sort_keys=False).decode("utf-8")
