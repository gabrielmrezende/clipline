# Operação da esteira de cortes

Roteiro para o Claude Code. Rodar comandos a partir de `Automacao/`, com
`.venv\Scripts\python.exe -m esteira`.

Antes de sugerir qualquer coisa, ler todos os arquivos de `Contexto/`.
Nunca alterar pastas de episódios (`1 - Programas/`). A saída vai para
`2 - Cortes/<Quadro NN - Convidado>/`.

O dono do canal diz "faça os cortes do episódio X". O Claude Code segue as
etapas 1 a 10 e entrega cada corte como `corte.mp4`, sem imagens. As imagens
são colocadas pelo dono do canal no CapCut, a partir de `imagens-sugeridas/`.
O vídeo final dele fica em `video-final/`. A única pausa é a confirmação do
download das fotos (etapa 8). Nada é publicado.

## Pasta do corte

```
2 - Cortes/<Quadro NN - Convidado>/
  transcricao/   texto.md, palavras.json, vozes.json, pessoas.json, pessoas.jpg
  aprovados.json  candidatos.md  calendario.md  revisao.md
  NN-titulo/
    corte.mp4
    imagens-sugeridas/   guia.md, MMSS-nome-K.jpg (fotos), MMSS-nome.png (notícia)
    video-final/         do dono do canal; a esteira nunca grava nela
    post.md
    trabalho/            enquadramento.json, montagem.json, legenda.srt,
                         registro.json, pedidos.json, planos.jpg, candidatas/
```

`MMSS` é o início do momento no `corte.mp4` (`0112` = 1:12).

## 1. Transcrever

Use a versão publicada do episódio. Se houver dúvida, pergunte.

```bash
.venv\Scripts\python.exe -m esteira transcrever "<video>" --quadro "Entre Assuntos" --numero 3 --convidado "Arthur Cerqueira"
```

## 2. Vozes

Rodar uma vez por episódio, depois de `transcrever`. Separa quem fala por voz
(pyannote, na GPU). `--pessoas` é o número de pessoas à mesa (padrão: 3).

```bash
.venv\Scripts\python.exe -m esteira vozes "<video>" "<pasta do episódio>" --pessoas 3
```

Grava `transcricao/vozes.json`. Use `--forcar` para refazer.

O token do Hugging Face vem só da variável de ambiente `HF_TOKEN`. Nunca
gravar o token em arquivo, log ou mensagem. A conta e o aceite dos termos do
modelo são do dono do canal. Sem `HF_TOKEN` ou com falha do modelo, o comando
para com mensagem clara. Nesse caso, avisar o dono do canal e esperar.

## 3. Escolher os cortes

Ler `transcricao/texto.md` e escolher até 8 a 10 cortes, conforme o episódio
permitir. Conferir em `transcricao/palavras.json` os tempos exatos. Ler o que
vem antes e depois de cada trecho para não mudar o sentido da fala.

Gravar `aprovados.json` com os cortes escolhidos pela esteira. Marcar
`"instagram": true` nos 4 mais fortes. O `clima` é um de quatro: `leve`,
`tenso`, `inspirador` ou `reflexivo`. A etapa 4 acusa qualquer outro valor.
Os demais cortes vão só para TikTok e Shorts.

```json
{"cortes": [{"numero": 1, "titulo": "...", "inicio": 724.12, "fim": 801.40, "clima": "leve", "instagram": true}]}
```

Registrar em `candidatos.md` os trechos descartados e o motivo:

```markdown
## 3. Título em forma de pergunta
Tempo: 00:12:04 a 00:13:21 (1min17)
Abertura: "..."
Fim: "..."
Por que funciona: ...
Riscos: ...
Clima da música: ...
Descartado: motivo (só nos descartados)
```

## 4. Validar

```bash
.venv\Scripts\python.exe -m esteira validar "<pasta do episódio>"
```

## 5. Enquadrar

```bash
.venv\Scripts\python.exe -m esteira planos "<pasta do episódio>"
```

O comando `planos` faz tudo sozinho: detecta rostos, liga cada voz a uma
pessoa e gera o `trabalho/enquadramento.json` de cada corte. Dentro de cada
plano de câmera, divide onde a voz troca. A troca é corte seco.

Regras que a esteira aplica:
- Zoom em 4 níveis: 1,0 / 1,35 / 1,7 / 2,0. Nunca acima de 2,0.
- Meta: rosto com 28% da altura da faixa do vídeo.
- Turno de voz com menos de 2 s não divide. Nenhum trecho fica com menos de 2 s.
- Quem fala fora da tela, com um rosto só: enquadra esse rosto. Com vários
  rostos: zoom 1,0 no centro do grupo. Sem rosto: centro, zoom 1,0 e alerta.
- Fala sobreposta por mais de 1 s: mantém o enquadramento anterior e alerta.

