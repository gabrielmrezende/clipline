# Cortes para o CapCut: design

Data: 2026-11-05
Status: desenho aprovado em conversa, spec aguardando revisão do dono do canal.

## 1. Objetivo

A esteira deixa de colocar imagens no vídeo. Ela entrega cada corte pronto,
menos as imagens: legenda, cortes de pausa, música, encerramento e zoom em
quem fala. Ao lado, deixa uma pasta com imagens sugeridas e um guia com o
segundo exato de cada uma. O dono do canal coloca as imagens à mão no CapCut
e salva o vídeo definitivo numa pasta própria do corte.

Motivo: no teste do F1 (Entre Assuntos #03), o corte, a legenda e a música
ficaram bons; as imagens e parte dos zooms, não. Os erros de zoom vistos
foram "zoom na pessoa errada" e "zoom demais ou de menos". Causa: o
`enquadramento.json` é decidido pelo Claude a partir de um quadro por plano,
com planos de até 62 s e um zoom só, enquanto a fala troca de pessoa várias
vezes; e o zoom é um número livre.

## 2. Decisões

- Entrega: um MP4 pronto, sem imagens (`corte.mp4`).
- Imagens: de 1 a 3 opções por momento, a melhor primeiro, já em 1080x1920.
- IA: só o prompt, no `guia.md`. A esteira não recebe nem prepara imagem de IA.
- Aprovação: o vídeo salvo em `video-final/` é a aprovação do corte. Corte
  sem vídeo ali não foi aprovado. Sai o `aprovacao.json`.
- Quem fala: diarização por voz (pyannote) + detecção e reconhecimento de
  rosto (OpenCV YuNet e SFace). Não usa leitura de boca: no canal há perfil,
  costas e microfone na frente da boca.
- Zoom calculado pelo tamanho do rosto, arredondado para 4 níveis fixos.
- Uma pausa só no fluxo: a confirmação do download das fotos do episódio.
- Os cortes já gerados do Entre Assuntos #03 não mudam.

## 3. Pasta do corte

```
2 - Cortes/<Quadro NN - Convidado>/
  transcricao/ (texto.md, palavras.json, vozes.json, pessoas.json, pessoas.jpg)
  aprovados.json  candidatos.md  calendario.md  revisao.md
  NN-titulo/
    corte.mp4
    imagens-sugeridas/
      guia.md
      MMSS-nome-K.jpg     fotos, K = 1 a 3, 1080x1920
      MMSS-nome.png       cartão de notícia, 1080x1920
    video-final/          criada vazia; a esteira nunca grava nela
    post.md
    trabalho/             enquadramento.json, montagem.json, legenda.srt,
                          registro.json, edicoes.md, pedidos.json,
                          planos.jpg, candidatas/
```

- `MMSS` é o início do momento no `corte.mp4` (`0112` = 1:12). Os arquivos
  ficam na ordem do vídeo ao importar no CapCut.
- `nome` é o `nome` do momento em minúsculas, sem acento, com hífens.

## 4. Quem fala e zoom

### 4.1 Vozes (`vozes`)

Comando novo, rodado uma vez por episódio depois de `transcrever`:

```bash
.venv\Scripts\python.exe -m esteira vozes "<video>" "<pasta do episódio>" --pessoas 3
```

- pyannote `speaker-diarization-3.1`, local, na GPU.
- `--pessoas` é o número de pessoas à mesa (padrão: 3).
- Token do Hugging Face só pela variável de ambiente `HF_TOKEN`; nunca em
  arquivo. A conta e o aceite dos termos do modelo são do dono do canal.
- Saída `transcricao/vozes.json`:
  `{"trechos": [{"inicio": 12.3, "fim": 18.9, "voz": "V1"}]}`.
- Sem `HF_TOKEN` ou com falha do modelo: o comando para com mensagem clara.

### 4.2 Rostos

Em cada plano de câmera (detecção de cena atual), a esteira lê um quadro a
cada 0,5 s e detecta rostos com YuNet. Cada rosto ganha uma assinatura SFace.
Assinaturas parecidas no episódio formam uma pessoa (`P1`, `P2`, ...). Por
plano, grava a caixa média de cada pessoa visível.

### 4.3 Ligar voz e pessoa

Nos planos com um rosto só, conta quanto tempo cada voz fala enquanto aquela
pessoa está na tela. Cada voz fica com a pessoa com quem mais coincide. Grava
`transcricao/pessoas.json` (`{"V1": "P2", ...}`) e a folha `pessoas.jpg`
(rosto, voz, tempo de fala). O Claude confere a folha, escreve o nome de cada
pessoa e corrige a ligação se precisar, sem parar o fluxo.

### 4.4 Enquadrar (`planos`)

O comando `planos` passa a gerar o `enquadramento.json` sozinho. Dentro de
cada plano de câmera, divide onde a voz troca:

- Turnos de menos de 2 s (por exemplo "uhum", "é") não dividem.
- Nenhum trecho fica com menos de 2 s; o trecho curto se junta ao vizinho.
- Quem fala aparece no plano: enquadra o rosto dele.
- Quem fala não aparece e há um rosto: enquadra esse rosto.
- Quem fala não aparece e há vários rostos: enquadra o convidado (pessoa
  ligada à voz que mais fala no episódio); sem o convidado na tela, zoom 1,0,
  centro do grupo. (Correção do dono do canal em 2026-11-05.)
- Nenhum rosto: centro, zoom 1,0, e alerta.
- Fala sobreposta (duas vozes ao mesmo tempo por mais de 1 s): mantém o
  enquadramento anterior e gera alerta.
- A troca entre trechos é corte seco, sem movimento.

### 4.5 Nível de zoom

- Meta: altura do rosto igual a 28% da altura da faixa do vídeo.
- `zoom = meta / altura medida`, arredondado para o nível mais próximo de
  1,0 / 1,35 / 1,7 / 2,0. Nunca acima de 2,0.
- Posição: rosto centralizado na horizontal; olhos perto do terço superior
  da faixa. O recorte nunca sai da imagem (regra atual de `recorte`).
- Close já grande dá 1,0 sozinho. Sai a regra fixa "convidado em 1,35".
- A meta de 28% é o ponto de partida; o teste real pode ajustá-la, com
  aprovação do dono do canal.

### 4.6 Conferência

`planos.jpg` mostra cada trecho com uma caixa no rosto escolhido, o nome de
quem fala e as primeiras palavras da fala. O Claude confere todas as folhas
e pode editar o `enquadramento.json` à mão. Alertas de 4.4 vão para o
`registro.json` e aparecem no `revisao.md`.

## 5. Imagens sugeridas

### 5.1 Momentos

O Claude lê a legenda e grava `trabalho/pedidos.json` com 4 a 6 momentos
por corte, no formato atual (`foto`, `noticia`, `ia`), com tempos na linha
do `corte.mp4`. As regras de pessoa real, IA e notícia continuam.

### 5.2 Fotos

1. `imagens buscar`: igual a hoje (Wikimedia, licenças CC0, domínio
   público, CC BY, CC BY-SA), gera `trabalho/candidatas/` e as folhas.
2. O Claude escolhe olhando a foto, não o título: grava
   `"escolhas": [N, M, ...]` (1 a 3, a melhor primeiro) no momento, ou troca
   para `ia`, ou marca `"descartar": true`.
3. A esteira mostra o total do episódio (quantidade de fotos, MB, origem
   Wikimedia Commons) e o Claude pede a confirmação do dono do canal. Esta é
   a única pausa.
4. `imagens sugerir`: baixa as fotos escolhidas (pelo `thumburl`), prepara
   e grava em `imagens-sugeridas/`, gera os cartões e o `guia.md`.

### 5.3 Preparo

- Foto vertical (pelo menos 1,5 vez mais alta que larga): tela cheia 1080x1920.
- Horizontal ou quadrada: inteira na faixa central, sobre a própria imagem
  ampliada e desfocada, sem cortar nada.
- Notícia: cartão do canal (código atual de `cartao.py`) em 1080x1920, com
  "Fonte: veículo, data". Nunca imita página de veículo real.
- IA: nenhum arquivo.

### 5.4 `guia.md`

Topo: lembretes do estilo (2 a 5 s na tela, corte seco, zoom lento de cerca
de 8%, a legenda fica coberta pela imagem, aviso de IA no post se usar
imagem gerada). Depois, um bloco por momento, em ordem de tempo:

```markdown
## 0:12 a 0:15 · Yas Marina (foto)
Fala: "...quando a corrida foi para Abu Dhabi..."
Opções: 0012-yas-marina-1.jpg, 0012-yas-marina-2.jpg
Créditos:
1. Autor, CC BY-SA 4.0, https://commons.wikimedia.org/...
2. ...

## 1:01 a 1:04 · Chuva na pista (IA)
Fala: "..."
Prompt (ChatGPT, 9:16): "..."
```

Momento cuja foto falhou no download vira bloco com "Sem imagem: motivo".

### 5.5 Post

O `post.md` sai sem o aviso de IA e sem créditos de fotos. Os dois são
decididos na etapa de publicação (próxima etapa), a partir do vídeo final.

## 6. Fluxo do roteiro

1. `transcrever`.
2. `vozes`.
3. Escolha dos cortes: `aprovados.json` e `candidatos.md`.
4. `validar`.
5. `planos`: rostos, ligação, enquadramento e folhas; o Claude confere.
6. `preparar`: legenda, pausas, música, em `trabalho/`.
7. `montar`: `corte.mp4`, sem imagens. Cria `imagens-sugeridas/` e
   `video-final/` vazias.
8. `imagens buscar`, escolha, confirmação do download, `imagens sugerir`.
9. `post.md` e `calendario.md`.
10. `revisao`: por corte, link do `corte.mp4` e do `guia.md`, redes, data,
    música, alertas de quem fala, nomes duvidosos e se `video-final/` está
    vazia. O Claude para.

## 7. Mudanças no código

- Novos: `vozes.py` (diarização), `rostos.py` (detecção e assinatura),
  `pessoas.py` (ligação voz e pessoa, folha), `enquadrar.py` (divisão por
  quem fala e nível de zoom). A lógica de `enquadrar.py` recebe vozes e
  rostos como dados, sem modelo, para ser testada sozinha.
- `planos.py`: mantém `Plano`, `recorte` e detecção de cena; a folha mostra
  a caixa do rosto, o nome e o texto.
- `render.py` e `montar.py`: sai a inserção de imagens; a saída é `corte.mp4`.
- `fluxo_imagens.py`: saem `lista`, `baixar`, `ia-entrada/`,
  `prompts-chatgpt.md`, `lista-imagens.md` e a escrita de `imagens.md`;
  entram `escolhas` e `sugerir`. O preparo com fundo desfocado passa para
  Pillow em `imagens.py`.
- `caminhos.py`: pastas `trabalho/`, `imagens-sugeridas/` e `video-final/`.
- `revisao.py`: novos campos; sai `aprovacao.json`.
- `cli.py`: comando `vozes`; `imagens sugerir`; remove `imagens lista` e
  `imagens baixar`.
- Dependências: `torch` com CUDA e `pyannote.audio` (cerca de 2,5 GB),
  `opencv-python` e os modelos YuNet e SFace (cerca de 80 MB). Cada download
  só com confirmação do dono do canal (nome, origem e tamanho).

## 8. Documentos

- Reescrever `Automacao/docs/operacao.md` com o fluxo da seção 6.
- `Contexto/estilo-dos-cortes.md`: regra do zoom (4.4 e 4.5), entrega em
  `corte.mp4`, vídeo final em `video-final/`.
- `Contexto/estilo-de-imagens.md`: imagens inseridas pelo dono do canal no
  CapCut a partir de `imagens-sugeridas/`.
- O texto de cada mudança em `Contexto/` é mostrado ao dono do canal e só é
  salvo com aprovação.

## 9. Erros

- Sem `HF_TOKEN`, sem `vozes.json` ou com falha da diarização: `planos` para
  com mensagem clara; não adivinha quem fala.
- Plano sem rosto ou voz sem pessoa ligada: centro, zoom 1,0, alerta.
- Um corte com erro não impede os outros (comportamento atual).
- `corte.mp4` existente não é sobrescrito sem `--forcar`; antes de usar
  `--forcar`, perguntar ao dono do canal.
- `video-final/` nunca é apagada nem alterada pela esteira.

## 10. Testes

- Automáticos: ajustar os 293 atuais ao novo fluxo. Novos testes de
  `enquadrar.py` com vozes e rostos falsos: divisão na troca de voz, mínimo
  de 2 s, turno curto ignorado, quem fala fora da tela, vários rostos, sem
  rosto, fala sobreposta e arredondamento do zoom. Testes da ligação voz e
  pessoa, do preparo das fotos (vertical e horizontal), do nome `MMSS`, do
  `guia.md` e da estrutura de pastas.
- Teste real: refazer os 10 cortes do Entre Assuntos #03 em
  `2 - Cortes/Entre Assuntos 03 - Arthur Cerqueira (teste capcut)/`, sem
  tocar nos atuais. O dono do canal compara os zooms com os erros que viu e
  testa o fluxo no CapCut. Resultado em `docs/resultados/`.

## 11. Fora do escopo

- Publicação a partir de `video-final/` (próxima etapa), incluindo aviso de
  IA e créditos das fotos no post.
- Refazer os cortes atuais do Entre Assuntos #03.
