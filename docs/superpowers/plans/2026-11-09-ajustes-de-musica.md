# Ajustes de música no painel: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar a faixa e o volume da música de um corte pelo painel, com catálogo do episódio, prévia de 15 s e remontagem do `corte.mp4` numa fila.

**Architecture:** Funções puras novas em `esteira/musica.py`, `esteira/publicar/post.py` e `esteira/render.py`. Um fluxo `trocar_musica` em `esteira/painel/troca_musica.py`, uma fila de um trabalhador em `esteira/painel/fila.py` e rotas novas em `esteira/painel/rotas_musica.py`. No frontend, um componente `BlocoMusica` na tela do corte.

**Tech Stack:** Python 3.12, FastAPI, pytest; React 18 + TypeScript, Vitest, Testing Library, Playwright. Nada novo para instalar.

**Spec:** `docs/superpowers/specs/2026-11-09-ajustes-de-musica-design.md` (e a do painel, `docs/superpowers/specs/2026-11-07-painel-de-revisao-design.md`).

Comandos a partir de `Automacao/`. Python: `.venv\Scripts\python.exe`. Frontend: em `painel-web/`, `npm test`, `npm run build`, `npm run e2e`.

## Global Constraints

- Português do Brasil em código, nomes, mensagens e testes.
- Volume da música: de `-30` a `-18` dB (`receita.VOLUME_MINIMO`/`VOLUME_MAXIMO`), passo 1 na tela.
- Faixas só da biblioteca: `musicas/catalogo.json` (campo `arquivo`, relativo a `musicas/`). `Musica.arquivo` no `montagem.json` é `str(MUSICAS / faixa.arquivo)`.
- Catálogo do episódio: `musicas-do-episodio.json` na pasta do episódio, formato `{"faixas": [{"arquivo": "...", "motivo": "..."}]}`.
- Chave do `uso.json`: `"<nome da pasta do episódio>/<nome da pasta do corte>"`.
- Prévia: 15 s, só áudio AAC `.m4a`, em `<corte>/trabalho/previa-musica.m4a`, ffmpeg de `bin/`, tempo limite de 60 s.
- Selos, em ordem de prioridade: `erro`, `vídeo final desatualizado`, `com alerta`, `sem vídeo final`, `pronto`.
- Estados do pedido: `na fila`, `montando`, `pronto`, `erro`. Um pedido ativo por corte.
- Toda gravação passa por `caminhos.garantir_escrita` (com `base_extra` = pasta de `--cortes`). `1 - Programas/` só é lido. `video-final/` nunca é escrito.
- Mensagens exatas da spec (confirmação de vídeo final, andamento, avisos de crédito) entram verbatim.
- Sem testes no keyring real, no `2 - Cortes/` real nem no ffmpeg real (executor falso), exceto a fumaça.

## Review Focus

1. Nome de faixa com espaço ou acento (`Sunshine A.mp3`) na URL `/api/musicas/{clima}/{arquivo}`: codificado no front e aceito na API. Teste na Task 6 (API) e na Task 7 (front).
2. Corte cujo `montagem.json` não tinha música (`musica: null`): a troca funciona; `trocar_credito` não acha crédito antigo e devolve os avisos, sem gravar texto errado. Teste na Task 2 e na Task 4.
3. Só o volume mudou (mesma faixa): monta de novo, não toca o `post.md` e não muda o `uso.json`. Teste na Task 4.
4. Prévia com `inicio` perto do fim ou além do fim do corte: perto do fim gera o que sobra; além do fim recomeça de 0. Teste na Task 3.
5. Dois cortes diferentes pedidos ao mesmo tempo: o segundo fica `na fila` até o primeiro terminar. Teste na Task 5.

---

### Task 1: Catálogo do episódio e registro de uso

**Files:**
- Modify: `esteira/musica.py`, `docs/operacao.md` (etapa 6, seção "Música")
- Test: `tests/test_musica.py`

**Interfaces:**
- Produces:
  - `ler_musicas_do_episodio(pasta: Path, catalogo: list[Faixa]) -> tuple[list[tuple[Faixa, str]], list[str]]` (faixa e motivo; avisos).
  - `MUSICAS_DO_EPISODIO = "musicas-do-episodio.json"`.
  - `registrar_uso(chave: str, faixa: Faixa, pasta_musicas: Path = MUSICAS, agora: Callable[[], datetime] = datetime.now) -> None`: tira a chave e a acrescenta no fim com `{"arquivo": faixa.arquivo, "data": agora().isoformat(timespec="seconds")}`, como `atualizar_musica` faz. `atualizar_musica` passa a usá-la.

