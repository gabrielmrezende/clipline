# Imagens no vídeo (Fase B)

Data: 2026-11-09. Status: decisões tomadas pelo Claude com a autorização do dono do
canal ("Te autorizo a tomar as melhores decisões por mim"), sem rodada de perguntas.
Base: Fase A (`docs/superpowers/specs/2026-11-09-imagens-no-painel-design.md`), já no
`master` (f354520).

## Objetivo

A esteira põe no próprio `corte.mp4` as imagens prontas de cada momento (fotos
baixadas, cartões de notícia e imagens de IA geradas). O dono assiste no painel,
troca o que quiser, monta de novo com um botão e aprova com outro. O CapCut vira
opcional.

### Critérios de sucesso

1. `esteira montar` e o painel montam o corte com uma imagem por momento pronto,
   seguindo `Contexto/estilo-de-imagens.md`: de 2 a 5 s, no tempo da fala; vertical
   em tela cheia; horizontal ou quadrada inteira na faixa central, sobre ela mesma
   ampliada e desfocada; sem legenda durante a imagem; corte seco; zoom lento de 8%,
   alternando aproximação e afastamento.
2. Um momento sem imagem pronta fica fora do vídeo, com um alerta que diz o motivo.
   O corte não falha por causa disso.
3. No painel, o dono escolhe qual opção pronta de cada momento vai para o vídeo,
   monta o corte de novo e aprova o vídeo.
4. O botão Aprovar copia o `corte.mp4` para `video-final/`. A esteira nunca apaga
   nem substitui um vídeo que o dono pôs lá.
5. O `agendar` sabe quais imagens de IA estão no vídeo aprovado pelo painel e recusa
   o agendamento sem o aviso de IA nos textos. O resumo lista os créditos das fotos
   que estão no vídeo.
6. O nome dos arquivos e a chave do momento usam um tempo só (pendência da Fase A).

### Fora deste subprojeto

Criar momentos ou mudar tempos pelo painel; pôr o aviso de IA ou os créditos no
`post.md` sozinho; trava entre o painel e o `esteira montar` rodado pela CLI no mesmo
corte (pendência antiga); gerar imagem de IA durante a montagem; baixar qualquer coisa
durante a montagem.

## Decisões

### D1. Qual tempo vale

- **Chave e nome de arquivo:** o tempo proposto, o que está no `pedidos.json`
  (`MMSS-slug(nome)`, como o painel e o `ia.json` já fazem). É um identificador: não
  muda quando o ajuste de 2 a 5 s mexe no início.
- **Tela:** o tempo ajustado (`ajustar_tempos`, numa cópia), calculado sempre do mesmo
  jeito a partir do `pedidos.json`. Vale para o vídeo, para o `guia.md` e para o
  botão ▶ do cartão.
- Corrige o `_sugerir_um`, que hoje nomeia as fotos e os cartões pelo tempo ajustado, e
  o `guia.md`, que procura as imagens de IA pela chave ajustada. Foto baixada antes da
  correção com o nome ajustado (só acontece quando o ajuste puxa o início para trás)
  deixa de aparecer como pronta e precisa ser baixada de novo.

### D2. Qual imagem de cada momento entra

- Campo novo no momento: `no_video: str = ""`, o nome de um arquivo pronto do momento.
  Vazio é o padrão:
  - foto: a primeira opção pronta, na ordem das escolhas (a melhor primeiro);
  - IA: a versão mais nova;
  - notícia: o cartão.
- Arquivo pronto é o mesmo que o painel já marca como "Pronta":
  - foto: `<chave>-K.jpg` gravado pela esteira (`sugeridas.json`), que ainda é a
    candidata escolhida em K (`creditos.json`);
  - notícia: `<chave>.png` gravado pela esteira;
  - IA: as versões `<chave>-ia-K.jpg` do `ia.json` e as pagas sem registro.
