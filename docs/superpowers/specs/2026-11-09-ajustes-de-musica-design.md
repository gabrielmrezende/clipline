# Ajustes de música no painel

Data: 2026-11-09. Status: aprovado em conversa, aguardando revisão da spec.
Base: o painel de revisão (Fase 1), já no `master`
(`docs/superpowers/specs/2026-11-07-painel-de-revisao-design.md`).

## Objetivo

Deixar o dono do canal trocar a música de um corte e ajustar o volume pelo
painel, no notebook ou no celular, sem editar o `montagem.json` à mão. Ele
escolhe a faixa num catálogo feito para aquele episódio, ouve a faixa sozinha e
uma prévia de 15 s mixada com a voz, e o painel monta o `corte.mp4` de novo.

"Mais imagens no painel" é outro subprojeto, com spec própria, depois deste.

### Critérios de sucesso

1. Na tela do corte, o dono escolhe outra faixa e outro volume e, sem sair do
   painel, recebe um `corte.mp4` novo com essa música.
2. Ele ouve cada faixa sozinha e uma prévia de 15 s com a voz antes de montar.
3. As faixas que o Claude escolheu para o episódio aparecem primeiro, com o
   motivo de cada uma.
4. Depois da troca, o crédito no `post.md` é o da faixa nova, e o
   `publicar agendar` aceita o post sem edição manual.
5. `corte.mp4`, `montagem.json` e o crédito no `post.md` nunca ficam falando de
   músicas diferentes, nem quando a montagem falha.
6. Um corte que já tinha vídeo final avisa antes e, depois, aparece como
   "vídeo final desatualizado".

### Fora deste subprojeto

Corte sem música (a regra do canal é música em todos os cortes), desfazer com
versões antigas do `corte.mp4`, buscar faixas novas no incompetech, mudar o
clima do corte, imagens.

## Catálogo do episódio

- Na etapa 6 do `docs/operacao.md` (música), o Claude grava
  `musicas-do-episodio.json` na pasta do episódio: de 8 a 12 faixas da
  biblioteca atual (`musicas/catalogo.json`), escolhidas pelo tom do episódio.
  Formato:

  ```json
  {"faixas": [{"arquivo": "tenso/Ice Flow.mp3", "motivo": "tensão contida, combina com geopolítica"}]}
  ```

  `arquivo` é o mesmo campo `arquivo` do `catalogo.json` (relativo a
  `musicas/`).
- O texto novo do `operacao.md` é mostrado ao dono do canal para aprovação
  antes de ser salvo.
- `musica.ler_musicas_do_episodio(pasta: Path, catalogo: list[Faixa]) ->
  tuple[list[tuple[Faixa, str]], list[str]]` devolve as faixas da lista que
  existem no catálogo, na ordem do arquivo, com o motivo, e os avisos:
  - arquivo ausente: lista vazia, sem aviso;
  - arquivo ilegível: lista vazia e o aviso `musicas-do-episodio.json ilegível`;
  - faixa fora do catálogo: ignorada, com o aviso
    `faixa fora do catálogo: <arquivo>`.

## Trocar a música: fluxo

1. O dono escolhe a faixa (do catálogo do episódio ou da biblioteca) e o volume
   (`-30` a `-18` dB, de 1 em 1, os limites atuais de `receita.py`).
2. O painel pede `POST .../cortes/{n}/musica`. A API valida faixa e volume e
   põe um pedido na fila. Um corte só pode ter um pedido ativo (na fila ou
   montando).
3. Quando o pedido chega a vez, o trabalhador da fila:
   1. lê e guarda em memória o `montagem.json` atual;
   2. grava nele a música nova: `Musica(arquivo=str(MUSICAS / faixa.arquivo),
      volume_db, titulo=faixa.titulo, credito=faixa.credito)`;
   3. chama `montar.montar_episodio(pasta, numeros={n}, forcar=True)`;
   4. **se o resultado começar com `ok`:** chama `post.trocar_credito` (ver
      abaixo) e registra a faixa no `uso.json` com a chave
      `"<episódio>/<pasta do corte>"`, como `musica.atualizar_musica` faz hoje;
      o pedido termina `pronto`, com os avisos de `trocar_credito`;
   5. **se der erro:** grava de volta o `montagem.json` guardado; `corte.mp4` e
      `post.md` ficam com a música antiga; o pedido termina `erro`, com a
      mensagem.
- A montagem nunca recebe `cartao` (a montagem do painel não refaz cartões de
  notícia).
- Se o `post.md` não existir, `trocar_credito` não roda e o pedido termina
  `pronto` com o aviso `post.md não encontrado: crédito não atualizado`.

