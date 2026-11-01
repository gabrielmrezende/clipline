# Esteira de cortes do Tudo é Política: design

Data: 2026-11-01
Status: desenho aprovado em conversa, spec aguardando revisão do dono do canal.

## 1. Objetivo

Reduzir o trabalho manual de achar trechos, legendar, sugerir imagens e
preparar textos de cortes dos quadros Por Trás do TCC e Entre Assuntos.
O resultado é sempre um rascunho que o dono do canal revisa e finaliza no
CapCut. Nada é publicado automaticamente nesta versão.

## 2. Decisões

- Abordagem: scripts locais em Python para o trabalho mecânico. As etapas
  de julgamento são feitas pelo Claude Code, em sessão interativa.
- Não usa chave de API nesta versão.
- O vídeo fica local. O texto da transcrição é enviado ao Claude para gerar
  sugestões.
- As regras editoriais ficam em `Contexto/` e não são duplicadas no código:
  - `canal.md`
  - `temas-e-formatos.md`
  - `estilo-dos-cortes.md`
  - `estilo-de-legenda.md`
  - `estilo-de-imagens.md`
  - `redes-e-publicacao.md`
  - `cortes-de-referencia.md`
  - `glossario.md`

## 3. Estrutura de pastas

```text
Tudo é Política/
  Entre Assuntos/, Por Trás do TCC/ ...   (somente leitura pela esteira)
  Contexto/
  Automacao/
    docs/                                 (specs e planos)
  Cortes/
    <Quadro NN - Convidado>/
      episodio.json
      transcricao/
      candidatos.md
      aprovados.json
      NN-titulo-do-corte/
        corte.mp4
        corte-sem-legenda.mp4
        legenda.srt
        edicoes.md
        imagens.md
        imagens/
        post.md
        registro.json
```

Os episódios não são movidos, renomeados nem alterados. `Automacao/` é o
único repositório Git. Vídeos não entram no Git.

## 4. Ambiente

- Windows 11, RTX 4060 Laptop com 8 GB, i9-13900H, 16 GB de RAM.
- Python 3.12 em ambiente próprio dentro de `Automacao/`. O Python 3.14 do
  sistema não é alterado.
- ffmpeg próprio em `Automacao/`. O ffmpeg do CapCut não é dependência.
- Fonte Montserrat Bold disponível para a queima de legenda.

## 5. Estágios

Cada estágio grava seu resultado em pasta e pode ser refeito sozinho. Se o
resultado já existir, o script para e pergunta antes de sobrescrever.

### 5.1 Transcrever (script)

Entrada: caminho da versão publicada do episódio. Em caso de dúvida entre
versões, a esteira pergunta.

Processamento: `faster-whisper` na GPU, em português, com modelo grande,
tempo por palavra e nomes de `glossario.md` como orientação.

Saída: `episodio.json` e, em `transcricao/`, arquivo completo por palavra e
texto legível com marcas de tempo.

Falha: em falta de memória de vídeo, tenta modo mais leve. Se falhar de
novo, para com erro e não grava transcrição parcial como concluída.

### 5.2 Sugerir trechos (Claude Code)

Entrada: transcrição e `Contexto/`.

Saída: `candidatos.md`, com 5 a 10 candidatos. Cada candidato contém título,
início, fim, duração, abertura, fim, motivo, riscos e clima da música.

Antes de entregar, confere:
- início e fim batem com palavras reais da transcrição;
- duração entre 60 e 120 segundos;
- início e fim não cortam frase;
- o trecho anterior e o posterior não mudam o sentido da fala.

O dono do canal aprova em conversa. A aprovação é gravada em
`aprovados.json`. As sugestões são palpites baseados em texto e não medem
tom de voz nem reação visual.

### 5.3 Cortar (script)

Entrada: `aprovados.json` e transcrição.

