# Operação da esteira de cortes

Roteiro para o Claude Code. Rodar comandos a partir de `Automacao/`, com
`.venv\Scripts\python.exe -m esteira`.

Antes de sugerir qualquer coisa, ler todos os arquivos de `Contexto/`.
Nunca alterar pastas de episódios.

O dono do canal diz "faça os cortes do episódio X". O Claude Code segue as
etapas 1 a 10 sem pausa. A única aprovação humana é a da etapa 10, com o corte
pronto. Nada é publicado.

## 1. Transcrever

Use a versão publicada do episódio. Se houver dúvida, pergunte.

```bash
.venv\Scripts\python.exe -m esteira transcrever "<video>" --quadro "Entre Assuntos" --numero 3 --convidado "Arthur Cerqueira"
```

## 2. Escolher os cortes

Ler `transcricao/texto.md` e escolher até 8 a 10 cortes, conforme o episódio
permitir. Conferir em `transcricao/palavras.json` os tempos exatos. Ler o que
vem antes e depois de cada trecho para não mudar o sentido da fala.

Gravar `aprovados.json` com os cortes escolhidos pela esteira. Marcar
`"instagram": true` nos 4 mais fortes. O `clima` é um de quatro: `leve`,
`tenso`, `inspirador` ou `reflexivo`. A etapa 3 acusa qualquer outro valor.
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

## 3. Validar e enquadrar

```bash
.venv\Scripts\python.exe -m esteira validar "<pasta do episódio>"
.venv\Scripts\python.exe -m esteira planos "<pasta do episódio>"
```

O comando `planos` cria `enquadramento.json` e `planos.jpg` em cada corte.
Abra a folha e leia a transcrição para saber quem fala. Em
`enquadramento.json`, cada plano tem `inicio`, `fim`, `x`, `y` e `zoom`, com
`x` e `y` entre 0 e 1 na imagem original:

- Close: deixar quem fala centralizado.
- Câmera aberta: dar zoom em quem fala. No convidado, usar zoom leve, perto de
  1,35. Se a fala mudar dentro do plano, dividir o plano nesse momento.
- Duas pessoas: manter as duas só quando a troca fizer parte da cena.

Evite zoom acima de 2, porque o episódio é 1080p. Não parar para aprovação.

## 4. Preparar

```bash
.venv\Scripts\python.exe -m esteira preparar "<pasta do episódio>"
```

Cria `montagem.json`, `legenda.srt` e `registro.json` em cada corte. Use
`--numero N` para um corte só e `--forcar` para refazer.

Se o enquadramento mudar depois do `preparar`, rodar `preparar --numero N
--forcar` (perde os destaques) ou editar `planos` no `montagem.json`.

## 5. Música

A música é escolhida pelo clima do corte. O `preparar` já faz isso e grava a
faixa no `montagem.json`. Para trocar só a música de uma receita que já
existe, sem refazer o resto:

```bash
.venv\Scripts\python.exe -m esteira musica "<pasta do episódio>" --numero N
```

O comando mostra a faixa de cada corte, ou `sem música para o clima <clima>`.
Sem faixa para o clima, o corte sai sem música e a revisão avisa. Se a
biblioteca ainda não existir, ver "Biblioteca de música" no fim deste roteiro.

## 6. Destaques

Não marcar destaques. A legenda é toda branca.

## 7. Imagens

Até a Parte 3 (busca automática), as imagens são manuais. Ler `legenda.srt` e
escrever `imagens.md` com 4 a 8 sugestões, usando os tempos do corte final.

```markdown
## 2. 00:00:18 a 00:00:21 — Gripen
Tipo: foto livre | vídeo | notícia | ilustração de IA
Fala: "..."
Origem: link
Autor e licença: ...
```

Regras:
- Pessoa real: foto livre ou oficial, depois o próprio vídeo. Agência só por decisão do canal.
- Nunca gerar imagem de IA de pessoa real.
- Nunca gerar página imitando veículo real.
- Notícia: conferir a fonte original e gerar cartão:

```bash
.venv\Scripts\python.exe -m esteira cartao --manchete "..." --veiculo "..." --data "..." --saida "<pasta do corte>\imagens\noticia-1.png"
```

- Objeto ou cenário: escrever o prompt para geração manual.
- Baixar arquivos somente depois da aprovação, informando nome, origem e tamanho.

Imagens usadas vão para `imagens/` na pasta do corte, numeradas como em
`imagens.md` (`01-nome.jpg`). Depois, registrar no `montagem.json`:

```bash
.venv\Scripts\python.exe -m esteira imagens "<pasta do episódio>"
```

As imagens entram em corte seco, com zoom lento de cerca de 8%. O motor faz o
zoom. Durante a imagem, a legenda não aparece.

Para imagens de IA, gerar `prompts-chatgpt.md` na pasta do episódio, com os
prompts numerados, e criar a pasta `ia-entrada/`. O dono do canal gera as
imagens no ChatGPT e baixa na ordem. O enquadramento de cada imagem é
automático: vertical em tela cheia, horizontal inteira sobre fundo desfocado.

## 8. Montar

```bash
.venv\Scripts\python.exe -m esteira montar "<pasta do episódio>"
```

Gera `final.mp4` em cada corte, com legenda, imagens, música (se houver) e
encerramento. Um corte com erro não impede os outros: ver `registro.json`.
Se `final.mp4` já existir, a esteira não sobrescreve sem `--forcar`. Antes de
usar `--forcar`, perguntar ao dono do canal.

## 9. Textos e calendário

Escrever `post.md` com título e descrição do YouTube, textos de Instagram e
TikTok, aviso de IA quando houver imagem de IA e a seção "Publicação sugerida".

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

## 10. Revisão e aprovação

```bash
.venv\Scripts\python.exe -m esteira revisao "<pasta do episódio>"
```

Gera `revisao.md` na pasta do episódio, com um bloco por corte: link do
`final.mp4`, título, redes, data, música, frase anterior e posterior ao trecho e
alertas. No fim, os descartados e o motivo.

O comando `revisao` regrava o arquivo; por isso, rodá-lo antes de acrescentar
à mão qualquer alerta.

Antes de parar, acrescentar aos alertas de cada corte os nomes que podem ter
saído errados na legenda, comparando com `Contexto/glossario.md`.

Parar e esperar a resposta do dono do canal. Esta é a única aprovação.

Depois da resposta, gravar `aprovacao.json` na pasta do episódio:

```json
{"cortes": [{"numero": 1, "status": "aprovado", "redes": ["youtube", "tiktok", "instagram"]}]}
```

`status` é `aprovado` ou `corrigir`. `redes` lista onde o corte pode sair.
Corte com `instagram: true` leva as três redes; os demais, `youtube` e
`tiktok`. Gravar o arquivo não publica nada.

## Corrigir um corte

Alterar só o `montagem.json` daquele corte (legenda, destaque, imagens,
faixas) e remontar só ele:

```bash
.venv\Scripts\python.exe -m esteira montar "<pasta do episódio>" --numero N --forcar
```

Depois, gerar `revisao` de novo e mostrar o corte ao dono do canal.

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
