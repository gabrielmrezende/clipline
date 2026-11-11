# Segurança do agente e do painel

O clipline dá a um agente (Claude Code) um terminal, arquivos de terceiros para ler e comandos que publicam e gastam.
Este documento diz o que impede o pior e onde estão os limites.

## Camadas

| Camada | Onde | O que garante |
|---|---|---|
| Regras em texto | `CLAUDE.md`, skills em `.claude/skills/` | Orientação. O modelo costuma seguir, mas não é garantia. |
| Travas determinísticas | `.claude/hooks/travas.py` (hook `PreToolUse`) | Nega `--confirmar`, `--forcar`, `--religar`, `publicar conectar/marcar/cancelar`, leitura de credenciais e tokens, escrita em `1 - Programas/`, `video-final/`, fila e travas. Falha fechada. |
| Confirmação fora do terminal | Painel: blocos **Publicar**, **Imagens**, **Aprovar** | O sim é um clique humano sobre o resumo exato que foi mostrado (a marca do resumo vai junto). |
| Contrato dos arquivos | `esteira/contrato.py`, `docs/esquemas/` | Arquivo fora do formato é recusado com arquivo, campo e correção. |
| Escrita confinada | `caminhos.garantir_escrita` | Nada grava fora de `2 - Cortes/` e da pasta do repositório. |
| Painel | `esteira/painel/app.py` | `TrustedHostMiddleware`, recusa de pedidos de outra origem (`Sec-Fetch-Site`, `Origin`), CSP e cabeçalhos de segurança, código de acesso com trava por aparelho na rede local. |
| Segredos | Gerenciador de Credenciais (keyring), `HF_TOKEN` | Nenhuma chave em arquivo; mensagens de erro mascaram tokens. |

## Conteúdo não confiável

Transcrição (fala de convidados), títulos e autores do Wikimedia Commons, `post.md` e páginas da web entram no contexto
do agente. O `CLAUDE.md` manda tratá-los como dados. Os metadados do Wikimedia chegam saneados (sem HTML, numa linha,
com tamanho limitado). O impacto de uma instrução escondida é contido pelas travas: mesmo enganado, o agente não
confirma nada.

## Limites conhecidos

- O hook olha o texto do comando. Um script que monta o comando em partes passa. Por isso o caminho recomendado para
  confirmar é o painel, e não a CLI.
- O filtro de pessoa real em imagens de IA é uma lista (nomes do glossário e cargos públicos). Descrição que identifica
  alguém sem nome nem cargo passa; o dono aprova cada prompt no painel.
- Na rede local o painel é HTTP sem TLS. Use só na Wi-Fi de casa. Para fora dela, prefira uma VPN como Tailscale.
