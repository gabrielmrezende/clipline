# Imagens no painel (Fase A)

Data: 2026-11-09. Status: aprovado em conversa, aguardando revisão da spec.
Base: painel de revisão e ajustes de música, já no `master`
(`docs/superpowers/specs/2026-11-07-painel-de-revisao-design.md`,
`docs/superpowers/specs/2026-11-09-ajustes-de-musica-design.md`).

## Objetivo

Levar as imagens sugeridas para o painel: o Claude continua propondo os
momentos, as fotos e os prompts (etapa 8 do `operacao.md`), e o dono do canal
revisa tudo por corte, baixa as fotos e gera as imagens de IA por uma API, com
a aprovação de cada prompt e do custo antes de gerar.

A **Fase B** (montar as imagens direto no `corte.mp4`, deixando o CapCut
opcional) é outro subprojeto, com spec própria.

### Critérios de sucesso

1. Na tela do corte, o dono vê cada momento proposto pelo Claude e consegue:
   trocar as fotos escolhidas, buscar outras candidatas, trocar foto por IA e
   vice-versa, editar e aprovar prompts e descartar momentos.
2. Ele baixa as fotos escolhidas e gera as imagens de IA aprovadas pelo painel,
   por corte ou pelo episódio inteiro, sempre depois de ver o resumo (quantas,
   tamanho ou custo) e confirmar.
3. Nenhuma imagem de IA é gerada a partir de prompt que cite pessoa do
   glossário.
4. As imagens de IA geradas aparecem em `imagens-sugeridas/` em 1080x1920, no
   `guia.md`, e nunca são apagadas por uma nova rodada de fotos.
5. A chave da API nunca passa pelo navegador nem é gravada em arquivo.
6. O provedor (OpenAI ou Google), o modelo, a qualidade e o preço por imagem
   são escolhidos nas configurações do painel.

### Fora deste subprojeto

Montar imagens no vídeo (Fase B), aviso de IA automático no `post.md` (a regra
continua: o aviso entra na publicação, a partir do vídeo final), criar momentos
novos no painel, cartões de notícia pelo painel (continuam como hoje), consulta
automática de preços na internet.

## Regras do canal que mudam

O texto exato destas mudanças é mostrado ao dono do canal para aprovação antes
de ser salvo:

- `Contexto/estilo-de-imagens.md`, linha "Imagens de IA: a esteira só escreve o
  prompt no `guia.md`. O dono do canal gera no ChatGPT, em 9:16." passa a dizer
  que a esteira gera pelo painel, por API, com o prompt e o custo aprovados pelo
  dono, e que o `guia.md` marca as imagens de IA.
- `docs/operacao.md`, etapa 8: a regra "IA: só o prompt, que vai no `guia.md`. A
  esteira não recebe nem prepara imagem de IA." passa a descrever o fluxo do
  painel e o comando `imagens gerar`.

Continuam valendo: nunca gerar imagem de IA de pessoa real (a esteira recusa
prompt com nome de pessoa do glossário); fotos só do Wikimedia Commons com as
licenças aceitas; download de fotos só depois da confirmação do dono; o aviso
de IA entra no post na publicação, a partir do vídeo final.

## Dados

### `pedidos.json` (por corte, em `trabalho/`)

O `Momento` (`esteira/pedidos.py`) ganha:

- `aprovado: bool = False`: o prompt de um momento `ia` foi aprovado pelo dono.
  Mudar o `prompt` pelo painel desmarca a aprovação.

O resto continua como hoje (`tipo`, `busca`, `prompt`, `candidatas`,
`escolhas`, `descartar`, `motivo`…). A versão do arquivo é o SHA-256 dos bytes,
como no `post.md`.

### `ia.json` (por corte, em `trabalho/`)

Lista das imagens de IA geradas pela esteira:

```json
[{"arquivo": "0052-turistas-ia-1.jpg", "momento": "0052-turistas", "versao": 1,
  "provedor": "openai", "modelo": "<modelo>", "prompt": "<prompt usado>",
  "data": "2026-11-09T15:20:00"}]
```

- Chave do momento: `MMSS-slug(nome)` (o mesmo `_base` do `fluxo_imagens`).
- Arquivo: `imagens-sugeridas/<momento>-ia-<versao>.jpg`, versão de 1 a 3.
- Essas imagens **não** entram em `sugeridas.json`, e o `imagens sugerir`
  nunca as apaga.

### `imagens-ia.json` (em `Automacao/`)

Configuração, sem segredos:

