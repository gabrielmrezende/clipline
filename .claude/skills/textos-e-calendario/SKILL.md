---
name: textos-e-calendario
description: Etapa 9 do clipline. Use para escrever o post.md de cada corte (YouTube, Instagram, TikTok) e o calendario.md do episódio.
---

# Textos e calendário

## post.md

Um subagente por corte, em paralelo. Cada um recebe: título do corte, `trabalho/legenda.srt`, a seção do
`candidatos.md` desse corte, `../Contexto/redes-e-publicacao.md` e o crédito da música (`credito` em
`trabalho/montagem.json`).

Formato exato (o painel e o `publicar` leem por estas seções):

```markdown
# Textos do corte

## YouTube
Título: <até 100 caracteres, sem < nem >, uma linha>

Descrição:
<texto>

<crédito da música, exato>

## Instagram
<até 2.200 caracteres e até 30 hashtags; termina com o crédito da música>

## TikTok
<até 2.200 caracteres; termina com o crédito da música>

## Música
Faixa: <título>
Crédito: <crédito exato>

## Publicação sugerida
<redes e data>
```

- Nenhuma linha dos textos começa com `## `.
- Sem aviso de IA e sem crédito de foto: os dois entram na publicação, a partir do vídeo aprovado. O `agendar`
  e o painel cobram o que faltar.
- Não prometa o que o corte não mostra. Título em forma de pergunta funciona bem, mas não é regra.

## calendario.md

Siga `docs/operacao.md`, etapa 9: TikTok e Shorts com todos os cortes (1 a 2 por dia), Instagram só com
`instagram: true`, tudo antes do próximo episódio, começando pelos cortes mais amplos. Diga de onde vêm as
métricas, se usar alguma, e nunca afirme que um horário é garantidamente o melhor.

Grave a data de cada corte no campo `data` do `aprovados.json` e rode `esteira validar "<pasta>"`.