- [ ] **Step 1: Testes que falham:**
  - `test_musicas_do_episodio_ausente`: `([], [])`.
  - `test_musicas_do_episodio_ordem_e_motivo`: duas faixas do catálogo na ordem do arquivo, com os motivos.
  - `test_musicas_do_episodio_fora_do_catalogo`: uma faixa desconhecida é ignorada, e o aviso é `"faixa fora do catálogo: x/y.mp3"`.
  - `test_musicas_do_episodio_ilegivel`: `{quebrado` → `([], ["musicas-do-episodio.json ilegível"])`; o mesmo para `{"faixas": "x"}`.
  - `test_registrar_uso_move_para_o_fim`: chave existente sai do meio e vai para o fim, com a data do relógio injetado.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_musica.py -q`. Esperado: os novos falham.
- [ ] **Step 3:** Implementar e fazer `atualizar_musica` chamar `registrar_uso`.
- [ ] **Step 4:** Rodar `tests/test_musica.py` e `tests/test_cli.py`. Esperado: tudo passa.
- [ ] **Step 5: `operacao.md`** (o texto já foi aprovado pelo dono antes da execução):
  - na seção "Música" da etapa 6, acrescentar: "Depois de preparar, gravar `musicas-do-episodio.json` na pasta do episódio com 8 a 12 faixas do `musicas/catalogo.json` que combinem com o tom do episódio, cada uma com um motivo curto. Formato: `{\"faixas\": [{\"arquivo\": \"tenso/Ice Flow.mp3\", \"motivo\": \"tensão contida\"}]}`. O painel mostra essas faixas primeiro.";
  - trocar o parágrafo "O comando `musica` não serve para escolher outra faixa. Para trocar a faixa de um corte, editar …" por: "Para trocar a faixa ou o volume de um corte, usar o painel (bloco Música na tela do corte). Ele monta o corte de novo e troca o crédito no `post.md`."
- [ ] **Step 6: Commit** `feat: catálogo de músicas do episódio e registro de uso`.

### Task 2: `trocar_credito` no `post.md`

**Files:**
- Modify: `esteira/publicar/post.py`
- Test: `tests/test_publicar_post.py`

**Interfaces:**
- Consumes: `_linhas`, `_limites_secao`, `_fim_predominante`, `interpretar_post`, `somente_leitura_do_texto`, `_repetidas`, `garantir_escrita`, `ErroPost` (já existem em `post.py`); `receita.Musica`.
- Produces: `trocar_credito(caminho: Path, antiga: Musica | None, nova: Musica, base: Path | None = None) -> list[str]` (avisos).
  - Avisos exatos: `"<rede>: crédito antigo não encontrado; confira o crédito"` (rede em `youtube`, `instagram`, `tiktok`) e `"seção Música não atualizada"`.
  - Com `antiga is None`: nada a substituir nos textos (três avisos de crédito). A seção Música recebe `Crédito: <novo>` se a linha existir, senão aviso.
  - Com `antiga.arquivo == nova.arquivo`: devolve `[]` sem ler nem gravar.

- [ ] **Step 1: Testes que falham**, sobre `tests/dados_post_corte1.md` (crédito Ice Flow) copiado em `tmp_path`, com `base=tmp_path`:
  - `test_trocar_credito_quatro_lugares`: depois da troca para "Música: Clear Air — Kevin MacLeod (incompetech.com), licença CC BY 4.0", o crédito novo está na descrição do YouTube, no Instagram e no TikTok; a seção Música tem `Faixa: Clear Air (Kevin MacLeod, incompetech.com)` e `Crédito: <novo>`; o crédito antigo não aparece em lugar nenhum; avisos `[]`.
  - `test_trocar_credito_editado_a_mao`: Instagram sem o crédito antigo exato → texto do Instagram idêntico, aviso do Instagram, os outros trocados.
  - `test_trocar_credito_crlf_e_misto`: arquivo CRLF com um trecho LF; depois da troca, as linhas não tocadas mantêm o fim original e `ler_post` lê tudo.
  - `test_trocar_credito_sem_secao_musica`: seção removida → aviso `"seção Música não atualizada"`, textos trocados.
  - `test_trocar_credito_mesma_faixa`: bytes e mtime iguais, `[]`.
  - `test_trocar_credito_sem_musica_antiga`: `antiga=None` → três avisos de crédito e a linha `Crédito:` da seção Música com o novo.
  - `test_trocar_credito_recusa_se_quebrar`: crédito novo `"Música: X\n## Intrusa"` (criaria uma seção nova) → levanta `ErroPost` e o arquivo fica igual byte a byte, sem `.tmp`.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_publicar_post.py -q`. Esperado: os novos falham.
- [ ] **Step 3:** Implementar reaproveitando as funções de linhas e a releitura antes do `os.replace`. A conferência exige: os quatro campos iguais aos esperados (texto antigo com a substituição) e as seções só de leitura iguais, exceto `Música`. Gravação atômica com `.tmp` apagado em `finally`.
- [ ] **Step 4:** Rodar o mesmo comando. Esperado: tudo passa.
- [ ] **Step 5: Commit** `feat: trocar_credito atualiza a música no post.md`.

### Task 3: Prévia de 15 s

**Files:**
- Modify: `esteira/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `_filtro_musica(entrada, musica, duracao)`, `duracao_principal`, `executar_ffmpeg` (injetável).
- Produces:
  - `trechos_da_previa(faixas: list[tuple[float, float]], inicio: float, duracao: float) -> list[tuple[float, float]]`: pura. Converte o tempo do corte em trechos do episódio. Com `inicio >= duracao_total`, usa `inicio = 0`.
  - `gerar_previa(receita: Receita, video: Path, musica: Musica, inicio: float, saida: Path, duracao: float = 15.0, executar: Callable[[list[str], Path | None], None] = executar_ffmpeg) -> Path`.
  - A voz dos trechos é concatenada (`atrim`/`concat` de áudio), e a música é mixada com `_filtro_musica(1, musica, duracao_real)`. A saída usa `-vn -c:a aac -b:a 192k`. O tempo limite é de 60 s (`ErroMidia("prévia demorou mais de 60 s")`).

- [ ] **Step 1: Testes que falham:**
  - `test_trechos_inicio_no_meio_de_uma_faixa`: `faixas=[(100,110),(200,220)]`, `inicio=5`, `duracao=15` → `[(105,110),(200,210)]`.
  - `test_trechos_perto_do_fim`: `inicio=25` → `[(215,220)]`.
  - `test_trechos_alem_do_fim_recomeca`: `inicio=40` → `[(100,110),(200,205)]`.
  - `test_gerar_previa_monta_comando`: executor falso guarda os argumentos. O `-filter_complex` contém `sidechaincompress` e `volume=-22.0dB` (`Musica(volume_db=-22)`), a saída termina em `previa-musica.m4a` e tem `-vn`.
  - `test_gerar_previa_erro_do_ffmpeg`: executor falso levanta `ErroMidia("ffmpeg falhou: x")` → a exceção sobe.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_render.py -q`. Esperado: os novos falham.
- [ ] **Step 3:** Implementar. O limite de 60 s vai como `timeout` no `subprocess.run` do executor real: acrescentar o parâmetro opcional `timeout: float | None = None` em `midia.executar_ffmpeg`/`_rodar` e converter `subprocess.TimeoutExpired` em `ErroMidia`.
- [ ] **Step 4:** Rodar `tests/test_render.py` e `tests/test_midia.py` (se existir). Esperado: tudo passa.
- [ ] **Step 5: Commit** `feat: prévia de 15 s da música com a voz do corte`.

### Task 4: Fluxo `trocar_musica`

**Files:**
- Create: `esteira/painel/troca_musica.py`
- Test: `tests/test_painel_troca_musica.py`

**Interfaces:**
- Consumes: `ler_receita`, `gravar_receita`, `Musica`, `NOME_ARQUIVO` (receita); `trocar_credito` (Task 2); `registrar_uso`, `Faixa`, `MUSICAS` (Task 1, musica); `ler_aprovados`, `pasta_do_corte`, `TRABALHO` (cortar); `ErroPost`.
- Produces:
  - `@dataclass Resultado`: `estado: str` (`"pronto"` | `"erro"`), `mensagem: str`, `avisos: list[str]`, `anterior: Musica | None`.
  - `trocar_musica(pasta_episodio: Path, numero: int, faixa: Faixa, volume_db: float, montar: Callable[[Path, int], str], base: Path | None = None, pasta_musicas: Path = MUSICAS, trava: threading.Lock | None = None) -> Resultado`. `montar` devolve a string de resultado do `montar_episodio` daquele corte (`"ok…"` ou `"erro: …"`). `trava` é a mesma `_TRAVA_GRAVACAO` do PUT do post.

- [ ] **Step 1: Testes que falham**, com o episódio de `tests/auxiliares_painel.criar_episodio` e `montar` falso:
  - `test_troca_ok`: o `montar` falso confere que o `montagem.json` já tem a faixa nova e o volume, e devolve `"ok"`. Resultado `pronto`; `post.md` com o crédito novo; `uso.json` (em `pasta_musicas=tmp_path`) com a chave `"<ep>/<pasta>"`; `anterior` igual à música antiga.
  - `test_troca_erro_restaura`: `montar` devolve `"erro: ffmpeg falhou"` → resultado `erro` com essa mensagem; `montagem.json` igual byte a byte ao original; `post.md` e `uso.json` intactos.
  - `test_troca_excecao_restaura`: `montar` levanta `RuntimeError("x")` → `erro`, `montagem.json` restaurado.
  - `test_troca_so_volume`: mesma faixa, volume -20 → `montagem.json` com -20; `post.md` e `uso.json` intactos.
  - `test_troca_sem_musica_antiga`: `montagem.json` com `musica: null` → `pronto` e os avisos de crédito da Task 2.
  - `test_troca_credito_falha`: `post.md` sem `## TikTok` → `pronto` com o aviso `"crédito não atualizado: post.md sem a seção ## TikTok"`.
  - `test_troca_sem_post`: sem `post.md` → `pronto` com o aviso `"post.md não encontrado: crédito não atualizado"`.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_troca_musica.py -q`. Esperado: falham.
- [ ] **Step 3:** Implementar na ordem da spec: guardar os bytes do `montagem.json`, gravar a música nova, montar; em `finally`, restaurar os bytes se o resultado não começar com `ok`; depois do `ok`, trocar o crédito (sob `trava`) e registrar o uso (só se a faixa mudou).
- [ ] **Step 4:** Rodar o mesmo comando. Esperado: passam.
- [ ] **Step 5: Commit** `feat: fluxo de troca de música com restauração em caso de erro`.

### Task 5: Fila de montagem

**Files:**
- Create: `esteira/painel/fila.py`
- Test: `tests/test_painel_fila.py`

**Interfaces:**
- Consumes: `trocar_musica`, `Resultado` (Task 4).
- Produces:
  - `class PedidoAtivo(Exception)`.
  - `@dataclass Pedido`: `id: str` (`secrets.token_hex(4)`), `episodio: str`, `numero: int`, `arquivo: str`, `volume_db: float`, `estado: str`, `mensagem: str = ""`, `avisos: list[str]`, `anterior: dict | None = None` (`{"arquivo", "titulo", "volume_db"}`), `criado: float`, `terminado: float | None = None`.
  - `class Fila`: `__init__(executar: Callable[[Path, int, Faixa, float], Resultado], relogio: Callable[[], float] = time.time)`. Métodos:
    - `pedir(pasta_episodio: Path, numero: int, faixa: Faixa, volume_db: float) -> Pedido`;
    - `pedidos() -> list[Pedido]` (até 50, mais recentes primeiro);
    - `pedido(id: str) -> Pedido | None`;
    - `ativo(episodio: str, numero: int) -> Pedido | None`;
    - `ultimo_pronto(episodio: str, numero: int) -> Pedido | None`;
    - `parar(timeout: float = 5) -> None` (para os testes).
  - Um trabalhador daemon com `queue.Queue`, e um `threading.Lock` protege o dicionário de pedidos.

- [ ] **Step 1: Testes que falham**, com `executar` falso controlado por `threading.Event`:
  - `test_pedido_vai_de_na_fila_a_pronto`.
  - `test_um_pedido_ativo_por_corte`: segundo `pedir` do mesmo corte enquanto o primeiro está ativo → `PedidoAtivo`; depois de pronto, aceita.
  - `test_dois_cortes_em_sequencia`: com o primeiro bloqueado, o segundo corte fica `na fila`; liberado, os dois terminam `pronto`, na ordem.
  - `test_erro_e_excecao_viram_estado_erro`: `Resultado("erro","x",[])` → `erro`/`x`; exceção no `executar` → `erro` com a mensagem da exceção, e a fila continua atendendo.
  - `test_lista_limita_50`.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_fila.py -q`. Esperado: falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar o mesmo comando. Esperado: passam, sem threads penduradas (usar `parar` no fim de cada teste).
- [ ] **Step 5: Commit** `feat: fila de montagem do painel`.

### Task 6: Selo novo, rotas de música e ligação no app

**Files:**
- Create: `esteira/painel/rotas_musica.py`
- Modify:
  - `esteira/painel/leitura.py` (`selo`);
  - `esteira/revisao.py` (se precisar das datas no bloco);
  - `esteira/painel/app.py` (`criar_app(..., fila: Fila | None = None)`, inclui o roteador novo);
  - `esteira/cli.py` (`_painel` cria a fila real);
  - `docs/painel.md` (seção "Música").
- Test: `tests/test_painel_musica_api.py`, `tests/test_painel_leitura.py`, `tests/test_painel_cli.py`.

**Interfaces:**
- Consumes: Tasks 1–5; `ler_catalogo(MUSICAS)`; `resolver_episodio`, `resolver_arquivo`, `_pasta_do_corte`, `_TRAVA_GRAVACAO` (rotas atuais); `montar_episodio`.
- Produces:
  - `selo(...)`: com vídeo final cujo arquivo mais novo tem `st_mtime` menor que o do `corte.mp4`, devolve `"vídeo final desatualizado"` (abaixo de `erro`, acima de `com alerta`). Para isso, `BlocoRevisao` ganha `video_final_desatualizado: bool = False`, calculado em `dados_revisao`, sem mudar o `revisao.md`.
  - Rotas (prefixo `/api`, mesmas respostas de erro):
    - `GET /episodios/{ep}/musicas`;
    - `GET /musicas/{clima}/{arquivo}` (só `"{clima}/{arquivo}"` presente no catálogo, senão 404; `audio/mpeg`);
    - `GET /episodios/{ep}/cortes/{n}/musica` → `{atual, anterior, pedido}`;
    - `POST /episodios/{ep}/cortes/{n}/musica/previa` → `FileResponse` `audio/mp4`; falha vira 422 com `"Não consegui gerar a prévia: <motivo>"`;
    - `POST /episodios/{ep}/cortes/{n}/musica` → 202 `Pedido`; `PedidoAtivo` → 409 `{"detail": "Este corte já está sendo montado."}`; faixa fora do catálogo ou volume fora → 422;
    - `GET /tarefas`, `GET /tarefas/{id}`.
  - `criar_app` sem `fila` cria `Fila(executar=…)` com o `montar` real:
    ```python
    lambda pasta, n: montar_episodio(pasta, numeros={n}, forcar=True)[n]
    ```
    e o `trocar_musica` com `base=cortes` e `trava=_TRAVA_GRAVACAO`.
  - `_painel`: com a variável de ambiente `ESTEIRA_PAINEL_MONTAGEM_FALSA=1` (só para o teste de ponta a ponta), o `montar` vira uma função que regrava o `corte.mp4` com os mesmos bytes e devolve `"ok"`. O `docs/painel.md` diz que é só para testes.
  - Para o tipo `Faixa` na API, use `{arquivo, titulo, clima, duracao}`.

- [ ] **Step 1: Testes que falham:**
  - leitura: `test_selo_video_final_desatualizado` (`os.utime` no `corte.mp4` mais novo que o vídeo final) e prioridade abaixo de `erro`.
  - api: lista com `do_episodio` (com motivo) e `biblioteca` por clima;
  - api: `test_faixa_com_espaco_na_url` (`/api/musicas/leve/Sunshine%20A.mp3` → 200 `audio/mpeg`) e faixa fora do catálogo → 404;
  - api: `test_post_musica_202_e_409` (fila com `executar` bloqueado);
  - api: volume `-31` e `-17` → 422; faixa desconhecida → 422;
  - api: `GET .../musica` com `atual` lido do `montagem.json`;
  - api: `test_previa_422` (gerador falso levanta `ErroMidia`) e `test_previa_ok` (gerador falso grava um arquivo → 200 `audio/mp4`);
  - api: com `rede=True`, sem cookie → 401 nas rotas novas;
  - cli: `test_painel_montagem_falsa_por_ambiente`.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_musica_api.py tests/test_painel_leitura.py tests/test_painel_cli.py -q`. Esperado: falham.
- [ ] **Step 3:** Implementar. O gerador de prévia é injetável em `criar_app` (`gerar_previa=render.gerar_previa`).
- [ ] **Step 4:** Rodar os mesmos e a suíte completa uma vez (`.venv\Scripts\python.exe -m pytest -q`, cerca de 20 min). Esperado: tudo passa.
- [ ] **Step 5: Commit** `feat: rotas de música, fila e selo de vídeo final desatualizado`.

### Task 7: Frontend: bloco Música

**Files:**
- Create: `painel-web/src/componentes/BlocoMusica.tsx`, `painel-web/src/componentes/BlocoMusica.test.tsx`
- Modify:
  - `painel-web/src/api.ts` (tipos `ListaMusicas`, `MusicaDoCorte`, `Pedido`, `SeloValor` com `"vídeo final desatualizado"`);
  - `painel-web/src/componentes/Selo.tsx` (ícone `↻`, classe `selo-alerta`);
  - `painel-web/src/telas/Corte.tsx`;
  - `painel-web/src/componentes/EditorPost.tsx` (recarregar de fora);
  - `painel-web/src/telas/Episodio.tsx` (cartão `montando…`);
  - `painel-web/src/estilo.css`.

**Interfaces:**
- Consumes: as rotas da Task 6.
- Produces:
  - `<BlocoMusica ep n videoFinal: string[] tempoDoPlayer: () => number aoTerminar: () => void />`.
  - `EditorPost` ganha a prop `recarregarSinal: number`. Quando ela muda: sem rascunho não salvo, recarrega; com rascunho, mostra `O crédito da música mudou no post.md`.
  - `Players` expõe o tempo atual por `ref` (ou callback) para a prévia.

- [ ] **Step 1: Testes que falham** em `BlocoMusica.test.tsx`, com `fetch` falso:
  - mostra `Do episódio` com o motivo, antes de `Biblioteca`;
  - tocar uma faixa e depois outra pausa a primeira (só um `<audio>` tocando);
  - o `src` da faixa `Sunshine A.mp3` é `/api/musicas/leve/Sunshine%20A.mp3`;
  - o volume vai de -30 a -18 e mostra `-26 dB`;
  - `Ouvir prévia (15 s)` manda `inicio` igual a `tempoDoPlayer()` e mostra `a partir de 0:42` quando o tempo é 42;
  - com `videoFinal` não vazio, `Montar com esta música` chama `window.confirm` com o texto exato da spec; `confirm` falso não manda nada;
  - o andamento mostra `Na fila`, `Montando…`, `Pronto: o corte.mp4 foi atualizado.` (consulta a cada 2 s com timers falsos) e chama `aoTerminar` uma vez;
  - um erro mostra `Erro: <mensagem>` e `Tentar de novo`.
- [ ] **Step 2: Testes que falham** em `EditorPost.test.tsx`: `recarregarSinal` sem rascunho → novo GET; com rascunho → a mensagem aparece e o rascunho fica. Em `Selo.test.tsx`: o valor novo mostra o texto exato.
- [ ] **Step 3:** Rodar `npm test`. Esperado: os novos falham.
- [ ] **Step 4:** Implementar. Os controles de música ficam desabilitados com pedido ativo, e os avisos do pedido são listados abaixo do andamento.
- [ ] **Step 5:** Rodar `npm test` e `npm run build`. Esperado: passam.
- [ ] **Step 6: Commit** `feat: bloco Música na tela do corte`.

### Task 8: Fumaça e conferência real

**Files:**
- Modify: `painel-web/e2e/preparar.mjs`, `painel-web/e2e/fumaca.spec.ts` (ou `musica.spec.ts`), `painel-web/playwright.config.ts` (env `ESTEIRA_PAINEL_MONTAGEM_FALSA=1` no webServer).

- [ ] **Step 1:** Ajustar o episódio falso:
  - `montagem.json` do corte 1 com a música "Ice Flow" (o arquivo pode não existir, porque a montagem é falsa);
  - `musicas-do-episodio.json` com duas faixas do `musicas/catalogo.json` real.
- [ ] **Step 2: Teste**:
  - abrir o corte 1, escolher outra faixa de `Do episódio` e clicar em `Montar com esta música`;
  - esperar `Pronto: o corte.mp4 foi atualizado.`;
  - o editor mostra o crédito novo no TikTok.
- [ ] **Step 3:** `npm run build` e `npm run e2e`. Esperado: tudo passa.
- [ ] **Step 4: Conferência real (o controller, não o implementador):**
  - com o painel de teste (`--cortes .superpowers\painel-teste`), trocar a música de um corte da CÓPIA DE TESTE com a montagem real;
  - conferir o `corte.mp4` novo, o crédito no `post.md` da cópia e a prévia;
  - não tocar o `2 - Cortes/` real.
- [ ] **Step 5: Commit** `test: fumaça da troca de música`.
