# Publicação agendada dos cortes — design

Data: 06/11/2026. Status: aguardando revisão do dono do canal.

## Objetivo

O dono do canal pede "agende o corte N para <data>". A esteira mostra um
resumo, espera o sim dele e agenda o corte no YouTube, no Instagram e no
TikTok, usando o vídeo de `video-final/` e os textos do `post.md`. Depois
disso ele não precisa abrir as redes, exceto pelos cliques que as
auditorias ainda exigem (ver "Limites das redes").

## Decisões do dono do canal

- Agendar com um comando, nas três redes de uma vez.
- A data e a hora vêm do pedido dele. Nada de calendário automático.
- Antes de enviar, a esteira mostra o resumo e espera um sim claro.
- TikTok, até a auditoria: o vídeo vai para os rascunhos do app.
- Instagram e TikTok atrasados (PC desligado no horário) são publicados
  assim que o PC ligar, sem limite de atraso.

## Limites das redes

| Rede | Antes da auditoria | Depois da auditoria |
|---|---|---|
| YouTube | Sobe como privado, com título e descrição. O dono muda para "agendado" no Studio. | Sobe privado com `publishAt`: o YouTube publica sozinho, com o PC desligado. |
| Instagram | Publica o Reels direto, no horário, pelo PC. | Igual. |
| TikTok | Envia para os rascunhos do app (inbox), sem o texto: a API não leva legenda ao rascunho. O dono cola o texto do `post.md` e toca em publicar. | Publica direto (Direct Post), no horário, pelo PC. |

- YouTube: projetos novos da API ficam com vídeo travado em privado até
  a auditoria de conformidade do Google.
- Instagram: API do Instagram com login do Instagram. Serve para conta
  profissional sem página do Facebook. Não agenda pela API: o PC publica
  no horário.
- TikTok: Content Posting API. Sem auditoria, só privado ou rascunho.
  Não agenda pela API: o PC envia no horário.
- O modo de cada rede ("privado"/"agendado", "rascunho"/"direto") fica
  numa configuração sem segredos, `Automacao/publicacao.json`. O dono
  troca quando a auditoria sair.

## Comandos

Todos em `Automacao/`, com `.venv\Scripts\python.exe -m esteira publicar ...`.

- `conectar youtube|instagram|tiktok`: cadastro único de cada rede.
- `agendar "<pasta do episódio>" --numero N --data "AAAA-MM-DD HH:MM"`:
  sem `--confirmar`, só mostra o resumo e não envia nada. Com
  `--confirmar`, grava na fila e envia ao YouTube na hora.
  `--redes youtube,instagram` limita as redes (padrão: as três).
- `fila ["<pasta do episódio>"]`: lista cada corte e rede com o estado,
  a data, o link e o erro, se houver.
- `rodar`: publica o que já venceu. Roda pelo Agendador de Tarefas.
- `cancelar "<pasta do episódio>" --numero N [--redes ...]`: tira da fila
  o que ainda não saiu.
- `marcar "<pasta do episódio>" --numero N --rede R feito|reenviar`:
  resolve um item em "conferir".
- `instalar-tarefa`: cria a tarefa no Agendador do Windows (ver abaixo).

A data é sempre no horário de Brasília (America/Sao_Paulo).

## Fluxo de agendamento

1. O Claude Code roda `agendar` sem `--confirmar` e mostra o resumo ao
   dono do canal:
   - vídeo, duração e resolução;
   - para cada rede, o título e o texto exatos;
   - a data.
2. Com um sim claro, roda o mesmo comando com `--confirmar`. O sim vale
   só para aquele corte, aquelas redes e aquela data.
3. YouTube: envia logo, como privado, e com `publishAt` no modo
   "agendado".
4. Instagram e TikTok ficam "agendado" na fila até o `rodar` encontrá-los
   vencidos.

## Conferências do `agendar` (barram o agendamento)

- Há exatamente um `.mp4` em `video-final/`.
- O vídeo é vertical, 1080x1920. YouTube: até 3 minutos (Shorts).
- O `post.md` existe e tem as seções `## YouTube` (com `Título:` e
  `Descrição:`), `## Instagram` e `## TikTok`.
- Cada texto traz o crédito da música do `montagem.json` do corte.
- A data é futura.
- O corte não está agendado nem publicado naquela rede.

