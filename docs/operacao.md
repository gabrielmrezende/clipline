# Operação da esteira de cortes

Roteiro para o Claude Code. Rodar comandos a partir de `Automacao/`, com
`.venv\Scripts\python.exe -m esteira`.

Antes de sugerir qualquer coisa, ler todos os arquivos de `Contexto/`.
Nunca alterar pastas de episódios.

## 1. Transcrever

Use a versão publicada do episódio. Se houver dúvida, pergunte.

```bash
.venv\Scripts\python.exe -m esteira transcrever "<video>" --quadro "Entre Assuntos" --numero 3 --convidado "Arthur Cerqueira"
```

## 2. Sugerir trechos

Ler `transcricao/texto.md` e escrever `candidatos.md` com 5 a 10 candidatos.
Conferir em `transcricao/palavras.json` os tempos exatos. Ler o que vem antes
e depois de cada trecho para não mudar o sentido da fala.

```markdown
## 3. Título em forma de pergunta
Tempo: 00:12:04 a 00:13:21 (1min17)
Abertura: "..."
Fim: "..."
Por que funciona: ...
Riscos: ...
Clima da música: ...
```

Parar e aguardar a aprovação do dono do canal.

## 3. Registrar a aprovação

Gravar `aprovados.json` e validar:

```json
{"cortes": [{"numero": 1, "titulo": "...", "inicio": 724.12, "fim": 801.40, "clima": "leve"}]}
```

```bash
.venv\Scripts\python.exe -m esteira validar "<pasta do episódio>"
```

## 4. Enquadrar

```bash
.venv\Scripts\python.exe -m esteira planos "<pasta do episódio>"
```

O comando cria `enquadramento.json` e `planos.jpg` em cada corte. Abra a folha
e leia a transcrição para saber quem fala. Em `enquadramento.json`, cada plano
tem `inicio`, `fim`, `x`, `y` e `zoom`, com `x` e `y` entre 0 e 1 na imagem
original:

- Close: deixar quem fala centralizado.
- Câmera aberta: dar zoom em quem fala. No convidado, usar zoom leve, perto de
  1,35. Se a fala mudar dentro do plano, dividir o plano nesse momento.
- Duas pessoas: manter as duas só quando a troca fizer parte da cena.

Evite zoom acima de 2, porque o episódio é 1080p.

## 5. Cortar

```bash
.venv\Scripts\python.exe -m esteira cortar "<pasta do episódio>"
```

Revisar `edicoes.md` com o dono do canal. Se um corte falhar, ler `registro.json`.

## 6. Sugerir imagens

Ler `legenda.srt` e escrever `imagens.md` com 4 a 8 sugestões, usando os tempos
do corte final.

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

## 7. Escrever textos

Escrever `post.md` com título e descrição do YouTube, textos de Instagram e
TikTok, clima da música, aviso de IA quando houver imagem de IA e a seção
"Publicação sugerida".

## 8. Sugerir calendário

Sempre gerar `calendario.md` na pasta do episódio, sem esperar pedido. Colocar
todas as sugestões dentro de 1 semana, porque o próximo episódio costuma sair
nesse intervalo. Usar os horários de `Contexto/redes-e-publicacao.md` e, se não
couberem todos os cortes, acrescentar outro dia no mesmo horário. Usar um corte
por horário e informar o motivo da ordem. Começar pelos cortes mais amplos. Se houver métricas novas,
usar esses dados e dizer de onde vieram. Nunca afirmar que um horário é
garantidamente o melhor.
