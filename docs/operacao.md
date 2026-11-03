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
faixa no `montagem.json`. O comando `musica` preenche ou recalcula a música de
receitas já preparadas (por exemplo, depois de mudar o clima do corte), sem
refazer o resto:

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

## 6. Destaques

Não marcar destaques. A legenda é toda branca.

## 7. Imagens

Ler `legenda.srt` de cada corte e gravar `pedidos.json` na pasta do corte, com
4 a 6 momentos. Os tempos ficam em segundos, na linha do tempo da legenda.
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

1. Buscar: `.venv\Scripts\python.exe -m esteira imagens buscar "<pasta do episódio>"`.
   Gera `candidatas/NN-M.jpg` em cada corte.
2. Escolher olhando as folhas. Em cada foto, gravar `"escolha": N` no
   `pedidos.json`, ou trocar para `"tipo": "ia"` com `prompt`, ou marcar
   `"descartar": true`.
3. Listar: `... imagens lista "<pasta do episódio>"`. Gera o `imagens.md` de
   cada corte, `lista-imagens.md` (nome, origem, licença e tamanho),
   `prompts-chatgpt.md` e `ia-entrada/`.
4. Pausa: o dono do canal aprova `lista-imagens.md` e gera as imagens de IA no
   ChatGPT. Ele salva as imagens em `ia-entrada/` na ordem dos prompts; a
   esteira usa a ordem de gravação dos arquivos.
5. Baixar: `... imagens baixar "<pasta do episódio>"`. Baixa as fotos, gera os
   cartões, encaixa as imagens de IA e atualiza as receitas.

Para trocar uma imagem: mudar o `pedidos.json` e rodar `lista` e `baixar` de
novo. Arquivo antigo em `imagens/` com o mesmo número trava o corte; remover
só com confirmação do dono do canal.

As imagens entram em corte seco, com zoom lento de cerca de 8%. Durante a
imagem, a legenda não aparece. O enquadramento é automático: vertical em tela
cheia, horizontal inteira sobre fundo desfocado.

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