Os textos saem do `post.md` sem nenhuma mudança. A seção `## Música` e
qualquer outra seção são ignoradas.

## Fila: `postagens.json`

Fica na pasta do episódio. Cada item tem corte, rede, data, estado,
tentativas, link, id na rede e erro.

Estados: `agendado` → `enviando` → `publicado` (ou `rascunho`, ou
`privado` no YouTube antes da auditoria). Os outros estados são `erro`,
`conferir` e `cancelado`.

Regras:
- Antes de enviar, o item passa a `enviando`, e o arquivo é gravado.
- Um item que já está em `enviando` quando o `rodar` começa vira
  `conferir`. Ele nunca é reenviado sozinho, para não publicar duas vezes.
- Falha de rede ou de servidor: volta a `agendado` e soma uma tentativa.
  Na terceira, vira `erro`.
- Token vencido sem renovação: `erro`, com "reconecte com
  `publicar conectar <rede>`".
- Erro numa rede ou num corte não impede os outros.
- Duas execuções do `rodar` ao mesmo tempo: um arquivo de trava na pasta
  `Automacao/` faz a segunda sair sem fazer nada.

O `rodar` lê as filas de todas as pastas de episódio em `2 - Cortes/`.

## Agendador de Tarefas

`publicar instalar-tarefa` cria a tarefa "Tudo é Política - publicar".
Ela roda `publicar rodar` a cada 15 minutos e ao entrar no Windows, só
com o usuário logado. O registro vai para `Automacao/logs/publicar.log`,
sem tokens. A instalação mostra o que vai criar e pede confirmação.

## Contas e segredos

- O dono do canal cria os apps de desenvolvedor: projeto no Google Cloud
  com YouTube Data API v3, app da Meta com Instagram API e app no TikTok
  for Developers. O `operacao.md` traz o passo a passo.
- `conectar` pede o id e o segredo do app no terminal, sem mostrar o que
  é digitado. Depois abre o site oficial da rede no navegador. O retorno
  vem para `http://localhost` no próprio PC, e a esteira troca o código
  pelo token.
- Exceção, Instagram: a Meta só aceita retorno `https`. O dono gera o
  token no painel do app da Meta ("Gerar token") e o cola no terminal, sem
  ele aparecer.
- Id, segredo e tokens vão para o Gerenciador de Credenciais do Windows,
  pelo pacote `keyring`. Nunca vão para arquivo, log ou mensagem.
- A renovação dos tokens é automática: refresh token no YouTube e no
  TikTok, token longo renovável no Instagram.

## Componentes

- `esteira/publicar/fila.py`: lê e grava o `postagens.json`, faz as
  transições de estado e cuida da trava. Não acessa a rede.
- `esteira/publicar/post.py`: lê o `post.md` e faz as conferências.
- `esteira/publicar/agendar.py`: monta o resumo e grava a fila.
- `esteira/publicar/rodar.py`: escolhe os itens vencidos e chama a rede.
- `esteira/publicar/credenciais.py`: interface do `keyring` e fluxo OAuth
  local.
- `esteira/publicar/youtube.py`, `instagram.py`, `tiktok.py`: cada um
  expõe `publicar(video, textos, data, modo) -> Resultado(link, id,
  estado)`. Os módulos usam `urllib`, como o `rede.py`, com upload
  retomável.
- `esteira/cli.py`: o subcomando `publicar`.

## Testes

- Fila, post, agendar e rodar são testados com redes falsas: estados,
  duplicação, atraso, trava e conferências.
- Cada módulo de rede é testado com respostas HTTP gravadas, sem acesso à
  internet.
- Nenhum teste publica de verdade. O primeiro envio real é um corte
  aprovado, com o sim do dono, depois do `conectar`.

## Fora do escopo

- Calendário ou escolha automática de datas.
- Apagar ou editar posts já publicados.
- Miniatura personalizada, legenda, música do app ou marcação de pessoas.
- Métricas de desempenho.
- Pedir as auditorias. O dono do canal faz isso; o `operacao.md` traz os
  links.

## Regras que mudam

- `Contexto/redes-e-publicacao.md`: "A postagem só acontece depois da
  aprovação humana" continua valendo. O sim ao resumo do `agendar` é essa
  aprovação, para aquele corte, aquelas redes e aquela data.
- `CLAUDE.md` e `operacao.md`: acrescentar a etapa de publicação, com
  aprovação.
