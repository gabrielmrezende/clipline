# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [0.2.0] - 2026-11-11

Rodada de melhorias a partir da auditoria de 11/11/2026 (`docs/auditoria/`).

### Agente (Claude Code)
- `CLAUDE.md` versionado, com as regras invioláveis e o aviso de que conteúdo é dado, não instrução.
- Travas por hook (`.claude/hooks/travas.py`): o agente não confirma, não sobrescreve, não mexe em credenciais nem
  grava em pastas protegidas. Falha fechada, com testes.
- Skills `escolher-cortes` (com nota explicada por corte e gancho), `momentos-de-imagem` e `textos-e-calendario`;
  comandos `/episodio`, `/corrigir-corte` e `/agendar`.
- `Contexto.exemplo/` com modelos das regras editoriais.
- Contrato dos arquivos do agente (`esteira/contrato.py`, `docs/esquemas/`) e campo `origem` (modelo, data, regras).

### CLI
- `validar` confere todos os arquivos do agente e aceita `--json`.
- Novos: `trecho` (palavras, tempos e quem fala de um intervalo), `status` (etapa e próximo passo; `--regras`),
  `doctor` (ambiente). Instalável com `pip install -e .`; comando `clipline`.
- JSON quebrado, arquivo ausente ou campo errado viram mensagem de uma linha, sem traceback.
- `vozes` grava `transcricao/texto-falantes.md`: transcrição com quem fala e as pausas longas.

### Esteira
- A limpeza só corta uma pausa se o áudio confirmar o silêncio (ffmpeg `silencedetect`) e ninguém falar nela;
  as mantidas aparecem como "pausa com som mantida" em `edicoes.md`. Repetição com vírgula ("muito, muito") é ênfase.
- O glossário inteiro vai para o Whisper em `hotwords`; o `initial_prompt` não corta mais nome no meio.
- Prompt de IA que cita cargo público ("o presidente", "a senator") é recusado, além dos nomes do glossário.
- `clipline.toml` (opcional): duração dos cortes, identidade, legenda e voz. Sem ele, tudo como antes.
- Legenda "palavra": a palavra falada acende (opcional). Voz normalizada por EBU R128 (opcional).
- `imagens sugerir` não perde mais as fotos anteriores se o download falhar.
- Gravação atômica dos arquivos de estado; ffmpeg pelo `PATH` fora do Windows.

### Publicação
- Rótulo nativo de conteúdo de IA: `status.containsSyntheticMedia` no YouTube e `post_info.is_aigc` no TikTok direto.
- O agendamento exige o crédito de cada foto livre que está no vídeo, em cada texto publicado.
- PKCE no login do Google; erro claro quando a porta do retorno está ocupada pelo painel.

### Painel
- Bloco **Publicar**: resumo, confirmação do resumo exato, fila do corte e cancelar.
- Bloco **Legenda**: corrigir o texto das telas e montar de novo.
- Recusa de pedidos de outra origem, CSP e cabeçalhos de segurança; sessão de 7 dias; `POST /api/sair`; trava de
  login por aparelho, com tempo que dobra.
- Linha do corte pelo teclado; abas com `aria-controls` corretos; fala dos trechos para leitor de tela; borda dos
  campos com contraste 3:1; volta à página depois de entrar; manifesto completo.

### Repositório
- CI no GitHub Actions (pytest, ruff, tsc, Vitest, build, Playwright).
- `CONTRIBUTING.md`, `SECURITY.md`, modelos de issue e de pull request.
- Testes rodam fora do Windows; e2e com `PLAYWRIGHT_CHROMIUM`.

## [0.1.0] - 2026-11-10

Primeira versão pública.
