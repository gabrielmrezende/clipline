# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [0.3.0] - 2026-11-15

A esteira sai do computador e do canal de origem: roda sem GPU NVIDIA, fora do Windows e em Docker, serve a outro
canal com um `clipline init` e ganha um editor de trecho no painel. Sem `clipline.toml`, tudo continua como antes.

### Instalação e canal
- Instalação em um comando: `scripts/instalar.ps1` no Windows e `scripts/instalar.sh` no Linux e no macOS. Confere o
  Python e o Node, cria o `.venv`, gera o build do painel, cria as pastas que faltam e roda o `doctor`.
- `clipline init` cria as pastas e o `clipline.toml` de um canal novo, sem sobrescrever nada.
- `clipline.toml` cobre as pastas (`[pastas]`, inclusive a de entrada), os encerramentos, a logo, a sobreposição, o
  idioma e o prefixo das credenciais. A variável `CLIPLINE_RAIZ` troca a raiz.
- Imagem Docker em CPU com o painel e o `baixar`; `compose.yaml` monta as pastas do canal, com as de leitura só para
  leitura, e publica a porta só em `127.0.0.1`.
- `doctor` mostra as pastas e a identidade em uso, os extras opcionais, se a chave da Anthropic existe (sem mostrá-la),
  onde o `transcrever` vai rodar (GPU ou CPU) e quantas músicas do catálogo estão no disco.

### Esteira
- `transcrever` e `vozes` aceitam `--dispositivo auto|cuda|cpu`. Sem GPU NVIDIA, ou com a GPU sem o cuBLAS, o `auto`
  transcreve na CPU com o `medium` em int8. Uma falta de biblioteca do CUDA no meio da transcrição também recua para a
  CPU.
- Idioma do canal (`[transcricao] idioma`): vale para o Whisper, as listas da limpeza, o filtro de pessoa real, a
  legenda e os textos fixos dos cartões ("Fonte"/"Source", "SIGA"/"FOLLOW"). O "I" do inglês fica maiúsculo na
  legenda.
- `baixar <url>`: baixa um vídeo com o yt-dlp para `0 - Entrada/`, depois do resumo e do aviso de direitos
  (`--confirmar`).
- Imagens de IA verticais na OpenAI (864x1536) nos modelos que aceitam; licenças aceitas do Wikimedia no
  `clipline.toml`, com aviso da CC BY-SA.

### Enquadramento
- Acompanhamento suave: dentro de um plano, o recorte segue o rosto de quem fala sem tremer.
- Tela dividida: diálogo rápido entre duas pessoas da mesma cena sai empilhado.
- Os dois ficam desligados por padrão, na seção `[enquadramento]` do `clipline.toml`.

### Painel
- Bloco **Trecho**: o início e o fim do corte mudam com um clique na transcrição, com as falas dos outros cortes
  marcadas. Antes de trocar, o painel diz o que muda e o que se perde; o corte é preparado e montado de novo.
- Player de revisão com atalhos (J, K, L, quadro a quadro, velocidade), lista de atalhos no `?` e as áreas que o
  TikTok, os Shorts e os Reels cobrem.
- As remoções da limpeza aparecem na linha do corte, com a lista do que saiu.
- Fila persistente: sobrevive a um reinício (o que rodava aparece como interrompido), cancela e tenta de novo. O
  andamento chega por eventos (SSE), com consulta periódica de reserva.
- Diálogo de confirmação próprio no lugar do `window.confirm`, com o custo no botão e o foco em Cancelar quando a ação
  gasta ou não volta.
- Tema claro, escuro ou do sistema, escolhido no topo; esqueletos no lugar do "Carregando…"; telas carregadas sob
  demanda.
- React Router 7, Vite 8 e Vitest 5; `npm audit` sem nenhum aviso. O build pede Node 22.12 ou mais novo.

### Publicação
- Tarefa agendada também no Linux (systemd do usuário ou cron) e no macOS (launchd); `publicar desinstalar-tarefa`.
  Registro em `logs/publicar.log`, com rotação, e trava com PID e hora de início.
- YouTube: envio retomável em partes; tags, playlist e miniatura opcionais no `post.md`.
- TikTok: PKCE no login, no formato do Login Kit para desktop.

### Agente
- Servidor MCP (`esteira mcp`): a esteira em ferramentas tipadas, com gravações pelo contrato e nenhuma ferramenta que
  confirme. Com ele, dá para tirar o shell do agente.
- `revisao-visual`: um modelo de visão olha quadros de cada corte montado e grava `revisao-visual.md`. Sem
  `--confirmar`, só mostra o custo.
- Classificador opcional de pessoa real (`[ia] classificador = true`), uma segunda trava antes de gerar imagem de IA.
- As travas valem também para a ferramenta PowerShell, protegem a pasta de programas do `clipline.toml` e o próprio
  `clipline.toml`, e bloqueiam mexer em tarefas agendadas.

### Correções
- `musicas baixar` pulava toda faixa do catálogo; num clone novo, sem os `.mp3`, não baixava nada e o `montar` parava
  com "música não encontrada". Agora baixa a faixa catalogada que falta no disco.
- `transcrever --dispositivo auto` numa GPU sem o cuBLAS baixava o `large-v3` e quebrava; agora vai para a CPU.
- O editor de trecho mostrava `[Errno 2]` com o caminho inteiro quando faltava o `episodio.json`.
- `%` no nome da pasta de entrada virava campo do yt-dlp.
- Um log que não abre não impede mais o `publicar rodar`.
- Log do servidor MCP em UTF-8.
- O instalador não chama o `init` quando já há `clipline.toml`, `CLIPLINE_RAIZ` ou as pastas do canal.

### Repositório
- CI com Python 3.12 e 3.13, um job no Windows, cache do pip, ffmpeg fixado por SHA e Dependabot;
  `requirements-ci.txt` com versões fixas; ruff também em `scripts/`.
- `CODE_OF_CONDUCT.md`, `.editorconfig`, pre-commit e `CITATION.cff`.
- Extras `entrada`, `mcp` e `ia` no `pyproject.toml`.

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
