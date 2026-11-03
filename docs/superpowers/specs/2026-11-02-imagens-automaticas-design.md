# Imagens automáticas (Parte 3): design

Data: 2026-11-02
Status: desenho aprovado em conversa, spec aguardando revisão do dono do canal.

## 1. Objetivo

Todo corte sai com as imagens inseridas sem o dono do canal procurar foto.
A esteira encontra fotos de licença livre, o Claude escolhe olhando as
candidatas, e o dono do canal só aprova o download e gera as imagens de IA
no ChatGPT.

O motor da Parte 1 já insere imagens a partir do `montagem.json`. Esta parte
automatiza o que foi feito à mão no F1: escolher momentos, buscar, escolher,
baixar, encaixar as imagens de IA e preencher o `imagens.md`.

## 2. Decisões

- Uma pausa no meio do fluxo: o dono do canal aprova a lista de downloads e
  gera as imagens de IA a partir de `prompts-chatgpt.md`. Nenhuma outra.
- Abordagem "script e olhar": scripts fazem busca, filtro, folhas, ajuste de
  tempo e download; o Claude decide os momentos e escolhe olhando as folhas.
- Fonte de fotos: Wikimedia Commons API. Licenças aceitas: CC0, domínio
  público, CC BY e CC BY-SA. Fora: NC, ND, uso justo e arquivo sem licença.
- Imagens de IA geradas pelo dono do canal no ChatGPT (Plus), em 9:16.
- Downloads usam o `thumburl` devolvido pela API, nunca link montado à mão.
- User-Agent: `TudoEPoliticaEsteira/1.0`, sem e-mail.

## 3. Fluxo

1. O Claude grava `pedidos.json` em cada corte, com 4 a 6 momentos.
2. `esteira imagens buscar <episódio>` consulta a Wikimedia e gera as folhas
   de candidatas.
3. O Claude olha as folhas e grava a escolha de cada momento no
   `pedidos.json`.
4. `esteira imagens lista <episódio>` ajusta os tempos, grava o
   `imagens.md` de cada corte, `lista-imagens.md` e `prompts-chatgpt.md`, e
   cria `ia-entrada/`.
5. Pausa: o dono do canal aprova os downloads e põe as imagens do ChatGPT em
   `ia-entrada/`.
6. `esteira imagens baixar <episódio>` baixa as fotos, encaixa as imagens de
   IA e atualiza as receitas.
7. Montagem e revisão seguem como hoje.

## 4. Arquivos

```text
Cortes/<episódio>/
  lista-imagens.md        downloads para aprovação (nome, origem, tamanho)
  prompts-chatgpt.md      prompts numerados, na ordem de geração
  ia-entrada/             imagens do ChatGPT + .mapa.tsv
  <corte>/
    pedidos.json          momentos, candidatas e escolha
    candidatas/NN-M.jpg   folha de candidatas por momento
    imagens.md            formato atual
    imagens/NN-*          arquivos finais
Automacao/esteira/
  pedidos.py              leitura, validação e ajuste de tempo
  wikimedia.py            busca, filtro de licença e resolução
  folhas.py               folha de candidatas (Pillow)
  ingestao.py             encaixe de ia-entrada/
```

`imagens.py` (leitura do `imagens.md`) continua igual. `cli.py` ganha
`imagens buscar|lista|baixar`.

## 5. Pedidos

`pedidos.json`, com tempos em segundos a partir do início do corte:

```json
{"momentos": [
  {"inicio": 12.4, "fim": 15.8, "fala": "...", "tipo": "foto",
   "busca": "Lewis Hamilton Mercedes 2021"},
  {"inicio": 40.0, "fim": 43.0, "fala": "...", "tipo": "noticia",
   "titulo": "...", "veiculo": "..."},
  {"inicio": 61.2, "fim": 64.0, "fala": "...", "tipo": "ia",
   "prompt": "..."}
]}
```

Validação antes da busca:
- `tipo` é `foto`, `noticia` ou `ia`;
- `foto` exige `busca`; `noticia` exige `titulo` e `veiculo`; `ia` exige
  `prompt`;
