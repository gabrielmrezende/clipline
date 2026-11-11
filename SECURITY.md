# Segurança

## Como relatar

Não abra issue pública para falha de segurança. Use o relato privado do GitHub
(**Security → Report a vulnerability** neste repositório). Diga o que é, como reproduzir e o impacto que você vê.

## O que conta

- Publicar, gastar com API de imagem ou sobrescrever arquivo sem a confirmação do dono.
- O agente (Claude Code) conseguir contornar as travas de `.claude/hooks/travas.py`.
- Ler ou vazar chave, token ou código de acesso do painel.
- Gravar fora de `2 - Cortes/` e da pasta do repositório.
- Uma página de outra origem conseguir chamar a API do painel.

## Como o projeto se protege

Resumo em [`docs/seguranca-do-agente.md`](docs/seguranca-do-agente.md): travas do agente, contrato dos arquivos que
ele escreve, defesa de origem e cabeçalhos do painel, código de acesso na rede local, segredos no Gerenciador de
Credenciais e confirmação humana para publicar.