1. Recorta o trecho aprovado.
2. Remove pausas longas e gaguejos com margem de segurança, mantendo "né" e
   "tá", e lista cada remoção em `edicoes.md`.
3. Monta 1080x1920, 30 fps: faixa central entre 23% e 77% da altura, com
   recorte central fixo, e fundo do próprio vídeo ampliado e desfocado.
4. Gera `legenda.srt`, corrige nomes com o glossário e queima legenda em
   Montserrat Bold branca, com contorno preto, em até 2 linhas, em cerca de
   84% da altura.
5. Adiciona o cartão de cerca de 3 segundos baseado em
   `Entre Assuntos/Juliano Viegas/Cortes/Final Vídeo.mp4`.
6. Grava `corte.mp4`, `corte-sem-legenda.mp4` e `registro.json`, sem música.

Confere se o arquivo final abre e tem a duração esperada. Um corte com erro
é marcado e não impede os demais.

Enquadramento: a primeira versão usa recorte central fixo. Se o teste do F1
mostrar falhas frequentes, avaliaremos ajuste por trecho ou detecção de
rosto em um novo ciclo.

### 5.4 Sugerir imagens (Claude Code + script de cartão)

Entrada: legenda final do corte e `Contexto/`.

Saída: `imagens.md`, com 4 a 8 sugestões. Cada sugestão contém tempo de
início e fim, tipo, fala relacionada, origem, autor, licença e link.

| Tipo | Tratamento |
|---|---|
| Foto livre ou oficial | Busca, anota origem e licença, baixa após aprovação |
| Pessoa real sem foto livre | Sugere trecho do vídeo; foto de agência só por decisão humana |
| Notícia | Confere fonte original; script gera cartão 1080x1920 do canal |
| Objeto ou cenário | Escreve prompt para geração manual em ferramenta de IA |

Regras: nunca gerar imagem de IA de pessoa real. Nunca gerar página imitando
veículo real. A licença é informação registrada, não parecer jurídico.
A inserção das imagens é manual no CapCut, e elas cobrem a legenda queimada.

### 5.5 Textos de post (Claude Code)

Saída: `post.md`, com título e descrição do YouTube, textos adaptados para
Instagram e TikTok, aviso de IA quando aplicável e clima da música.

Os textos de Instagram e TikTok usam regras provisórias até haver exemplos
do canal em `redes-e-publicacao.md`.

## 6. Proteções

- A esteira grava somente em `Cortes/` e `Automacao/`.
- Senhas, chaves e tokens não entram em `Contexto/`.
- Nenhum arquivo do canal é apagado, movido ou renomeado sem confirmação.
- Arquivos horizontais e versões intermediárias não são usados como
  referência de estilo.
- Downloads de imagem acontecem somente após aprovação.

## 7. Testes

1. Testes automáticos com vídeo curto: tempos, limpeza de fala, legenda e
   criação de pastas.
2. Teste real com o episódio do F1, de ponta a ponta, gerando 3 a 5 cortes.
3. Comparação visual com `cortes-de-referencia.md`.
4. Avaliação do dono do canal no CapCut.

## 8. Critérios de sucesso

- Pelo menos 3 candidatos do F1 são aprovados.
- `corte.mp4` e `corte-sem-legenda.mp4` abrem no CapCut sem conversão.
- Nomes principais saem corretos, e erros novos vão para o glossário.
- A legenda fica sincronizada e sem quebras estranhas.
- Nenhuma remoção de pausa muda o sentido da fala.
- O tempo total por corte, incluindo revisão, é claramente menor que o
  processo manual. A linha de base será medida no primeiro corte manual de
  comparação ou informada pelo dono do canal.

## 9. Fora desta versão

- Postagem automática
- Geração automática de imagens de IA
- Inserção automática de imagens ou música
- Projeto editável do CapCut
- Detecção de rosto
- Identificação automática de quem fala
- Painel visual

Ordem futura: imagens mais automatizadas e, por último, postagem automática.
