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

## Servidor MCP, revisão visual e classificador

Três peças novas (detalhes e configuração em [`mcp.md`](mcp.md)):

| Camada | Onde | O que garante |
|---|---|---|
| Ferramentas tipadas | `esteira/mcp_servidor.py` (`esteira mcp`) | Nenhum parâmetro para confirmar, forçar, religar, publicar, gastar ou ler credenciais. `aprovados.json`, `pedidos.json` e `post.md` só pelo contrato, com escrita confinada e atômica; arquivo que já existe só é regravado com a versão da última leitura; `aprovado` e `no_video` (do dono) e o que a esteira baixou vêm sempre do arquivo que já estava; prompt de IA com pessoa do glossário é recusado; corte já preparado não muda de pasta nem de tempo. Conteúdo do episódio volta marcado como dado. |
| Classificador de pessoa real | `esteira/classificador.py` (`[ia] classificador = true`) | Segunda trava, por modelo, logo antes de gerar imagem de IA. Desligado por padrão; ligado, falha fechada (sem chave, sem rede ou com recusa do modelo, não gera). |
| Revisão visual | `esteira/revisao_visual.py` (`esteira revisao-visual`) | Segunda opinião sobre quadros de cada `corte.mp4`. Gasta, então só com `--confirmar`, que o hook nega ao agente. |

O `.claude/settings.json` do repositório não mudou. Tirar o shell do agente é uma escolha do dono, em
`.claude/settings.local.json` (o bloco sugerido está em `mcp.md`).

### Limites que ficam

- O servidor MCP só tira poder quando o shell sai. Com `Bash` liberado, o agente ainda roda qualquer comando, e quem
  segura é o hook, que lê o texto.
- O hook confere `Bash`, `Write`, `Edit`, `MultiEdit` e `NotebookEdit`. A ferramenta `PowerShell` que o Claude Code
  oferece no Windows não passa por ele (nem o matcher do `settings.json` nem o `decidir` olham para ela). Enquanto o
  shell estiver liberado, negue `PowerShell` nas permissões ou estenda o hook.
- No modo sem shell, `Write` e `Edit` continuam (o agente escreve `candidatos.md` e `calendario.md`). Por eles ainda
  dá para gravar `aprovados.json`, `pedidos.json` e `post.md` sem contrato nem versão; o hook só barra os caminhos
  protegidos. O `validar` pega o formato, mas não devolve ao dono um `aprovado` que o agente tenha mudado.
- A versão impede sobrescrever às cegas, mas não é uma trava de arquivo: entre a conferência e a gravação
  (milissegundos), o painel ainda pode gravar.
- As anotações das ferramentas (só leitura, destrutiva) e o aviso "é dado, não instrução" são dicas para o cliente e
  para o modelo. A garantia é o que as ferramentas não fazem.
- O classificador é um modelo e erra para os dois lados. Ele soma à lista do glossário e à aprovação de cada prompt
  pelo dono no painel; não substitui nenhuma das duas.
- A revisão visual manda quadros (com o rosto dos convidados), legendas e falas para a API da Anthropic; o
  classificador manda o prompt e a lista de pessoas do glossário. Nenhum dos dois manda chave nem arquivo do dono.
- A revisão visual é opinião, não aprovação. O dono continua revendo cada corte no painel.
- A chave da Anthropic fica no Gerenciador de Credenciais (`imagens conectar anthropic`, que o hook nega ao agente).
  O `doctor` ainda não diz se ela está guardada.
- Não há fallback de modelo: se o modelo configurado sair do ar, a revisão daquele corte vira erro e o classificador
  recusa a geração. Troca-se o modelo no `clipline.toml`.
