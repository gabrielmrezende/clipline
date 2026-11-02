# Montagem automática dos cortes: design

Data: 2026-11-02
Status: desenho aprovado em conversa, spec aguardando revisão do dono do canal.

## 1. Objetivo

Automatizar quase todo o trabalho dos cortes. A esteira passa a entregar o
vídeo final pronto, sem edição no CapCut, e o dono do canal só aprova no
final.

O projeto foi dividido em quatro partes, feitas nesta ordem. Cada parte tem
sua própria spec, plano e implementação, e só começa depois que a anterior
funcionar num episódio real.

1. Motor de montagem (esta spec).
2. Música: biblioteca livre, escolha pelo clima e registro de licença.
3. B-roll: busca de fotos livres, cartões de notícia e ilustrações de IA
   locais, inseridos no tempo da fala.
4. Postagem: APIs oficiais do YouTube, Instagram e TikTok, depois da
   aprovação.

## 2. Decisões gerais

- Aprovação humana em um único ponto: o corte pronto, com texto e data.
- O vídeo é montado pela esteira, sem CapCut.
- Somente ferramentas gratuitas. As etapas de julgamento continuam no
  Claude Code, sem chave de API.
- A esteira começa por um comando do dono do canal no Claude Code, por
  episódio.
- Estilo visual atual do canal, com destaque automático de palavras-chave.
- Montagem com ffmpeg e Python, ampliando `esteira/render.py`.
- Até 8 a 10 cortes por episódio, conforme o episódio permitir.
- Instagram recebe os 4 cortes mais fortes. TikTok e Shorts recebem todos.

## 3. Fluxo do comando

O dono do canal diz "faça os cortes do episódio X". O Claude Code roda, sem
parar no meio:

1. Transcrever (script, como hoje).
2. Escolher cortes (Claude): até 8 a 10, seguindo `Contexto/`, e marcar os
   4 mais fortes para o Instagram. Os candidatos descartados ficam
   registrados com o motivo.
3. Enquadrar (Claude): lê `planos.jpg` e a transcrição e grava o
   enquadramento, como hoje, sem pausa.
4. Marcar destaques (Claude): no máximo uma palavra por tela de legenda, e
   não em todas. Só nomes, números e a palavra central do argumento.
5. Montar (script novo): gera `final.mp4` de cada corte.
6. Textos e calendário (Claude), como hoje, com as novas regras de
   publicação.
7. Gerar `revisao.md` e parar para a aprovação.

## 4. Receita do corte

Cada corte tem um `montagem.json`, que descreve tudo o que entra no vídeo.
O motor só lê a receita. As partes 2 e 3 só preenchem campos dela.

```json
{
  "versao": 1,
  "faixas": [[724.12, 760.30], [761.10, 801.40]],
  "planos": [{"inicio": 724.12, "fim": 740.0, "x": 0.5, "y": 0.4, "zoom": 1.35}],
  "legenda": [{"inicio": 0.0, "fim": 1.8, "texto": "o gripen é um caça", "destaque": "gripen"}],
  "imagens": [{"inicio": 18.0, "fim": 21.0, "arquivo": "imagens/01-gripen.jpg"}],
  "musica": {"arquivo": "...", "volume_db": -20},
  "encerramento": true
}
```

Tempos de `legenda` e `imagens` são do corte final. Tempos de `faixas` e
`planos` são do episódio. A receita é validada antes da montagem: tempos
dentro do corte, imagens sem sobreposição, arquivos existentes e destaque
presente no texto da tela.

Até a parte 3, o campo `imagens` é preenchido com as imagens que o dono do
canal colocar em `imagens/` e listar em `imagens.md`. Até a parte 2,
`musica` pode ficar vazio.

## 5. Motor de montagem

Uma única passada do ffmpeg, com estas camadas:

1. Vídeo: faixa central, fundo desfocado e zoom por plano, como hoje.
2. Imagens: tela cheia, de 2 a 5 segundos, no tempo da fala. A legenda não
   aparece durante a imagem. A forma de entrada (corte seco ou aproximação
   leve) segue os cortes de referência; conferir isso é a primeira tarefa
   do plano.