## Troca do crédito no `post.md`

`post.trocar_credito(caminho: Path, antiga: Musica, nova: Musica, base: Path |
None = None) -> list[str]`:

- Na descrição do YouTube, no Instagram e no TikTok, troca toda ocorrência
  exata de `antiga.credito` por `nova.credito`. Texto sem a ocorrência fica
  como está e gera o aviso `<rede>: crédito antigo não encontrado; confira o
  crédito`, com `<rede>` em `youtube`, `instagram` ou `tiktok`.
- Na seção `## Música`, troca a linha que começa com `Crédito:` pelo crédito
  novo e, na linha que começa com `Faixa:`, troca `antiga.titulo` por
  `nova.titulo`. Seção ou linha ausente: aviso `seção Música não atualizada`.
- Mesma rede de segurança de `gravar_textos`: fins de linha preservados linha a
  linha, o texto novo é relido antes do `os.replace` e precisa ter exatamente
  os campos esperados e as outras seções só de leitura intactas (todas, exceto
  `Música`); se não bater, `ErroPost` e nada é gravado. Mesma trava de gravação
  do PUT do post (`_TRAVA_GRAVACAO`), para não correr junto com uma edição.
- Faixa igual à anterior (só o volume mudou): o `post.md` não é tocado.

## Prévia de 15 s

`render.gerar_previa(receita: Receita, video: Path, musica: Musica, inicio:
float, saida: Path, duracao: float = 15.0) -> Path`:

- `inicio` é o segundo do corte (o tempo do player do `corte.mp4`). A função
  converte esse tempo para os trechos do episódio original pelas `faixas` da
  receita e recorta a voz de `inicio` até `inicio + duracao` (ou até o fim do
  corte).
- Mixa a música com o mesmo filtro do corte final (`_filtro_musica`: volume,
  fades, abaixamento da música quando há voz), para a prévia soar igual ao
  corte.
- Só áudio, AAC em `.m4a`. Saída em `<pasta do corte>/trabalho/previa-musica.m4a`,
  regravada a cada pedido, por `garantir_escrita`.
- Usa o ffmpeg de `Automacao/bin/`, como o resto da esteira, com tempo limite
  de 60 s.
- O vídeo original é lido do `episodio.json` do episódio e nunca é escrito.

## Fila de montagem

`esteira/painel/fila.py`:

- `class Fila`: `__init__(montar: Callable[[Path, int], str], relogio)`, um
  único trabalhador (`threading.Thread`, daemon) e uma `queue.Queue`.
- `pedir(pasta_episodio: Path, numero: int, faixa: Faixa, volume_db: float) ->
  Pedido`; levanta `PedidoAtivo` se o corte já tem pedido na fila ou montando.
- `Pedido`: `id` (texto curto aleatório), `episodio`, `numero`, `estado`
  (`na fila`, `montando`, `pronto`, `erro`), `mensagem`, `avisos`, `criado`,
  `terminado`.
- `pedidos() -> list[Pedido]` (os 50 mais recentes) e `pedido(id) -> Pedido`.
- A fila vive na memória do processo. O trabalhador grava a música nova no
  `montagem.json` só imediatamente antes de montar e o restaura em `finally`
  se a montagem não terminar com `ok` (inclusive por exceção).
- Se o processo do painel morrer no meio de uma montagem, o pedido é perdido e
  o `finally` não roda: o `montagem.json` pode ficar com a música nova e o
  `corte.mp4` ausente (o `montar` apaga o arquivo antes de renderizar). O
  painel mostra o corte como `corte não montado`, e basta escolher a música e
  montar de novo. Isso é aceito.
- O app cria uma `Fila` por processo (`app.state.fila`), com a função real de
  montar; os testes passam uma falsa.

## API nova

| Método e rota | Faz |
|---|---|
| `GET /api/episodios/{ep}/musicas` | `{do_episodio: [{arquivo, titulo, clima, duracao, motivo}], biblioteca: {clima: [{arquivo, titulo, duracao}]}, avisos}` |
| `GET /api/musicas/{clima}/{arquivo}` | a faixa mp3, só se `"{clima}/{arquivo}"` estiver no `catalogo.json`; com range |
| `GET .../cortes/{n}/musica` | `{atual: {arquivo, titulo, volume_db} | null, anterior: {…} | null, pedido: Pedido | null}` |
| `POST .../cortes/{n}/musica/previa` | `{arquivo, volume_db, inicio}` → `audio/mp4` (o `.m4a`) |
| `POST .../cortes/{n}/musica` | `{arquivo, volume_db}` → 202 `Pedido`; 409 `PedidoAtivo`; 422 faixa fora do catálogo ou volume fora de -30 a -18 |
| `GET /api/tarefas` | pedidos recentes |
| `GET /api/tarefas/{id}` | um pedido; 404 se não existir |

