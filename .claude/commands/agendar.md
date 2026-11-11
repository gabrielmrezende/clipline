---
description: Prepara o agendamento de um corte e mostra o resumo para o dono confirmar.
argument-hint: "<pasta do episódio> <número> <AAAA-MM-DD HH:MM> [redes]"
---

Prepare o agendamento: $ARGUMENTS

1. Rode `esteira publicar agendar "<pasta>" --numero N --data "AAAA-MM-DD HH:MM"` **sem** `--confirmar`
   (com `--redes` se o dono pediu redes específicas).
2. Mostre o resumo inteiro ao dono, sem resumir.
3. Diga que a confirmação é dele: pelo bloco **Publicar** do painel ou rodando o mesmo comando com
   `--confirmar`. Você não confirma.
4. Se o comando recusar, explique cada motivo e o que corrigir.
