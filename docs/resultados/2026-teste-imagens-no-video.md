# Teste das imagens no vídeo (Fase B): Entre Assuntos #03, corte 01

Data: 2026-11-10. Pasta: `Automacao/.superpowers/teste-fase-b/` (cópia do corte 01 do episódio
`(teste capcut)`, sem o `corte.mp4` e sem o `video-final/` do dono). O episódio real e a pasta
`(teste capcut)` não foram tocados.

## Como foi montada a cópia
- Fotos: as 3 já baixadas em 05/11 (Yas Marina, Largada, Barcelona), com o `sugeridas.json` de
  então (sem `creditos.json`: vale a regra do último resumo).
- IA: as imagens que o dono gerou no ChatGPT em 03/11 para os prompts "Turistas" e "Madrid"
  (`ia-entrada/` do episódio), preparadas em 1080x1920 e registradas no `ia.json` da cópia como
  `teste (imagem do ChatGPT de ia-entrada)`. "Turistas" ganhou uma 2ª versão espelhada para testar
  `Usar no vídeo`. Nenhuma API paga foi chamada.

## Medido
- `montar` (CLI, código do branch): 99 s para o corte de 1:41, com a suíte de testes rodando ao
  mesmo tempo. 5 imagens no vídeo, nenhum alerta.
- Quadros conferidos (até 640 px, apagados no fim):
  - fotos horizontais inteiras na faixa central, sobre a própria foto ampliada e desfocada;
  - imagens de IA verticais em tela cheia;
  - sem legenda durante a imagem, e ela volta logo depois;
  - entrada e saída em corte seco;
  - "Turistas" entrou com a versão mais nova (2), como manda o padrão.
- Painel: os 5 cartões com `No vídeo`; `Usar no vídeo` na versão 1 de "Turistas" gravou o
  `no_video` no `pedidos.json` e o bloco avisou que as imagens mudaram.
- `Montar com as imagens` (painel): confirmação `Montar o corte de novo com 5 imagens? ...`,
  `Aprovar` desabilitado durante a montagem, 120 s até `ok`. O `registro.json` passou a listar
  `0052-turistas-ia-1.jpg`; o `corte-anterior.mp4` e o marcador foram apagados; o player voltou.
- `Aprovar este vídeo`: `video-final/corte-aprovado.mp4` com o mesmo tamanho do `corte.mp4`
  (122 MB), `aprovado.json` com as 5 imagens, selo `pronto` e o botão virou `Aprovado`.
- `agendar` (só o resumo, sem `--confirmar`): recusou com `youtube/instagram/tiktok: falta o aviso
  de IA`, porque o vídeo aprovado tem 2 imagens de IA e o `post.md` deste corte não tem o aviso.

## Achados e correções
- O aviso `As imagens mudaram desde a última montagem.` só aparecia ao recarregar a página. O PUT
  do momento passou a devolver `montagem_desatualizada`, e o bloco avisa na hora (fix 959727f).
- Durante o desenvolvimento: o JPEG em faixa de cor cheia fazia o overlay desbotar o corte inteiro
  e a legenda. A imagem passou a ser convertida para a faixa do vídeo (`out_range=tv`). O código de
  antes de 05/11 tinha o mesmo defeito.

## Para o dono decidir
- No vídeo final que o dono fez no CapCut para este corte, a foto horizontal de Yas Marina foi
  ampliada até encher a tela. A regra escrita (`Contexto/estilo-de-imagens.md`) e a esteira usam a
  foto inteira na faixa central, sobre o fundo desfocado. Se o dono preferir encher a tela, é uma
  mudança de regra.