```json
{"provedor": "openai",
 "provedores": {
   "openai": {"modelo": "<modelo>", "qualidade": "<qualidade>", "preco_usd": 0.05},
   "google": {"modelo": "<modelo>", "qualidade": "<qualidade>", "preco_usd": 0.04}}}
```

Os modelos, qualidades e preços iniciais são conferidos nas páginas oficiais
de cada provedor no momento da implementação. O preço é só para a estimativa
mostrada ao dono; ele pode editar.

### Chaves

Keyring do Windows, serviço `tudo-e-politica-imagens`, campos `openai:chave` e
`google:chave`. Cadastro só pelo terminal:
`python -m esteira imagens conectar openai|google` (pede a chave sem ecoar).
Nunca em arquivo, nunca pelo navegador.

## Provedores (`esteira/imagens_ia/`)

- `provedor.py`: `class Provedor(Protocol)`: `nome: str`,
  `gerar(prompt: str, proporcao: str = "9:16") -> bytes` (imagem PNG ou JPEG).
  Erros: `SemChave`, `ChaveRecusada`, `ErroTemporario` (limite, 5xx, rede),
  `ConteudoRecusado(motivo)`; todos com mensagem em português.
- `openai.py` e `google.py`: adaptadores por HTTP direto, com o cliente de
  `esteira/publicar/http.py`. Endpoint, modelo e formato de pedido e resposta
  conferidos na documentação oficial na implementação. Pedem a proporção
  vertical mais próxima de 9:16 que o modelo aceitar.
- `chaves.py`: ler e gravar as chaves no keyring (import do `keyring` dentro das
  funções, como em `publicar/credenciais.py`).
- `config.py`: ler e gravar `imagens-ia.json`; `provedor_atual(...) -> Provedor`.
- Nenhum novo pacote é instalado.

## Gerar uma imagem

`imagens_ia.gerar.gerar_momento(pasta_corte: Path, chave_momento: str,
provedor: Provedor, base: Path | None = None) -> str` (arquivo gerado):

1. Lê o momento em `pedidos.json`; precisa ser `tipo == "ia"`, `aprovado`,
   não `descartar`, com `prompt` não vazio.
2. Recusa (`ErroPrompt`) prompt que cite pessoa do glossário
   (`pedidos._pessoa_citada` com `pessoas_do_glossario`).
3. Recusa se o momento já tem 3 versões.
4. Chama `provedor.gerar(prompt)`.
5. Prepara em 1080x1920 com `imagens.preparar_foto` (vertical → tela cheia;
   outra proporção → faixa central com fundo desfocado).
6. Grava `imagens-sugeridas/<momento>-ia-<K>.jpg` por `garantir_escrita`,
   acrescenta ao `ia.json` e refaz o `guia.md`.

`fluxo_imagens.escrever_guia` passa a incluir, nos momentos `ia`, a linha
`Imagem de IA: <arquivos> (<provedor>, <data>)` quando houver versões, além do
prompt.

## Comandos novos

- `python -m esteira imagens conectar openai|google`.
- `python -m esteira imagens gerar "<pasta do episódio>" [--numero N]`: sem
  `--confirmar`, mostra o resumo (momentos aprovados sem imagem, provedor,
  modelo, custo estimado) e não gera; com `--confirmar`, gera. Mesmo padrão do
  `publicar agendar`.

## Painel

### Fila

A fila passa a ter tipos de pedido: `musica`, `fotos`, `ia`. Continua um único
trabalhador. Um corte só pode ter um pedido ativo de cada tipo. Pedidos de
episódio (`fotos` ou `ia` do episódio inteiro) viram um pedido com a lista de
cortes; enquanto ele estiver ativo, nenhum corte dessa lista aceita outro
pedido do mesmo tipo (409). O andamento mostra `Gerando 2 de 5…` /
`Baixando 2 de 5…`.

O pedido `fotos` roda o `sugerir` atual, que apaga e refaz as fotos que a
própria esteira gravou no corte (`sugeridas.json`); a confirmação na tela diz
isso: `As fotos baixadas antes neste corte serão substituídas.`

### API nova

