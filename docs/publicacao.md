# Publicação agendada

`publicar rodar` envia o que venceu na fila (`postagens.json` de cada episódio). Quem chama esse comando a cada
15 minutos é o agendador do sistema, instalado por `publicar instalar-tarefa`. Este documento diz o que é criado
em cada sistema, como conferir, como remover e onde fica o registro.

O fluxo de agendar (resumo, `--confirmar`, painel) está em [`operacao.md`](operacao.md).

## Instalar e remover

Sem `--confirmar`, os dois comandos só mostram o que vão fazer: arquivos, conteúdo e comandos.

```bash
.venv\Scripts\python.exe -m esteira publicar instalar-tarefa
.venv\Scripts\python.exe -m esteira publicar instalar-tarefa --confirmar
.venv\Scripts\python.exe -m esteira publicar desinstalar-tarefa
.venv\Scripts\python.exe -m esteira publicar desinstalar-tarefa --confirmar
```

No Linux e no macOS, troque `.venv\Scripts\python.exe` por `.venv/bin/python`.

Instalar de novo substitui a tarefa anterior (os mesmos nomes). Remover uma tarefa que não existe só gera um aviso.
O agente (Claude Code) não instala nem remove tarefas: confirmar é do dono.

### Nomes

Os nomes vêm de `[canal] nome` no `clipline.toml`. Sem o arquivo, o canal é "Tudo é Política" e os nomes são os de
sempre.

| Sistema | Nome com o canal padrão |
|---|---|
| Windows | `Tudo é Política - publicar` e `Tudo é Política - publicar ao entrar` |
| Linux (systemd) | `tudo-e-politica-publicar.service` e `tudo-e-politica-publicar.timer` |
| Linux (cron) | linhas terminadas em `# clipline: tudo-e-politica-publicar` |
| macOS | `clipline.tudo-e-politica.publicar` |

No Windows, os caracteres que o Agendador não aceita (`\ / : * ? " < > |`) viram `-`. Nos outros sistemas, o nome
do canal vai sem acento, em minúsculas e com hífens.

Trocou o nome do canal? Remova a tarefa antes de trocar (com o nome antigo ainda valendo) e instale de novo depois.
Senão ficam duas tarefas rodando a mesma fila; a trava impede envio duplo, mas a antiga continua lá.

## Windows: Agendador de Tarefas

Duas tarefas, criadas com `schtasks`:

- a cada 15 minutos (`/SC MINUTE /MO 15`);
- ao entrar no Windows (`/SC ONLOGON`).

As duas rodam `cmd /c cd /d "<Automacao>" && "<python>" -m esteira publicar rodar`, com o usuário logado.

Conferir: `schtasks /Query /TN "Tudo é Política - publicar" /V /FO LIST`, ou o app Agendador de Tarefas.
O `esteira doctor` faz essa consulta e mostra o item **tarefa de publicação**.

## Linux: systemd do usuário (ou cron)

Quando `systemctl --user` responde, a instalação usa um timer de usuário:

- `~/.config/systemd/user/tudo-e-politica-publicar.service`: `Type=oneshot`, `WorkingDirectory` na pasta
  `Automacao/` e `ExecStart` com o python do venv;
- `~/.config/systemd/user/tudo-e-politica-publicar.timer`: `OnActiveSec=1min` (1 minuto depois de ligar o timer,
  ou seja, ao entrar na sessão ou logo depois de instalar) e `OnUnitActiveSec=15min` (a cada 15 minutos);
- depois, `systemctl --user daemon-reload` e `systemctl --user enable --now tudo-e-politica-publicar.timer`.

Conferir: `systemctl --user list-timers` e `journalctl --user -u tudo-e-politica-publicar.service`.

O timer de usuário só roda com a sessão aberta. Para rodar com o computador ligado e ninguém logado:
`loginctl enable-linger $USER` (decisão do dono; o comando não faz isso).

Sem systemd do usuário (WSL sem systemd, contêiner), a reserva é o crontab. A instalação lê o crontab atual
(`crontab -l`), tira as linhas de uma instalação anterior, acrescenta duas no fim e grava com `crontab -`:

```
*/15 * * * * cd /caminho/Automacao && /caminho/Automacao/.venv/bin/python -m esteira publicar rodar >/dev/null # clipline: tudo-e-politica-publicar
@reboot cd /caminho/Automacao && /caminho/Automacao/.venv/bin/python -m esteira publicar rodar >/dev/null # clipline: tudo-e-politica-publicar
```

O resto do crontab fica como estava. O cron não sabe quando o usuário entra: `@reboot` roda quando o computador
liga. Os erros (saída de erro) seguem para o e-mail do cron, se houver um configurado.

**Credenciais no Linux.** O `keyring` usa o Secret Service (GNOME Keyring, KWallet). Sob o systemd do usuário, a
sessão já tem o barramento que ele precisa. Sob o cron, não: se o log mostrar erro de credencial, acrescente
`DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<seu uid>/bus` no começo do crontab, ou prefira o systemd.

## macOS: launchd

Um LaunchAgent em `~/Library/LaunchAgents/clipline.tudo-e-politica.publicar.plist`:

- `ProgramArguments`: o python do venv com `-m esteira publicar rodar`;
- `WorkingDirectory`: a pasta `Automacao/`;
- `RunAtLoad`: roda ao carregar, ou seja, ao entrar na sessão;
- `StartInterval`: 900 segundos (15 minutos).

Depois de gravar o arquivo, a instalação roda `launchctl bootout gui/<uid>/clipline.tudo-e-politica.publicar` (tira
a versão anterior; falhar aqui é normal na primeira vez) e `launchctl bootstrap gui/<uid> <plist>`.