- `no_video` que não está mais pronto: entra o padrão, com alerta.
- Momento descartado (pelo dono ou pelo ajuste de tempo) não entra.
- A lógica de "pronto" sai de `painel/rotas_imagens.py` e vai para um módulo comum,
  usado pelo painel e pela montagem.

### D3. Montagem

- `esteira montar` sempre põe as imagens prontas. `--sem-imagens` monta sem elas (para
  quem quiser editar no CapCut a partir do corte limpo).
- O `registro.json` grava a lista do que entrou:
  `"imagens": [{"inicio", "fim", "arquivo", "tipo", "momento"}]`. O que ficou de fora vai
  para os alertas, por exemplo `imagem 0:52 Turistas fora do vídeo: IA ainda não gerada`.
- No `operacao.md`, a montagem passa para depois das imagens: a etapa 7 vira
  "Imagens" e a 8 vira "Montar". A pausa do download continua sendo a única.
- Painel: botão `Montar com as imagens` no bloco Imagens, com confirmação. Vira um
  pedido `montar` na fila. Ele usa a mesma proteção da troca de música: o `corte.mp4`
  de antes é guardado e volta se a montagem falhar ou o painel fechar no meio.
- Música e montagem são o mesmo tipo de trabalho na fila: o corte não aceita um
  pedido `montar` com uma troca de música ativa, nem o contrário (409
  `Este corte já está sendo montado.`).
- O bloco avisa `As imagens mudaram desde a última montagem.` quando a lista prevista
  é diferente da que está no `registro.json`.

### D4. Aprovação

- Botão `Aprovar este vídeo` na tela do corte, com confirmação. Copia o `corte.mp4`
  para `video-final/corte-aprovado.mp4` (cópia por arquivo temporário e troca no fim)
  e grava `trabalho/aprovado.json`:
  `{"arquivo", "tamanho", "modificado_ns", "data", "imagens"}`, com `imagens` copiado do
  `registro.json`.
- O arquivo em `video-final/` é "da esteira" só se tem o mesmo nome, tamanho e data
  de modificação do `aprovado.json`. Qualquer outro arquivo é do dono.
- Recusa (409), sem gravar nada:
  - há um vídeo do dono em `video-final/`: `video-final/ já tem um vídeo seu (<nome>).
    Para aprovar o corte da esteira, tire esse vídeo de lá.`;
  - o corte está sendo montado;
  - não há `corte.mp4` (422).
- Cópia da esteira mais antiga que o `corte.mp4` (o corte foi montado de novo): o
  botão vira `Aprovar de novo` e substitui só essa cópia.
- Cópia em dia: o botão some e aparece `Aprovado`.
- A regra "a esteira nunca grava em `video-final/`" passa a ser: "a esteira só grava em
  `video-final/` pelo botão Aprovar do painel, e só substitui a própria cópia; nunca
  apaga nem altera um vídeo do dono". Nem a CLI nem o Claude aprovam: aprovar é um
  ato do dono.

### D5. Publicação

- Vídeo de `video-final/` que é a cópia da esteira: o `agendar` usa as `imagens` do
  `aprovado.json`.
  - Com imagem de IA no vídeo: cada texto das redes escolhidas precisa ter o aviso
    "Algumas imagens utilizadas neste vídeo foram geradas por Inteligência Artificial
    (IA)."; sem ele, recusa com `<rede>: falta o aviso de IA`. O resumo mostra
    `Imagens de IA no vídeo: N (o aviso está nos textos).`
  - Sem imagem de IA no vídeo: nenhuma linha de IA, mesmo com imagens geradas no
    `ia.json`.
  - Com fotos: o resumo lista `Créditos das fotos no vídeo:` e uma linha por foto
    (autor, licença, link), tirada do `creditos.json`. Não bloqueia.
- Vídeo do CapCut, ou cópia da esteira sem a lista de imagens: continua a linha de hoje
  (`Este corte tem N imagens de IA geradas: confira se o vídeo final usa alguma e inclua
  o aviso.`).
