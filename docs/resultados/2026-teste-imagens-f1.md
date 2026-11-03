# Teste das imagens automáticas: Entre Assuntos #03, Arthur Cerqueira

Data: 2026-11-03. Parte 3 (imagens automáticas).

## Medido
- 10 cortes, 51 momentos (4 a 6 por corte): 39 fotos da Wikimedia
  Commons e 12 imagens de IA.
- `imagens buscar`: 3 min 50 s no episódio inteiro, já com o intervalo de
  2 s entre consultas.
- `imagens lista`: 4 min 30 s; 39 fotos, 21 MB.
- `imagens baixar`: 20 s; as 12 imagens de IA foram encaixadas na ordem
  certa e as receitas foram atualizadas.
- Escolha nas folhas: 34 de 42 na primeira rodada; 6 resolvidas com nova
  busca e 2 trocadas por IA (Madrid e difusor duplo). O kart também virou IA.
- Testes automáticos: 293 passando.
- O trabalho manual anterior ficou em `antigo/imagens-manual/`.

## Ajustes durante o teste
- A Wikimedia recusou a busca em sequência (429 e "search too busy").
  Agora a esteira respeita o Retry-After, repete a busca ocupada e espaça
  as consultas.
- Um arquivo com "Lando Norris" no nome mostrava outro piloto. A escolha
  precisa olhar a foto, não o título.
- Buscas vagas ("Madrid", "children karting") trazem resultados fora do
  assunto. Funciona melhor com o nome exato do lugar ou do objeto.

- Remontagem dos 10 cortes: 10 min, todos ok; quadros conferidos no
  segundo da fala.
- Os `post.md` não acompanharam a troca de imagens: 3 cortes ganharam IA
  sem o aviso e 1 ficou com aviso sem IA. Corrigido à mão. O `revisao`
  regravou os alertas manuais; os que ainda valiam foram recolocados.

## Pendente
- Ao trocar imagens, conferir o aviso de IA de cada `post.md`.
- `baixar` não baixa nenhuma foto enquanto faltar imagem de IA em
  `ia-entrada/`, mesmo nos cortes sem IA.
- O `lista` é lento (resolve o link e mede o tamanho de cada foto).
- Uma foto ficou sem tamanho na lista (HEAD falhou).
- Remontar os cortes e o dono do canal aprovar as imagens no vídeo.