Conferir: `launchctl print gui/$(id -u)/clipline.tudo-e-politica.publicar`.

O `keyring` usa o Chaves (Keychain) do macOS. Na primeira vez, o sistema pode pedir para liberar o acesso do python.

## Registro: `logs/publicar.log`

O próprio `publicar rodar` grava o registro em `Automacao/logs/publicar.log`, em UTF-8, uma linha por evento com data
e hora (`2026-11-15 18:00:03 01 instagram: publicado https://...`). Uma rodada sem nada para fazer não escreve
nada. Um erro que pare a rodada fica no log com o rastro do Python.

O arquivo gira por tamanho: passando de 1 MB, vira `publicar.log.1` (e o `.1` vira `.2`, até o `.5`, que é
apagado). Se o arquivo não puder ser renomeado (no Windows, quando outro programa o mantém aberto), a rodada segue
escrevendo no mesmo arquivo e tenta girar na próxima.

### Tarefa antiga (antes da rotação)

Até esta versão, a tarefa do Windows mandava a saída para o log pelo próprio `cmd`
(`... publicar rodar >> logs\publicar.log 2>&1`). Essa tarefa continua funcionando, mas o `cmd` mantém o arquivo
aberto a rodada inteira e ele nunca gira. Nesse caso o `publicar rodar` percebe que a saída já é o próprio log,
escreve só por ela (um escritor por arquivo) e acrescenta o aviso:

```
aviso: a tarefa agendada é antiga e grava este log pelo cmd (>>), sem rotação; reinstale com publicar instalar-tarefa --confirmar
```

O `esteira doctor` mostra o mesmo aviso no item **tarefa de publicação**. Reinstalar troca a linha da tarefa pela
nova, sem o redirecionamento.

## Trava

Uma rodada por vez: `publicar rodar`, `publicar agendar --confirmar`, `cancelar`, `marcar` e o painel usam a trava
`Automacao/publicar.trava`. Ela guarda o PID do processo e a hora de início:

```json
{"pid": 12345, "inicio": "2026-11-15T18:00:01-03:00"}
```

A trava só vale enquanto o processo existir. Se o computador desligou no meio de uma rodada, a próxima vê que o PID
não existe mais e segue, sem esperar. No Windows, a conferência usa `OpenProcess` e `GetExitCodeProcess`; no Linux
e no macOS, `os.kill(pid, 0)`, que só testa. O limite de 2 horas continua valendo como reserva (um PID reaproveitado
por outro programa, por exemplo). Uma trava sem PID, de uma versão anterior, vale só pelo limite de 2 horas.

## YouTube

### Envio em partes

O vídeo sobe pelo protocolo retomável da YouTube Data API, em partes de 8 MB lidas do disco uma a uma (o vídeo
inteiro nunca fica na memória). Se a conexão cair ou o YouTube responder 500, 502, 503 ou 504, o envio espera
(2, 4, 8, 16 e 32 s), pergunta até que byte o YouTube recebeu e segue dali. Depois de cinco falhas seguidas sem
avanço, desiste:

- se a última parte ainda não tinha ido, é um erro temporário: a fila tenta de novo na próxima rodada, do começo;
- se a última parte já tinha ido, o vídeo pode existir no canal: o item fica em **conferir**. Confira no Studio e
  use `publicar marcar` (feito ou reenviar). Assim um envio sem resposta não vira vídeo duplicado.

### Tags, playlist e miniatura (opcionais)

Na seção `## YouTube` do `post.md`, **antes** da linha `Descrição:` (o que vem depois dela é a descrição):

```markdown
## YouTube
Título: A Fórmula 1 faz sportswashing? #Shorts
Tags: política, Fórmula 1, sportswashing
Playlist: https://www.youtube.com/playlist?list=PL...
Miniatura: miniatura.jpg
Descrição:
...
```

- **Tags:** separadas por vírgula; repetidas saem. O YouTube aceita até 500 caracteres no total, contando as
  vírgulas e duas aspas para cada tag com espaço. Sem `<` nem `>`.
- **Playlist:** o ID (`PL...`) ou o link da playlist. O vídeo entra nela logo depois do envio. Pôr na playlist pede
  uma permissão que o envio não tem: conecte com `publicar conectar youtube --playlist` (o Google mostra a
  permissão de gerenciar a conta do YouTube). Sem ela, o vídeo sobe e o item mostra o aviso.
- **Miniatura:** um `.jpg` ou `.png` dentro da pasta do corte, até 50 MB. Em Shorts, o YouTube só aplica a miniatura
  depois de processar o vídeo: o envio consulta o processamento por até 5 minutos e então manda a imagem. Se a
  consulta falhar (por exemplo, se a permissão só de envio não bastar para ela), manda a imagem assim mesmo e avisa
  para conferir no Studio.

Os três aparecem no resumo do agendamento e entram na assinatura do item: mudar qualquer um depois de confirmar
faz a fila recusar o reenvio, como acontece com o título. Sem os campos, o `post.md`, o resumo e a assinatura são
os de sempre. O painel não edita esses campos e não mexe nessas linhas ao gravar o título ou a descrição.

Falha na playlist ou na miniatura nunca derruba a publicação: o vídeo já subiu, e o item fica com o estado do envio
(**privado** ou **publicado**) e o aviso no lugar do erro.

## TikTok: PKCE no login

O `publicar conectar tiktok` segue o Login Kit para desktop: manda `code_challenge` (SHA-256 do verificador, em
hexadecimal, como o TikTok pede para apps desktop) com `code_challenge_method=S256` e devolve o `code_verifier` na
troca do código pelo token. Contas já conectadas não precisam reconectar: o PKCE só vale no login.