- A mensagem de vídeo final desatualizado passa a ser `vídeo final mais antigo que o
  corte.mp4: aprove de novo no painel ou refaça no CapCut`.

## Montagem das imagens (render)

`renderizar_final(..., imagens=[...])` recebe a lista do D2 com os tempos de tela. Para
cada imagem, em ordem de tempo (posição `i`):

- entrada `-loop 1 -framerate 30 -t <duração> -i <arquivo>`;
- `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920`: os arquivos
  já são 1080x1920; isso só protege contra outro tamanho, sem distorcer;
- zoom de 8% com `perspective` por quadro (o código que a esteira usava até 05/11):
  `i` par aproxima (1,00 → 1,08) e `i` ímpar afasta (1,08 → 1,00);
- `overlay` com `enable='between(t,início,fim)'`, por cima do vídeo já legendado;
- a legenda é cortada nos intervalos das imagens (`ocultar_durante`, de volta ao
  `legenda.py`).

A imagem horizontal já sai do `preparar_foto` inteira na faixa central, sobre ela mesma
ampliada e desfocada, e o cartão de notícia já é 1080x1920. O zoom vale para o quadro
inteiro. O cartão tem margem de 80 px; com 8% de zoom, o texto continua a cerca de
40 px da borda.

## Módulo novo: `esteira/imagens_no_video.py`

- `prontas(m, chave, destino) -> list[str]`: os arquivos prontos do momento, na ordem
  de preferência (D2).
- `imagens_do_corte(destino) -> tuple[list[ImagemNoVideo], list[str]]`: lê o
  `pedidos.json` e a duração do `montagem.json`, ajusta os tempos numa cópia, escolhe
  um arquivo por momento e devolve a lista em ordem de tempo e os alertas. Sem
  `pedidos.json`: lista vazia e nenhum alerta. Com `pedidos.json` ilegível: lista vazia
  e o alerta `imagens: pedidos.json ilegível: <motivo>`.
- `ImagemNoVideo(inicio, fim, arquivo, tipo, momento)`, com `arquivo` relativo à pasta
  do corte (`imagens-sugeridas/<nome>`).

## Painel

### API

| Método e rota | Muda |
|---|---|
| `GET .../cortes/{n}/momentos` | cada momento ganha `no_video` (arquivo que vai entrar, ou `null`), `prontas` (arquivos prontos), `inicio_tela` e `fim_tela` (`null` se o ajuste descartou); a resposta ganha `no_corte` (lista do `registro.json`) e `montagem_desatualizada` |
| `PUT .../cortes/{n}/momentos/{chave}` | aceita `no_video` (`""` volta ao padrão); 422 se não for um arquivo pronto do momento |
| `POST .../cortes/{n}/montar` | corpo `{"confirmado": true}`; 202 com o pedido `montar`; 409 se o corte já está sendo montado |
| `GET .../cortes/{n}` | ganha `aprovacao`: `{"estado": "aprovar" \| "aprovar de novo" \| "aprovado" \| "bloqueado", "motivo"}` |
| `POST .../cortes/{n}/aprovar` | corpo `{"confirmado": true}`; 200 com a `aprovacao` nova; 409 ou 422 nos casos do D4 |

Todas passam pelo login com `--rede`, pelos tratadores de erro do painel e por
`garantir_escrita`.

### Telas

- **Cartão do momento:** mostra o tempo de tela (quando difere do proposto, também o
  proposto). O ▶ vai para o início da tela. Nas fotos prontas e nas versões de IA, a
  que vai para o vídeo leva o selo `No vídeo`; as outras prontas ganham o botão
  `Usar no vídeo`. Notícia mostra `No vídeo` no cartão pronto.