- `inicio` < `fim`, ambos dentro da duração principal do corte;
- prompt de IA com nome de pessoa do `Contexto/glossario.md` é recusado.

Notícia usa o comando `cartao` existente.

## 6. Busca e folhas (`imagens buscar`)

Por pedido do tipo `foto`:
1. `list=search&srnamespace=6`, 20 resultados.
2. `prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=1920`.
3. Filtro: licença aceita (seção 2); formato jpg, png ou webp; lado menor
   de pelo menos 800 px.
4. Até 6 candidatas, gravadas no `pedidos.json` com título, `thumburl`,
   largura, altura, autor e licença.

Folha `candidatas/NN-M.jpg` (NN = corte, M = momento): grade 3x2 com
miniaturas de até 640 px, cada uma com número, proporção (vertical ou
horizontal), autor e licença curta. Pedido sem candidata gera folha com
"nenhuma".

As miniaturas ficam numa pasta temporária e são apagadas ao fim do
comando. Elas não precisam de confirmação; a confirmação continua valendo
para todo arquivo que entra no vídeo. Essa exceção entra no `CLAUDE.md`
com aprovação do dono do canal.

## 7. Escolha

O Claude grava em cada momento um destes campos:
- `"escolha": N` (número da candidata);
- troca para `"tipo": "ia"` com `prompt`;
- `"descartar": true`.

`imagens lista` recusa momento de foto sem escolha.

## 8. Ajuste de tempo (`imagens lista`)

Na ordem dos momentos:
- menos de 2 s: estende o fim até 2 s, sem passar do início do próximo
  momento nem do fim da duração principal; se não couber, estende o início
  para trás, sem sobrepor o anterior nem ficar antes de 0;
- mais de 5 s: corta em 5 s;
- momento que não cabe em 2 s é descartado, com aviso.

O resultado passa pela `validar_receita` existente.

## 9. Downloads e imagens de IA (`imagens baixar`)

- `lista-imagens.md` lista cada foto com nome, origem e tamanho estimado.
- Fotos são baixadas pelo `thumburl` para `imagens/NN-<nome>.jpg`.
- `ia-entrada/`: os arquivos, ordenados pela data de gravação, são
  encaixados na ordem dos prompts de `prompts-chatgpt.md`. O resultado fica
  em `.mapa.tsv`. Se o número de arquivos não bater com o de prompts, o
  comando para e mostra o que falta, sem gravar nada.
- Ao fim, o comando grava `imagens.md` e atualiza a lista de imagens da
  receita (`atualizar_imagens`).

## 10. Erros

- Falha no download de uma foto: ela fica de fora, aparece como alerta no
  `revisao.md`, e as demais seguem.
- API fora do ar: `imagens buscar` avisa e não grava nada pela metade.
- Resposta da API sem `thumburl`: candidata ignorada.
- Arquivo baixado que não é imagem (ex.: HTML): tratado como falha.

## 11. Mudanças de regra

Aplicadas na implementação, com o texto mostrado ao dono do canal antes de
salvar:
- `Automacao/docs/operacao.md`: etapas de imagem com os três comandos.
- `Contexto/estilo-de-imagens.md`: ajuste curto ao novo fluxo.
- `CLAUDE.md`: exceção das miniaturas de pré-visualização.

## 12. Testes

1. Automáticos, sem internet, com API falsa: validação dos pedidos; filtro
   de licença e resolução; folha com imagens sintéticas; ajuste de tempo
   (curto, longo, encostado no vizinho, sem espaço); encaixe de
   `ia-entrada/` (ordem, contagem diferente); falha de download isolada;
   recusa de prompt com nome do glossário.
2. Teste real: refazer do zero as imagens de um episódio; o dono do canal
   aprova o resultado.

## 13. Critérios de sucesso

- O dono do canal só aprova downloads e gera as imagens de IA.
- Nenhuma foto quebrada nem fora da licença.
- Nenhuma imagem barrada pela validação de tempo.
- O dono do canal aprova as imagens sem trocar mais de uma por corte.

## 14. Fora desta parte

- Outras fontes de fotos (Flickr, Unsplash, Pexels).
- Geração de imagens de IA pela esteira.
- Captura automática de páginas de notícia.