- `anterior` é a música do último pedido `pronto` daquele corte nesta execução
  do painel (memória); `null` depois de reiniciar.
- Todas as rotas passam pelo login quando o painel roda com `--rede`, e pelos
  mesmos tratadores de erro (403 caminho, 404, mensagens em português).

## Selo "vídeo final desatualizado"

- Um corte com vídeo final cujo arquivo mais novo em `video-final/` é mais
  antigo que o `corte.mp4` ganha o selo `vídeo final desatualizado`.
- Prioridade dos selos: `erro`, `vídeo final desatualizado`, `com alerta`,
  `sem vídeo final`, `pronto`.
- Calculado pelas datas dos arquivos (`st_mtime`), sem arquivo novo.
- O frontend mostra ícone e texto, como os outros selos.

## Telas

Na tela do corte, um bloco **Música** entre os players e o editor do post:

- **Agora:** `<título> · <volume> dB`; depois de uma troca nesta sessão,
  também `Música anterior: <título>, volume <v> dB`.
- **Faixas:** primeiro `Do episódio` (com o motivo), depois `Biblioteca`,
  agrupada por clima, com os grupos recolhidos. Cada faixa: botão ▶ (toca a
  faixa sozinha; tocar outra para a anterior) e botão `Escolher`.
- **Volume:** controle deslizante de -30 a -18, passo 1, com as pontas
  `mais baixa` e `mais alta` e o valor em dB.
- **Prévia:** botão `Ouvir prévia (15 s)`, a partir do tempo atual do player do
  corte (`a partir de 0:42`), ou de 0:00 se o player não foi tocado; toca o
  áudio devolvido.
- **Montar:** botão `Montar com esta música`.
  - Com vídeo final, antes: confirmação `Este corte já tem vídeo final. O vídeo
    final não muda; você vai precisar refazer no CapCut. Montar mesmo assim?`.
  - Andamento: `Na fila`, `Montando…`, `Pronto: o corte.mp4 foi atualizado.`,
    `Erro: <mensagem>` com o botão `Tentar de novo`; avisos de crédito
    listados abaixo.
  - Enquanto há pedido ativo, os controles de música daquele corte ficam
    desabilitados. O painel consulta o pedido a cada 2 s até terminar.
- **Depois de pronto:** o player recarrega o `corte.mp4`; o editor do post
  recarrega se não houver rascunho não salvo; se houver, mostra
  `O crédito da música mudou no post.md` e o fluxo de conflito existente cuida
  do resto.
- Na grade do episódio, cartão com pedido ativo mostra `montando…`.

## Erros

- Nenhuma falha de leitura derruba a tela (mesma regra do painel).
- Montagem com erro: `montagem.json` restaurado, mensagem do `montar` no
  pedido.
- `trocar_credito` com `ErroPost`: o corte já foi montado; o pedido termina
  `pronto` com o aviso `crédito não atualizado: <mensagem>`, e o editor mostra
  o aviso de crédito que já existe.
- Prévia: ffmpeg ausente, falha ou tempo esgotado → resposta 422 com
  `{"detail": "Não consegui gerar a prévia: <motivo>"}` (nunca 500).

## Testes

- `musica.ler_musicas_do_episodio`: ausente, ilegível, faixa fora do catálogo,
  ordem.
- `post.trocar_credito`: os quatro lugares; crédito editado à mão (aviso, texto
  intacto); fins de linha mistos; seção Música ausente; só volume mudou (nada
  gravado); rede de segurança recusa sem gravar.
- `render.gerar_previa`: com o executor do ffmpeg falso, confere os trechos
  recortados para um `inicio` que cai no meio de uma faixa e o filtro de música
  igual ao do corte.
- `Fila`: ordem, um pedido ativo por corte (`PedidoAtivo`), montagem falsa com
  `ok` (crédito trocado, `uso.json` registrado), com `erro` (`montagem.json`
  restaurado, `post.md` intacto), exceção dentro da montagem (restaurado).
- API: listas de músicas, faixa fora do catálogo (422/404), volume fora (422),
  202 e 409, tarefas, prévia com gerador falso, login com `--rede`.
- Selo `vídeo final desatualizado` por datas.
- Frontend (Vitest): escolher faixa, um player tocando por vez, volume,
  prévia, confirmação com vídeo final, andamento até `pronto`, recarga do post
  sem rascunho e aviso com rascunho.
- Ponta a ponta (Playwright): trocar a música do episódio falso com montagem
  falsa e ver o crédito novo no editor.