- **Bloco Imagens, topo:** botão `Montar com as imagens`, com a confirmação
  `Montar o corte de novo com N imagens? O corte.mp4 atual será substituído (leva cerca
  de 1 minuto).`. Andamento como na troca de música (o player sai da tela enquanto
  monta) e, ao terminar, o vídeo e o selo são recarregados. Aviso
  `As imagens mudaram desde a última montagem.` quando for o caso.
- **Tela do corte, junto do selo:** `Aprovar este vídeo` / `Aprovar de novo` /
  `Aprovado` / motivo do bloqueio. Confirmação: `Aprovar este corte? O corte.mp4 vai
  para video-final/ como corte-aprovado.mp4 e passa a ser o vídeo que o agendar publica.`
  Com montagem desatualizada, a confirmação começa por
  `As imagens mudaram desde a última montagem.`

## Regras do canal que mudam

Texto aplicado com a autorização do dono e listado no relatório final:

- `Contexto/estilo-de-imagens.md`: a esteira põe no corte as imagens prontas (a escolhida
  no painel ou a padrão); o CapCut é opcional.
- `Contexto/estilo-dos-cortes.md`, "Montagem" e "Revisão": a esteira coloca as imagens;
  a aprovação é o botão Aprovar do painel ou o vídeo do CapCut em `video-final/`.
- `docs/operacao.md`: troca das etapas 7 e 8, `--sem-imagens`, a nova regra de
  `video-final/`, o painel monta e aprova, e a mensagem nova do `agendar`.
- `docs/painel.md`: seções "Imagens no vídeo" e "Aprovar".

## Erros

- Imagem que não abre na montagem: o ffmpeg falha e o corte dá erro, como hoje. A
  lista só traz arquivos que existem.
- Falha da montagem pelo painel: o `corte.mp4` e o `registro.json` de antes voltam.
- Aprovar com o `corte.mp4` aberto no player: a cópia lê o arquivo (o Windows deixa) e
  a troca no fim é em `video-final/`. Se a troca falhar, o temporário é apagado e nada
  muda.
- `aprovado.json` ilegível: nada em `video-final/` é tratado como da esteira; o botão
  fica bloqueado se houver vídeo lá.

## Testes

- `imagens_no_video`: padrão de cada tipo, `no_video` válido e vencido, momento sem
  imagem pronta (alerta), descartado pelo dono e pelo ajuste, tempos ajustados,
  `pedidos.json` ausente e ilegível.
- `fluxo_imagens`: `sugerir` nomeia pela chave proposta mesmo quando o ajuste muda o
  início; `guia.md` acha a imagem de IA com o tempo ajustado.
- Render: filtro com uma entrada e um `overlay` por imagem, zoom alternado, legenda
  cortada; render real curto com uma imagem vertical e uma horizontal (quadro no meio
  da imagem igual à imagem, legenda ausente, duração certa).
- `montar`: com e sem imagens, `--sem-imagens`, `registro.json` com `imagens` e alertas.
- Painel: `momentos` com os campos novos, PUT `no_video` (válido, inválido, vazio),
  `montar` 202 e 409 cruzado com a música, `aprovar` (cópia, vídeo do dono, de novo,
  em dia, sem corte, durante a montagem), `aprovacao` no detalhe do corte.
- Fila: música e montagem bloqueiam uma à outra no mesmo corte.
- `agendar`: IA no vídeo sem aviso recusa; com aviso passa; sem IA no vídeo não mostra
  linha; créditos no resumo; vídeo do CapCut mantém a linha de hoje.
- Vitest: selo `No vídeo` e `Usar no vídeo`, botão `Montar com as imagens` com a
  confirmação e o aviso de desatualizada, estados do botão Aprovar.
- Conferência real: cópia de um corte do F1 em `Automacao/.superpowers/teste-fase-b/`
  (nunca no episódio real), com as fotos já baixadas e uma imagem de IA de teste.
  Montar pela CLI e pelo painel, conferir quadros no tempo das imagens (tela cheia,
  faixa central, sem legenda, zoom) e aprovar pelo painel na cópia.
