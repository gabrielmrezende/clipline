# Contribuindo com o clipline

Obrigado pelo interesse. O projeto é em português: código, comentários, mensagens, interface e documentação.

## Antes de começar

1. Abra uma issue antes de um pull request grande. Correções pequenas podem ir direto.
2. Leia os [princípios de projeto](README.md#princípios-de-projeto). Dois não se negociam: nada publica, gasta ou
   sobrescreve sem confirmação humana, e regra editorial do canal não entra no código.

## Ambiente

```bash
git clone https://github.com/gabrielmrezende/clipline.git Automacao
cd Automacao
python -m venv .venv
.venv/bin/pip install -e ".[dev,painel]"      # Windows: .venv\Scripts\pip
cp -r Contexto.exemplo ../Contexto            # regras de exemplo, irmãs do repositório
cd painel-web && npm ci && npm run build
```

O ffmpeg vem de `bin/` (Windows) ou do `PATH`. `clipline doctor` diz o que falta.

## Testes

| O quê | Comando |
|---|---|
| Esteira e API do painel | `python -m pytest -n auto` |
| Lint do Python | `ruff check esteira tests .claude/hooks` |
| Tipos do painel | `cd painel-web && npx tsc -b` |
| Componentes do painel | `npm test` |
| Ponta a ponta | `npm run e2e` (com `PLAYWRIGHT_CHROMIUM=/caminho/do/chrome` se não der para baixar o do Playwright) |

Os testes não usam GPU, rede nem vídeos reais. Modelos, APIs e downloads entram como dependências trocáveis por falsos;
o ffmpeg gera vídeos sintéticos de poucos segundos. Um teste novo que precise da internet está errado.

## Estilo

- Funções pequenas, nomes em português, lógica pura separada de I/O (ver `enquadrar.py`, `limpeza.py`, `legenda.py`).
- Toda gravação de estado é atômica (`caminhos.gravar_atomico`) e passa por `garantir_escrita`.
- Mensagem de erro diz o arquivo, o campo e o que fazer, numa linha.
- Mudou um arquivo que o agente escreve? Atualize `esteira/contrato.py`, `docs/esquemas/` e a skill correspondente.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/pt-br/) em português: `feat:`, `fix:`, `docs:`, `refactor:`,
`test:`. Uma mudança por commit.

## O que nunca vai para o repositório

Vídeos, músicas, modelos `.onnx`, `bin/`, chaves, tokens, `clipline.toml`, `Contexto/` real e qualquer dado de canal.