| Método e rota | Faz |
|---|---|
| `GET .../cortes/{n}/momentos` | momentos do corte: tempo, fala, tipo, nome, `busca`, candidatas (com `miniatura` limitada a 640 px), escolhas, `prompt`, `aprovado`, `descartar`, fotos prontas, versões de IA, aviso de pessoa citada; mais a `versao` do `pedidos.json` |
| `PUT .../cortes/{n}/momentos/{chave}` | `{versao, tipo?, escolhas?, prompt?, aprovado?, descartar?}`; 409 se a versão mudou; 422 se inválido (escolhas fora da faixa, mais de 3, prompt com pessoa e `aprovado: true`) |
| `POST .../cortes/{n}/momentos/{chave}/buscar` | `{busca}` → novas candidatas do Wikimedia, gravadas no momento |
| `GET .../fotos/resumo` (corte e episódio) | quantas fotos, quantos MB, origem |
| `POST .../fotos` (corte e episódio) | 202 pedido `fotos` (roda o `sugerir`) |
| `GET .../ia/orcamento` (corte e episódio) | momentos aprovados sem imagem, provedor, modelo, custo estimado |
| `POST .../ia` (corte e episódio) e `POST .../momentos/{chave}/ia` | 202 pedido `ia` |
| `GET` e `PUT /api/configuracoes/imagens` | configuração e se cada chave está cadastrada (nunca a chave) |

Todas passam pelo login com `--rede`, pelos tratadores de erro do painel e por
`garantir_escrita`.

### Telas

- **Tela do corte, bloco "Imagens"** (substitui a exibição do `guia.md`):
  cartões por momento, em ordem de tempo, com tempo e fala, botão ▶ que leva o
  player do corte ao segundo, tipo, `Trocar para IA`/`Trocar para foto` e
  `Descartar`.
  - Foto: grade de candidatas em miniatura, escolhidas numeradas 1–3 na ordem
    do clique (clicar de novo tira), autor e licença, campo `Buscar outras`,
    fotos prontas marcadas `Pronta`.
  - IA: prompt editável, aviso em tempo real
    `Cita pessoa real (<nome>): não pode gerar`, caixa `Aprovado`, versões
    geradas em miniatura com provedor e data, botão `Gerar de novo`.
  - Topo: `Baixar as fotos escolhidas (N fotos, X MB)` e
    `Gerar as aprovadas (N imagens, ~US$ X)`, cada um com confirmação com o
    resumo; andamento `Na fila`, `Gerando 2 de 5…`, `Pronto`, `Erro: …`.
- **Tela do episódio, aba "Imagens"**: resumo por corte (momentos, fotos
  baixadas, prompts aprovados, imagens geradas) e os botões do episódio.
- **Tela "Configurações"**: provedor, modelo, qualidade, preço por imagem
  editáveis; estado de cada chave (`Conectado` ou
  `Rode python -m esteira imagens conectar <provedor>`).

## Publicação

O resumo do `publicar agendar` ganha, quando o corte tem imagens no `ia.json`,
a linha `Este corte tem N imagens de IA geradas: confira se o vídeo final usa
alguma e inclua o aviso.` Não bloqueia.

## Erros

- Sem chave: `Rode python -m esteira imagens conectar <provedor>`.
- Chave recusada: `Chave recusada pelo <provedor>: conecte de novo.`
- Limite, instabilidade ou rede: erro temporário com `Tentar de novo`; o painel
  nunca repete sozinho (para não cobrar duas vezes).
- Conteúdo recusado pelo provedor: o motivo aparece no momento; os outros
  momentos do pedido seguem.
- Uma imagem com erro não interrompe as outras do mesmo pedido.
- Conflito no `pedidos.json` (o Claude mudou o arquivo): 409 e o painel
  recarrega o momento, como no `post.md`.
- Nenhuma falha de leitura derruba a tela.

## Testes

- Adaptadores OpenAI e Google com respostas HTTP falsas: sucesso, sem chave,
  401, 429, 5xx, conteúdo recusado.
- `gerar_momento` com provedor falso: pessoa citada recusada, não aprovado
  recusado, limite de 3 versões, nome do arquivo, `ia.json`, `guia.md`.
- `sugerir` não apaga imagens de IA.
- `escrever_guia` com versões de IA.
- `imagens gerar` sem e com `--confirmar`; `imagens conectar` com keyring falso.
- API: momentos, edição com 409 e 422, buscar com Wikimedia falso, resumo,
  orçamento, pedidos 202, configurações sem expor a chave, login com `--rede`.
- Fila com tipos e pedidos de episódio.
- Frontend (Vitest): cartões, escolhas 1–3, troca de tipo, aviso de pessoa,
  confirmação com resumo, andamento, configurações.
- Ponta a ponta (Playwright) com um provedor falso ligado por variável de
  ambiente só de teste: aprovar um prompt, gerar e ver a imagem no cartão.