3. Legenda: estilo de `estilo-de-legenda.md`, gerada em ASS. O destaque
   sai em amarelo.
4. Música: de 18 a 22 dB abaixo da voz, com redução extra enquanto há fala
   (ducking). Começa com a fala e some antes do encerramento. Repete se for
   curta e é cortada se for longa. Sem música, o vídeo sai sem música e a
   revisão avisa.
5. Encerramento: o mesmo vídeo Final Corte de hoje.

Usa NVENC e cai para libx264 se falhar, como hoje.

Saídas por corte: `final.mp4`, `montagem.json`, `legenda.srt` e
`registro.json`. Deixam de ser gerados `corte.mp4` e
`corte-sem-legenda.mp4`.

Checagens antes de entregar: o arquivo abre, a duração bate com a esperada
(tolerância de 0,5 s), o áudio não satura, e nenhuma imagem ou destaque cai
fora do corte.

## 6. Revisão e aprovação

`revisao.md`, na pasta do episódio, tem um bloco por corte:

- link para `final.mp4`, título e redes (Instagram ou só TikTok e Shorts);
- data e horário sugeridos;
- frase anterior e posterior ao trecho, para conferir o sentido;
- alertas: sem música, licença a conferir, nome possivelmente errado.

No fim, os candidatos descartados e o motivo.

O dono do canal aprova em conversa. A aprovação é gravada em
`aprovacao.json`, que a parte 4 usará para postar:

```json
{"cortes": [{"numero": 1, "status": "aprovado", "redes": ["youtube", "tiktok", "instagram"]}]}
```

Correção: o Claude altera só o `montagem.json` daquele corte e remonta só
esse corte. Correção que vale para os próximos cortes vira regra em
`Contexto/`, com aprovação.

## 7. Erros

- Um corte com erro é marcado em `revisao.md` e não impede os demais.
- O vídeo é gravado em arquivo temporário e só vira `final.mp4` depois das
  checagens.
- Se `final.mp4` já existir, a esteira pergunta antes de sobrescrever.

## 8. Mudanças de regra

Estas alterações são aplicadas na implementação, com o texto mostrado ao
dono do canal antes de salvar:

- `CLAUDE.md`: o resultado passa a ser o vídeo final para aprovação, não
  rascunho para o CapCut. Continua proibido publicar sem aprovação.
- `estilo-dos-cortes.md`: até 8 a 10 cortes por episódio. A IA escolhe os
  cortes e a aprovação humana acontece no corte pronto. A música passa a
  ser escolhida pela esteira (parte 2). O resultado deixa de ser rascunho
  para o editor.
- `estilo-de-legenda.md`: destaque automático em amarelo, no máximo uma
  palavra por tela. Sai a entrega de versão sem legenda.
- `estilo-de-imagens.md`: inserção pela esteira, conforme `montagem.json`.
- `redes-e-publicacao.md`: Instagram com os 4 cortes mais fortes; TikTok e
  Shorts com todos, 1 a 2 por dia, antes do próximo episódio.
- `Automacao/docs/operacao.md`: novo fluxo sem pausa e etapa de montagem.

## 9. Testes

1. Testes automáticos com vídeo curto: validação da receita, imagem no
   tempo certo, legenda escondida durante a imagem, destaque em amarelo,
   mixagem com música, duração final.
2. Teste real com um episódio inteiro, de ponta a ponta.
3. Comparação visual com `Contexto/cortes-de-referencia.md`.

## 10. Critérios de sucesso

- Pelo menos 6 cortes do episódio de teste aprovados sem abrir editor.
- O tempo entre o comando e a revisão pronta é aceito pelo dono do canal.
- Nenhum corte aprovado muda o sentido da fala.
- Nomes principais saem corretos, e erros novos vão para o glossário.

## 11. Fora desta parte

- Escolha automática de música (parte 2).
- Busca e geração de imagens (parte 3).
- Postagem e agendamento (parte 4).
- Efeitos dinâmicos: legenda animada, zoom pulsante, efeitos de som.
- Detecção de rosto e identificação automática de quem fala.
- Disparo automático por pasta.
