---
description: Faz os cortes de um episódio, da transcrição à revisão (etapas 1 a 10 de docs/operacao.md).
argument-hint: "<vídeo em ../1 - Programas> --quadro Q --numero N --convidado C"
---

Faça os cortes do episódio: $ARGUMENTS

1. Rode `.venv\Scripts\python.exe -m esteira doctor`. Se algo essencial faltar, pare e diga ao dono o que instalar.
2. Siga `docs/operacao.md`, etapas 1 a 10, usando as skills `escolher-cortes`, `momentos-de-imagem` e
   `textos-e-calendario`.
3. Depois de cada arquivo que você gravar, rode `esteira validar` na pasta do episódio.
4. Pare só na pausa da etapa 7 (confirmação do download das fotos) e no fim.
5. No fim, mostre `esteira status` e diga ao dono para revisar e aprovar no painel. Nada é publicado.