Os alertas vão para o `registro.json` e aparecem no `revisao.md`.

Conferir, sem parar o fluxo:

1. `transcricao/pessoas.jpg`: rosto, voz e tempo de fala de cada pessoa.
   Preencher `nomes` em `transcricao/pessoas.json` (`{"P1": "Nome"}`). Se uma
   voz estiver ligada à pessoa errada, corrigir a `ligacao` no mesmo arquivo.
2. `trabalho/planos.jpg` de cada corte: cada trecho com uma caixa no rosto
   escolhido, o nome de quem fala e as primeiras palavras da fala. Conferir
   todas as folhas.

Se algo estiver errado, editar `trabalho/enquadramento.json` (cada plano tem
`inicio`, `fim`, `x`, `y` e `zoom`, com `x` e `y` entre 0 e 1 na imagem
original) e seguir.

Rodar `planos` de novo não sobrescreve `enquadramento.json` nem `pessoas.json`
editados à mão. Só `--forcar` refaz. Antes de usar `--forcar`, perguntar ao
dono do canal. Use `--numero N` para um corte só.

## 6. Preparar

```bash
.venv\Scripts\python.exe -m esteira preparar "<pasta do episódio>"
```

Cria `montagem.json`, `legenda.srt` e `registro.json` em `trabalho/`. A
música sai do clima do corte. Use `--numero N` para um corte só e `--forcar`
para refazer.

Se o enquadramento mudar depois do `preparar`, editar o
`enquadramento.json` e remontar (ver "Corrigir um corte").

### Música

O `preparar` já grava a faixa no `montagem.json`. O comando `musica` preenche
ou recalcula a música de receitas já preparadas (por exemplo, depois de mudar
o clima do corte), sem refazer o resto:

```bash
.venv\Scripts\python.exe -m esteira musica "<pasta do episódio>" --numero N
```

O comando mostra a faixa de cada corte, ou `sem música para o clima <clima>`.
Sem faixa para o clima, o corte sai sem música e a revisão mostra
`Música: nenhuma (sem música para o clima <clima>)`. Se a biblioteca ainda não
existir, ver "Biblioteca de música" no fim deste roteiro.

O comando `musica` não serve para escolher outra faixa. Para trocar a faixa de
um corte, editar `arquivo`, `titulo` e `credito` da `musica` no `montagem.json`
(usando uma faixa do `musicas/catalogo.json`) e remontar o corte.

A legenda é toda branca. Não marcar destaques.

## 7. Montar

```bash
.venv\Scripts\python.exe -m esteira montar "<pasta do episódio>"
```

Gera `corte.mp4` em cada corte, com legenda, cortes de pausa, música (se
houver), zoom em quem fala e encerramento. Não insere imagens. Cria
`imagens-sugeridas/` e `video-final/` vazias. Um corte com erro não impede os
outros: ver `registro.json`.

Se `corte.mp4` já existir, a esteira não sobrescreve sem `--forcar`. Antes de
usar `--forcar`, perguntar ao dono do canal.

A pasta `video-final/` é do dono do canal. A esteira nunca grava, apaga ou
altera nada nela, nem com `--forcar`.

## 8. Imagens sugeridas

Ler `trabalho/legenda.srt` de cada corte e gravar `trabalho/pedidos.json` com
4 a 6 momentos. Os tempos ficam em segundos, na linha do tempo do `corte.mp4`.
Todo momento tem `nome`, um rótulo curto.

```json
{"momentos": [
  {"inicio": 12.4, "fim": 15.8, "fala": "...", "tipo": "foto", "nome": "Yas Marina", "busca": "Yas Marina Circuit"},
  {"inicio": 40.0, "fim": 43.0, "fala": "...", "tipo": "noticia", "nome": "Manchete", "titulo": "...", "veiculo": "...", "data": "..."},
  {"inicio": 61.2, "fim": 64.0, "fala": "...", "tipo": "ia", "nome": "Chuva", "prompt": "..."}
]}
```

Regras:
- Pessoa real: foto livre ou oficial, depois o próprio vídeo. Agência só por decisão do canal.
- Nunca gerar imagem de IA de pessoa real. A esteira recusa prompt com nome de pessoa do glossário.
- Nunca gerar página imitando veículo real. Notícia: conferir a fonte original; a esteira gera o cartão do canal.
- IA: só o prompt, que vai no `guia.md`. A esteira não recebe nem prepara imagem de IA.

Passos:

1. Buscar (não baixa as fotos finais): `.venv\Scripts\python.exe -m esteira imagens buscar "<pasta do episódio>"`.
   Gera `trabalho/candidatas/` e as folhas de cada corte.
2. Escolher olhando a foto, não o título. Em cada foto, gravar
   `"escolhas": [N, M]` no `pedidos.json`: de 1 a 3 números, a melhor primeiro,
   sem repetir e dentro da faixa das candidatas. Ou trocar para `"tipo": "ia"`
   com `prompt`, ou marcar `"descartar": true`. Escolha inválida dá erro claro
   no momento; os outros cortes seguem.
