"""Travas do agente: o hook PreToolUse do Claude Code roda isto antes de cada ferramenta.

Recebe a chamada em JSON pelo stdin e, quando ela publica, gasta, sobrescreve, mexe em credenciais ou grava
onde não pode, responde com permissionDecision "deny". Regras em prosa (CLAUDE.md) são sugestões; isto é a
parte que vale mesmo quando o modelo erra ou é induzido a errar por um texto que leu.

Falha fechada: se o JSON não puder ser lido, nega.

Limite conhecido: uma lista de padrões não pega tudo (um script que monta o comando em partes, por exemplo).
A defesa completa é que confirmar só exista no painel, com clique humano. Ver docs/seguranca-do-agente.md.
"""

import json
import re
import sys

FERRAMENTAS_DE_ESCRITA = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# (padrão, motivo). Procurados no comando inteiro, sem diferenciar maiúsculas.
COMANDOS_PROIBIDOS = [
    (r"--confirmar\b", "Confirmar (publicar, gerar imagem paga, instalar tarefa) é ato do dono: peça que ele confirme pelo painel ou rode o comando."),
    (r"--forcar\b", "--forcar sobrescreve trabalho: peça ao dono para rodar o comando."),
    (r"--religar\b", "--religar refaz a ligação voz/pessoa: peça ao dono para rodar o comando."),
    (r"\bpublicar\s+(conectar|marcar|cancelar|instalar-tarefa)\b", "Contas, fila e tarefa de publicação são do dono."),
    (r"\bimagens\s+conectar\b", "Chaves de API são do dono."),
    (r"\bpainel\s+codigo\b", "O código de acesso do painel é do dono."),
    (r"\b(keyring|cmdkey|vaultcmd)\b|get_password|set_password|CredRead", "Credenciais não são lidas nem gravadas pelo agente."),
    (r"\$env:HF_TOKEN|%HF_TOKEN%|\$HF_TOKEN|\bprintenv\b|\bGet-ChildItem\s+env:", "Tokens não são lidos pelo agente."),
    (r"\bgit\s+push\b.*(--force|-f\b)|\bgit\s+reset\s+--hard\b", "Operação destrutiva de git exige o dono."),
    (r"\bschtasks\b", "O Agendador de Tarefas é configurado pelo dono."),
]

# Escrever ou apagar em pastas protegidas, pelo shell.
VERBOS_DE_ESCRITA = r"(\brm\b|\bdel\b|\berase\b|\brmdir\b|\brd\b|Remove-Item|\bmv\b|\bmove\b|Move-Item|\bcp\b|\bcopy\b|Copy-Item|Set-Content|Out-File|>)"
PASTAS_PROTEGIDAS = [
    (r"1 - Programas", "1 - Programas/ é só leitura."),
    (r"video-final", "video-final/ é do dono: só o botão Aprovar do painel grava lá."),
]

# Arquivos que o agente não edita com Write/Edit.
CAMINHOS_PROIBIDOS = [
    (r"(^|[\\/])1 - Programas([\\/]|$)", "1 - Programas/ é só leitura."),
    (r"(^|[\\/])video-final([\\/]|$)", "video-final/ é do dono: só o botão Aprovar do painel grava lá."),
    (r"(^|[\\/])postagens\.json$", "A fila de publicação só muda pelos comandos e pelo painel."),
    (r"(^|[\\/])aprovado\.json$", "O registro de aprovação só muda pelo painel."),
    (r"(^|[\\/])publicacao\.json$", "O modo de publicação é decisão do dono."),
    (r"(^|[\\/])\.claude[\\/](settings(\.local)?\.json|hooks[\\/])", "As travas do agente só mudam pelo dono."),
    (r"(^|[\\/])\.env($|\.)", "Arquivos de segredo não são editados pelo agente."),
]


def decidir(chamada: dict) -> str | None:
    """O motivo da recusa, ou None se a chamada pode seguir."""
    ferramenta = chamada.get("tool_name", "")
    entrada = chamada.get("tool_input") or {}
    if ferramenta == "Bash":
        comando = str(entrada.get("command", ""))
        for padrao, motivo in COMANDOS_PROIBIDOS:
            if re.search(padrao, comando, re.IGNORECASE):
                return motivo
        if re.search(VERBOS_DE_ESCRITA, comando, re.IGNORECASE):
            for padrao, motivo in PASTAS_PROTEGIDAS:
                if re.search(padrao, comando, re.IGNORECASE):
                    return motivo
        return None
    if ferramenta in FERRAMENTAS_DE_ESCRITA:
        caminho = str(entrada.get("file_path") or entrada.get("notebook_path") or "")
        for padrao, motivo in CAMINHOS_PROIBIDOS:
            if re.search(padrao, caminho, re.IGNORECASE):
                return motivo
    return None


def _negar(motivo: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"clipline: {motivo}",
        }
    }, ensure_ascii=False))


def principal() -> int:
    try:
        chamada = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        if not isinstance(chamada, dict):
            raise ValueError("chamada não é um objeto")
    except (ValueError, UnicodeDecodeError):
        _negar("não consegui ler a chamada da ferramenta; por segurança, nada foi executado.")
        return 0
    motivo = decidir(chamada)
    if motivo:
        _negar(motivo)
    return 0


if __name__ == "__main__":
    sys.exit(principal())
