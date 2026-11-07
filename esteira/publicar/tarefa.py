from pathlib import Path

NOMES = ("Tudo é Política - publicar", "Tudo é Política - publicar ao entrar")


def comandos_schtasks(python: Path, automacao: Path) -> list[list[str]]:
    linha = f'cmd /c cd /d "{automacao}" && "{python}" -m esteira publicar rodar >> logs\\publicar.log 2>&1'
    return [
        ["schtasks", "/Create", "/F", "/TN", NOMES[0], "/SC", "MINUTE", "/MO", "15", "/TR", linha],
        ["schtasks", "/Create", "/F", "/TN", NOMES[1], "/SC", "ONLOGON", "/TR", linha],
    ]