3. Resumo: `... imagens resumo "<pasta do episódio>"`. Mostra quantas fotos,
   quantos MB e a origem (Wikimedia Commons). O `resumo` não baixa nada.
4. Pausa: mostrar o resumo ao dono do canal e pedir a confirmação do download.
   Esta é a única pausa do fluxo. Só seguir com um sim claro.
5. Sugerir: `... imagens sugerir "<pasta do episódio>"`. Baixa as fotos
   escolhidas, prepara em 1080x1920, grava em `imagens-sugeridas/`, gera os
   cartões de notícia e o `guia.md`.

Use `--numero N` em qualquer passo para um corte só. Para trocar uma escolha,
mudar o `pedidos.json`, rodar `resumo`, pedir a confirmação e rodar `sugerir`
de novo.

Preparo das fotos: vertical (pelo menos 1,5 vez mais alta que larga) em tela
cheia; horizontal ou quadrada inteira na faixa central, sobre a própria
imagem ampliada e desfocada. Foto que falhar no download vira bloco com
"Sem imagem: motivo" no `guia.md`.

O `guia.md` traz o segundo exato de cada imagem, a fala, os arquivos e os
créditos das fotos. O dono do canal insere as imagens no CapCut.

## 9. Textos e calendário

Escrever `post.md` com título e descrição do YouTube, textos de Instagram e
TikTok e a seção "Publicação sugerida". O `post.md` sai sem o aviso de IA e
sem os créditos das fotos: os dois são decididos na publicação, a partir do
vídeo final em `video-final/`.

A seção "Música" traz a faixa usada e o crédito exato da receita
(`credito` no `montagem.json`). O mesmo crédito entra na descrição do YouTube
e nos textos de Instagram e TikTok. Não buscar música no CapCut. Corte sem
música não leva crédito.

Sempre gerar `calendario.md` na pasta do episódio, sem esperar pedido:
- TikTok e Shorts: todos os cortes, 1 a 2 por dia.
- Instagram: só os cortes com `instagram: true`, nos horários fixos de
  `Contexto/redes-e-publicacao.md`.
- Tudo antes do próximo episódio. Quando a data dele for conhecida, nenhum corte
  do episódio atual pode ficar nessa data ou depois dela.
- Começar pelos cortes mais amplos e informar o motivo da ordem.
- Se houver métricas novas, usar esses dados e dizer de onde vieram. Nunca
  afirmar que um horário é garantidamente o melhor.

Gravar a data de cada corte no campo `data` de `aprovados.json`.

## 10. Revisão

```bash
.venv\Scripts\python.exe -m esteira revisao "<pasta do episódio>"
```

Gera `revisao.md` na pasta do episódio, com um bloco por corte: links do
`corte.mp4` e do `guia.md`, título, redes, data, música, frase anterior e
posterior ao trecho, alertas de quem fala e se `video-final/` está vazia. No
fim, os descartados e o motivo.

O comando `revisao` regrava o arquivo; por isso, rodá-lo antes de acrescentar
à mão qualquer alerta.

Antes de parar, acrescentar aos alertas de cada corte os nomes que podem ter
saído errados na legenda, comparando com `Contexto/glossario.md`.

Parar e esperar o dono do canal. Ele coloca as imagens no CapCut e salva o
vídeo em `video-final/`. Corte sem vídeo ali não foi aprovado. Não existe
`aprovacao.json`. Nada é publicado.

## Corrigir um corte

Para zoom ou quem fala errado: editar `trabalho/enquadramento.json` do corte.
Para legenda, faixa ou outro ajuste: editar `trabalho/montagem.json`. Depois,
remontar só esse corte:

```bash
.venv\Scripts\python.exe -m esteira montar "<pasta do episódio>" --numero N --forcar
```

Perguntar ao dono do canal antes de usar `--forcar`. Depois, rodar `revisao`
de novo e mostrar o corte.

Correção que vale para os próximos cortes vira regra em `Contexto/`, com
aprovação. Nomes errados da transcrição vão para `Contexto/glossario.md`.

## Biblioteca de música

As faixas ficam em `Automacao/musicas/`, por clima, com `catalogo.json`.
Só entra música aprovada pelo dono do canal.

1. Gerar a proposta (não baixa músicas):

```bash
.venv\Scripts\python.exe -m esteira musicas propor
```

2. Mostrar `musicas/proposta.md` ao dono do canal e esperar a aprovação.
3. Depois da aprovação, informar nome, origem e tamanho e baixar:

```bash
.venv\Scripts\python.exe -m esteira musicas baixar
```

Faixa que falhar fica fora do catálogo e o comando informa. Faixa já baixada
não é baixada de novo.
