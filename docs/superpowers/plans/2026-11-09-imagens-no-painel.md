# Imagens no painel (Fase A): plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revisar no painel os momentos de imagem propostos pelo Claude, baixar as fotos escolhidas e gerar as imagens de IA aprovadas por API (OpenAI ou Google), com confirmação de quantidade e custo.

**Architecture:** O pacote novo `esteira/imagens_ia/` traz os provedores, as chaves, a configuração e a geração. O fluxo de imagens existente ganha o registro `ia.json` e o `guia.md` com IA. A fila do painel passa a aceitar tarefas genéricas (fotos e IA) além da música. As rotas novas ficam em `esteira/painel/rotas_imagens.py`, e o front ganha o bloco "Imagens", a aba do episódio e a tela de configurações.

**Tech Stack:** Python 3.12, FastAPI, Pillow, pytest; React 18 + TypeScript, Vitest, Playwright. Nenhum pacote novo.

**Spec:** `docs/superpowers/specs/2026-11-09-imagens-no-painel-design.md` (e as do painel e da música).

Comandos a partir de `Automacao/`. Python: `.venv\Scripts\python.exe`. Frontend: em `painel-web/`, `npm test`, `npm run build`, `npm run e2e`. A suíte Python completa leva cerca de 10 a 20 min: rodar só onde o plano manda.

## Global Constraints

- Português do Brasil em código, nomes, mensagens e testes.
- Nunca gerar imagem de IA de prompt que cite pessoa do glossário (`pedidos.pessoas_do_glossario` + `pedidos._pessoa_citada`). O painel avisa e o servidor recusa.
- Keyring: serviço `tudo-e-politica-imagens`, campos `openai:chave` e `google:chave`. A chave nunca vai para arquivo, log, resposta da API nem navegador.
- Configuração em `Automacao/imagens-ia.json`, sem segredos. Os modelos, qualidades e preços iniciais vêm das páginas oficiais, conferidas na implementação.
- Arquivos de IA: `imagens-sugeridas/<MMSS-slug>-ia-<K>.jpg`, K de 1 a 3, preparados em 1080x1920 por `imagens.preparar_foto`. Registro em `trabalho/ia.json`. Nunca em `sugeridas.json`.
- O `imagens sugerir` nunca apaga imagem de IA.
- Nada é gerado nem baixado sem confirmação: na CLI, `--confirmar`; no painel, confirmação com o resumo.
- O painel nunca repete sozinho uma geração que falhou.
- Toda gravação passa por `caminhos.garantir_escrita` (com `base_extra` = pasta de `--cortes`). `1 - Programas/` só é lido.
- Mensagens exatas da spec entram verbatim.
- Testes nunca chamam as APIs reais, o Wikimedia real, o keyring real nem tocam o `2 - Cortes/` real.

## Review Focus

1. Prompt com nome de pessoa em outra caixa ou sem acento ("lula", "felipe massa"): recusado. Teste na Task 4 e na Task 6.
2. Provedor devolve imagem horizontal ou quadrada: vira 1080x1920 com faixa central e fundo desfocado, sem corte. Teste na Task 4.
3. `imagens sugerir` rodado pela CLI depois de gerar IA: as imagens de IA e as linhas do `guia.md` continuam. Teste na Task 1.
4. Sem chave cadastrada: nada é cobrado; o pedido termina com `Rode python -m esteira imagens conectar <provedor>` em cada momento. Teste na Task 4 e na Task 7.
5. O Claude regrava o `pedidos.json` enquanto o dono edita no painel: 409, sem perder a edição de nenhum dos dois. Teste na Task 6.

---

### Task 1: Regras do canal, `aprovado`, `ia.json` e `guia.md` com IA

**Files:**
- Modify: `esteira/pedidos.py`, `esteira/fluxo_imagens.py`, `../Contexto/estilo-de-imagens.md`, `docs/operacao.md` (etapa 8)
- Test: `tests/test_pedidos.py`, `tests/test_fluxo_imagens.py`

**Interfaces:**
- Produces:
  - `Momento.aprovado: bool = False`, lido e gravado pelo `pedidos.json`, com default para arquivos antigos.
  - `fluxo_imagens.chave_momento(m: Momento) -> str`: o mesmo valor de `_base(m)`, tornado público.
  - Em `esteira/fluxo_imagens.py`:
    - `IA = "ia.json"`;
    - `ler_ia(trabalho: Path) -> list[dict]` (ausente ou ilegível → `[]`);
    - `registrar_ia(trabalho: Path, item: dict, base: Path | None = None) -> None`.
  - `escrever_guia` inclui, nos momentos `ia`, a linha `Imagem de IA: <arquivo1>, <arquivo2> (<provedor>, <AAAA-MM-DD>)` quando houver itens no `ia.json` com aquela chave e o arquivo existir. O prompt continua listado, com o rótulo `Prompt (9:16):` (sem "ChatGPT").

- [ ] **Step 1: Testes que falham:**
  - `test_momento_aprovado_default_e_ida_e_volta`.
  - `test_guia_lista_versoes_de_ia`: `ia.json` com duas versões e os arquivos presentes. O guia contém `Imagem de IA: 0052-turistas-ia-1.jpg, 0052-turistas-ia-2.jpg (openai, 2026-11-09)`.
  - `test_sugerir_nao_apaga_ia`: um arquivo `0052-turistas-ia-1.jpg` presente e listado no `ia.json`. Depois de `sugerir_episodio` (com consulta e baixar falsos), o arquivo continua e o guia mantém a linha de IA.
  - `test_ler_ia_ilegivel`: `[]`.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_pedidos.py tests/test_fluxo_imagens.py -q`. Esperado: os novos falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar os mesmos testes. Esperado: passam.
- [ ] **Step 5: Regras do canal** (texto já aprovado pelo dono antes da execução):
  - em `Contexto/estilo-de-imagens.md`, trocar "Imagens de IA: a esteira só escreve o prompt no `guia.md`. O dono do canal gera no ChatGPT, em 9:16." por "Imagens de IA: a esteira gera pelo painel, por API, depois que o dono aprova o prompt e o custo. O `guia.md` marca as imagens de IA.";
  - na etapa 8 do `docs/operacao.md`, trocar "IA: só o prompt, que vai no `guia.md`. A esteira não recebe nem prepara imagem de IA." por "IA: o Claude escreve o prompt. O dono aprova no painel e gera por lá, ou o Claude roda `imagens gerar` (sem `--confirmar` mostra o resumo e o custo; com `--confirmar` gera) depois do sim do dono ao resumo. A esteira recusa prompt com nome de pessoa do glossário."
- [ ] **Step 6: Commit** `feat: imagens de IA registradas em ia.json e no guia`.

### Task 2: Base dos provedores: interface, chaves, configuração e `imagens conectar`

**Files:**
- Create: `esteira/imagens_ia/__init__.py`, `esteira/imagens_ia/provedor.py`, `esteira/imagens_ia/chaves.py`, `esteira/imagens_ia/config.py`, `imagens-ia.json`
- Modify: `esteira/cli.py` (`imagens conectar`)
- Test: `tests/test_imagens_ia_base.py`

**Interfaces:**
- Produces:
  - `provedor.py`:
    - `class Provedor(Protocol)`: `nome: str`, `gerar(prompt: str, proporcao: str = "9:16") -> bytes`;
    - erros `ErroImagem(Exception)`, `SemChave(ErroImagem)`, `ChaveRecusada(ErroImagem)`, `ErroTemporario(ErroImagem)`, `ConteudoRecusado(ErroImagem)`;
    - mensagens exatas: `Rode python -m esteira imagens conectar <provedor>`, `Chave recusada pelo <provedor>: conecte de novo.`, e para os temporários `<provedor> indisponível agora: <motivo>. Tente de novo.`.
  - `chaves.py`:
    - `SERVICO = "tudo-e-politica-imagens"`;
    - `ler_chave(provedor: str) -> str | None`;
    - `gravar_chave(provedor: str, chave: str) -> None`;
    - `tem_chave(provedor: str) -> bool`;
    - `keyring` importado dentro das funções.
  - `config.py`:
    - `PROVEDORES = ("openai", "google")`, `ARQUIVO = AUTOMACAO / "imagens-ia.json"`;
    - `@dataclass Config(provedor: str, provedores: dict[str, dict])`, cada provedor com `modelo`, `qualidade`, `preco_usd`;
    - `ler_config(caminho: Path = ARQUIVO) -> Config` (ausente → padrão; ilegível → `ErroImagem("imagens-ia.json ilegível")`);
    - `gravar_config(config: Config, caminho: Path = ARQUIVO) -> None` (valida o provedor em `PROVEDORES` e `preco_usd >= 0`; passa por `garantir_escrita`);
    - `provedor_atual(config: Config, fabricas: dict[str, Callable[[dict], Provedor]] | None = None) -> Provedor`.
  - `imagens-ia.json` inicial com os dois provedores e valores tirados das páginas oficiais (confirmar na implementação e citar a fonte e a data no relatório).
  - CLI: `python -m esteira imagens conectar openai|google`:
    - pede a chave com `getpass` (`Chave da API (<provedor>):`);
    - recusa chave vazia;
    - grava no keyring;
    - mostra `Chave da <provedor> guardada no Windows.`

- [ ] **Step 1: Testes que falham:**
  - config: ausente → padrão; ida e volta; provedor inválido → `ErroImagem`; preço negativo → `ErroImagem`.
  - chaves: com um keyring falso, conferir que `gravar_chave` + `ler_chave` funcionam e que `tem_chave` reflete o estado.
  - cli: `conectar` com `getpass` falso grava no keyring falso; a chave não aparece na saída.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_imagens_ia_base.py tests/test_cli.py -q`. Esperado: os novos falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar os mesmos testes. Esperado: passam.
- [ ] **Step 5: Commit** `feat: base dos provedores de imagem e imagens conectar`.

### Task 3: Adaptadores OpenAI e Google

**Files:**
- Create: `esteira/imagens_ia/openai.py`, `esteira/imagens_ia/google.py`
- Test: `tests/test_imagens_ia_provedores.py`

**Interfaces:**
- Consumes: `Provedor` e os erros (Task 2); `ler_chave` (Task 2); `esteira/publicar/http.py` (`pedir`, `ErroRede`).
- Produces:
  - `class OpenAI` e `class Google`, que implementam `Provedor`. O construtor é `(config: dict, pedir=http.pedir, ler_chave=chaves.ler_chave)`.
  - `gerar` devolve os bytes da imagem decodificados do base64 da resposta.
  - Mapeamento de respostas:
    - sem chave → `SemChave`;
    - 401/403 → `ChaveRecusada`;
    - 429/5xx/`ErroRede` → `ErroTemporario`;
    - recusa de conteúdo do provedor → `ConteudoRecusado` com o motivo do provedor.
  - A proporção pedida é a vertical mais próxima de 9:16 aceita pelo modelo.

- [ ] **Step 1:** Conferir na documentação oficial atual de cada provedor o endpoint, os campos do pedido (modelo, prompt, tamanho ou proporção, qualidade), o formato da resposta e o formato de erro de conteúdo recusado. Registrar as URLs e a data no relatório.
- [ ] **Step 2: Testes que falham**, com `pedir` falso que guarda o pedido e devolve respostas montadas a partir da documentação. Para cada provedor:
  - sucesso: a URL e o corpo enviados conferem com a documentação, a chave vai só no cabeçalho, e os bytes voltam;
  - sem chave;
  - 401;
  - 429;
  - 503;
  - conteúdo recusado.
- [ ] **Step 3:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_imagens_ia_provedores.py -q`. Esperado: falham.
- [ ] **Step 4:** Implementar.
- [ ] **Step 5:** Rodar o mesmo comando. Esperado: passam.
- [ ] **Step 6: Commit** `feat: adaptadores de imagem da OpenAI e do Google`.

### Task 4: Gerar um momento, `imagens gerar` e lembrete no agendar

**Files:**
- Create: `esteira/imagens_ia/gerar.py`
- Modify: `esteira/cli.py` (`imagens gerar`), `esteira/publicar/agendar.py` (`resumo`), `docs/operacao.md` (só a menção ao comando já aprovada na Task 1, se faltar)
- Test: `tests/test_imagens_ia_gerar.py`, `tests/test_cli.py`, `tests/test_publicar_agendar.py`

**Interfaces:**
- Consumes: Task 1 (`chave_momento`, `registrar_ia`, `ler_ia`, `escrever_guia`, `Momento.aprovado`); Task 2 (`Provedor`, erros, `ler_config`, `provedor_atual`); `pedidos.ler_pedidos`, `pessoas_do_glossario`, `_pessoa_citada`; `imagens.preparar_foto`; `caminhos.CONTEXTO`.
- Produces:
  - `class ErroPrompt(ErroImagem)`.
  - `pendentes(pasta_corte: Path) -> list[Momento]`: momentos `ia` aprovados, não descartados, com prompt e sem versão no `ia.json`.
  - `orcamento(pastas_corte: list[Path], config: Config) -> dict`: `{"imagens": int, "provedor": str, "modelo": str, "custo_usd": float}`.
  - `gerar_momento(pasta_corte: Path, chave: str, provedor: Provedor, config: Config, pessoas: list[str], base: Path | None = None, agora: Callable[[], datetime] = datetime.now) -> str`. Segue os passos 1 a 6 da spec. As mensagens de `ErroPrompt` são exatas:
    - `Cita pessoa real (<nome>): não pode gerar`;
    - `Prompt não aprovado`;
    - `Este momento já tem 3 versões`;
    - `Momento não é de IA`.
  - `gerar_cortes(pastas_corte: list[Path], provedor, config, pessoas, base=None, progresso: Callable[[str], None] = lambda _: None) -> tuple[list[str], list[str]]` (arquivos gerados, avisos `<corte> <chave>: <mensagem>`). Gera um por vez, chama `progresso(f"Gerando {i} de {total}…")` e segue depois de um erro.
  - CLI `python -m esteira imagens gerar "<pasta>" [--numero N] [--confirmar]`:
    - sem `--confirmar`, imprime `N imagens, provedor <p>, modelo <m>, custo estimado ~US$ X.XX` e sai 0 sem gerar;
    - com `--confirmar`, gera e imprime os arquivos e os avisos.
  - `agendar.resumo` acrescenta, quando o `ia.json` do corte não está vazio: `Este corte tem N imagens de IA geradas: confira se o vídeo final usa alguma e inclua o aviso.`

- [ ] **Step 1: Testes que falham**, com provedor falso que devolve um PNG em memória:
  - gera `0052-turistas-ia-1.jpg` em 1080x1920, registra no `ia.json` (provedor, modelo, prompt, data) e o guia lista a versão;
  - segunda geração vira `-ia-2`; com 3 versões, `ErroPrompt("Este momento já tem 3 versões")`;
  - `test_pessoa_sem_acento_e_minuscula`: glossário com "Felipe Massa" e prompt "foto do felipe massa na pista" → `ErroPrompt("Cita pessoa real (Felipe Massa): não pode gerar")`, provedor não chamado;
  - não aprovado → `ErroPrompt("Prompt não aprovado")`;
  - `test_imagem_horizontal_fica_na_faixa_central`: PNG 1536x1024 vira 1080x1920; o topo é desfocado e o centro tem a imagem;
  - `test_sem_chave_nao_cobra`: provedor falso levanta `SemChave` → `gerar_cortes` devolve o aviso com `Rode python -m esteira imagens conectar openai` em cada momento, sem arquivo e sem `ia.json`;
  - `gerar_cortes` segue depois de um `ConteudoRecusado` e chama `progresso` com `Gerando 1 de 2…` e `Gerando 2 de 2…`;
  - cli: sem `--confirmar` não chama o provedor e imprime o orçamento; com `--confirmar` gera;
  - agendar: o resumo contém a linha do lembrete quando há `ia.json` e não contém quando não há.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_imagens_ia_gerar.py tests/test_cli.py tests/test_publicar_agendar.py -q`. Esperado: os novos falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar os mesmos testes. Esperado: passam.
- [ ] **Step 5: Commit** `feat: gerar imagens de IA por momento e imagens gerar`.

### Task 5: Fila com tarefas genéricas

**Files:**
- Modify: `esteira/painel/fila.py`, `esteira/painel/rotas_musica.py` (se o uso de `ativo` mudar)
- Test: `tests/test_painel_fila.py`, `tests/test_painel_musica_api.py`

**Interfaces:**
- Consumes: a `Fila` atual (`pedir(pasta_episodio, numero, faixa, volume_db)` para música; `Resultado` de `troca_musica`).
- Produces:
  - `Pedido` ganha `tipo: str = "musica"`, `cortes: list[int]` e `progresso: str = ""`. O `numero` continua: é o corte de um pedido de um corte só, ou `0` num pedido de episódio.
  - `Fila.pedir_tarefa(tipo: str, pasta_episodio: Path, cortes: list[int], executar: Callable[[Callable[[str], None]], Resultado]) -> Pedido`:
    - levanta `PedidoAtivo` se algum corte da lista já tem um pedido ativo do mesmo `tipo`;
    - `executar` recebe a função `progresso(texto)`, que atualiza `Pedido.progresso` sob a trava.
  - `Fila.ativo(episodio: str, numero: int, tipo: str = "musica") -> Pedido | None`.
  - O `pedir` da música continua igual, com `tipo="musica"` e `cortes=[numero]`.

- [ ] **Step 1: Testes que falham:**
  - um pedido `ia` de episódio com cortes `[1, 2]` bloqueia `pedir_tarefa("ia", …, [2], …)` (`PedidoAtivo`), mas não bloqueia `pedir_tarefa("fotos", …, [2], …)` nem uma troca de música do corte 2;
  - o progresso aparece no `pedido(id)` enquanto roda;
  - os testes atuais da fila e da API de música continuam passando sem mudança.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_fila.py tests/test_painel_musica_api.py -q`. Esperado: os novos falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar os mesmos testes. Esperado: passam.
- [ ] **Step 5: Commit** `feat: fila do painel com tarefas de imagens`.

### Task 6: API dos momentos

**Files:**
- Create: `esteira/painel/rotas_imagens.py`
- Modify: `esteira/painel/app.py` (inclui o roteador), `esteira/pedidos.py` (se precisar gravar por `garantir_escrita`)
- Test: `tests/test_painel_imagens_api.py`

**Interfaces:**
- Consumes: Task 1; `pedidos.ler_pedidos`/`gravar_pedidos`/`validar_escolhas`; `wikimedia.buscar_candidatas` (injetável no app como `buscar_candidatas`); `versao_dos_bytes` de `publicar.post`; `_pasta_do_corte` das rotas atuais.
- Produces:
  - `GET /api/episodios/{ep}/cortes/{n}/momentos` → `{versao, momentos: [{chave, inicio, fim, fala, tipo, nome, busca, prompt, aprovado, descartar, motivo, candidatas: [{titulo, miniatura, autor, licenca, pagina, largura, altura}], escolhas, fotos_prontas: [arquivo], ia: [{arquivo, provedor, data}], pessoa_citada: str | null}]}`.
    - `miniatura` é limitada a 640 px: trocar o `/<N>px-` da URL de miniatura do Wikimedia por `/640px-` quando N > 640.
  - `PUT .../momentos/{chave}` com `{versao, tipo?, escolhas?, prompt?, aprovado?, descartar?}`:
    - 200 com o momento atualizado e a `versao` nova;
    - 409 `{"detail": "O pedidos.json mudou desde que você abriu.", "versao_atual"}`;
    - 422 com mensagens em português para escolha fora da faixa, mais de 3 escolhas, escolha repetida, tipo inválido, e para `aprovado: true` com pessoa citada (`Cita pessoa real (<nome>): não pode gerar`);
    - mudar o `prompt` desmarca `aprovado`, a menos que o mesmo PUT traga `aprovado: true` e o prompt seja válido.
  - `POST .../momentos/{chave}/buscar` com `{busca}`: troca as `candidatas` e zera as `escolhas` e as fotos ainda não baixadas, gravando sob a versão atual. Busca vazia → 422; erro de rede do Wikimedia → 422 `Não consegui buscar no Wikimedia: <motivo>`.
  - Gravações do `pedidos.json` atômicas, por `garantir_escrita`, sob a mesma trava `_TRAVA_GRAVACAO`.

- [ ] **Step 1: Testes que falham**, num episódio falso com `pedidos.json` de um momento foto (3 candidatas) e um momento IA:
  - GET com a miniatura reduzida para 640 px e `pessoa_citada` preenchida;
  - PUT de escolhas `[2, 1]` com 200; `[4]` → 422; `[1, 1]` → 422;
  - PUT de prompt desmarca `aprovado`;
  - `test_conflito_quando_o_claude_regrava`: alterar o arquivo por fora entre o GET e o PUT → 409 com `versao_atual`, e o arquivo continua com a alteração de fora;
  - aprovar prompt com "lula" (glossário com "Lula") → 422 com a mensagem exata;
  - buscar com `buscar_candidatas` falso troca as candidatas e zera as escolhas;
  - com `rede=True`, sem cookie → 401.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_imagens_api.py -q`. Esperado: falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar o mesmo comando. Esperado: passam.
- [ ] **Step 5: Commit** `feat: API dos momentos de imagem no painel`.

### Task 7: API de fotos, IA, orçamento e configurações

**Files:**
- Modify: `esteira/painel/rotas_imagens.py`, `esteira/painel/app.py`, `esteira/cli.py` (variável só de teste), `docs/painel.md` (seção "Imagens")
- Test: `tests/test_painel_imagens_api.py`, `tests/test_painel_cli.py`

**Interfaces:**
- Consumes: Tasks 2, 4, 5 e 6; `fluxo_imagens.resumir_episodio`/`sugerir_episodio` (com `numeros`); `wikimedia.tamanho`.
- Produces:
  - `GET .../cortes/{n}/fotos/resumo` e `GET /api/episodios/{ep}/fotos/resumo` → `{fotos, megabytes, origem: "Wikimedia Commons"}`.
  - `POST .../cortes/{n}/fotos` e `POST /api/episodios/{ep}/fotos` → 202 `Pedido` (`tipo="fotos"`, roda o `sugerir_episodio` dos cortes; `progresso` `Baixando i de N…`). `PedidoAtivo` → 409 `{"detail": "Já há um pedido de fotos em andamento para este corte."}`.
  - `GET .../cortes/{n}/ia/orcamento` e `GET /api/episodios/{ep}/ia/orcamento` → o `orcamento` da Task 4.
  - `POST .../cortes/{n}/ia`, `POST /api/episodios/{ep}/ia` e `POST .../cortes/{n}/momentos/{chave}/ia` → 202 `Pedido` (`tipo="ia"`). O último faz "gerar de novo" daquele momento, mesmo que ele já tenha versão. 409 `{"detail": "Já há um pedido de imagens em andamento para este corte."}`.
  - `GET /api/configuracoes/imagens` → `{provedor, provedores: {…}, chaves: {openai: bool, google: bool}}`, sem a chave. `PUT` com `{provedor, provedores}` → 200 ou 422.
  - `criar_app` ganha os parâmetros `provedores: dict[str, Callable[[dict], Provedor]] | None` e `buscar_candidatas`/`sugerir`/`resumir` injetáveis.
  - `ESTEIRA_PAINEL_IMAGEM_FALSA=1` (só para testes, lida em `_painel`): os provedores viram um falso que devolve um PNG 1024x1536 cinza, e `tem_chave` responde verdadeiro. Documentado no `docs/painel.md`, junto das outras variáveis de teste.
  - `docs/painel.md` ganha a seção "Imagens": como revisar, baixar e gerar; `imagens conectar`; custo estimado; o aviso de IA continua na publicação.

- [ ] **Step 1: Testes que falham:**
  - resumo com `medir` falso;
  - POST fotos e ia: 202 e 409;
  - orçamento com 2 aprovados e preço 0,05 → `custo_usd == 0.10`;
  - `test_sem_chave_termina_com_aviso`: provedor falso `SemChave` → o pedido termina `pronto` com o aviso por momento, e nenhum arquivo;
  - "gerar de novo" cria a versão 2;
  - configurações: GET não contém a chave (com o keyring falso guardando "sk-segredo", o texto da resposta não contém "sk-segredo"); PUT válido e inválido;
  - cli: a variável de ambiente troca os provedores.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_imagens_api.py tests/test_painel_cli.py -q`. Esperado: os novos falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar os mesmos testes, e depois a suíte completa uma vez (`.venv\Scripts\python.exe -m pytest -q`). Esperado: tudo passa.
- [ ] **Step 5: Commit** `feat: API de fotos, imagens de IA e configurações`.

### Task 8: Frontend: bloco "Imagens" na tela do corte

**Files:**
- Create: `painel-web/src/componentes/BlocoImagens.tsx`, `painel-web/src/componentes/CartaoMomento.tsx`, os testes de cada um
- Modify: `painel-web/src/api.ts`, `painel-web/src/telas/Corte.tsx` (o bloco substitui a exibição do `guia.md`), `painel-web/src/estilo.css`

**Interfaces:**
- Consumes: rotas das Tasks 6 e 7; `Pedido` com `tipo`, `cortes` e `progresso`.
- Produces: `<BlocoImagens ep n irPara={(segundos) => …} />`, que usa o player do corte para o botão ▶.
- Textos exatos da spec:
  - `Trocar para IA`, `Trocar para foto`, `Descartar`;
  - `Buscar outras`, `Pronta`;
  - `Cita pessoa real (<nome>): não pode gerar`, `Aprovado`, `Gerar de novo`;
  - `Baixar as fotos escolhidas (N fotos, X MB)`, `Gerar as aprovadas (N imagens, ~US$ X)`;
  - a confirmação de fotos inclui `As fotos baixadas antes neste corte serão substituídas.`;
  - andamento: `Na fila`, o `progresso` do pedido, `Pronto`, `Erro: …`.

- [ ] **Step 1: Testes que falham** (Vitest, com `fetch` falso):
  - clicar nas candidatas na ordem 3, 1 numera "1" na 3 e "2" na 1 e manda `escolhas: [3, 1]`; clicar de novo na 3 manda `[1]`;
  - uma quarta escolha fica desabilitada;
  - editar o prompt desmarca `Aprovado` na tela; com `pessoa_citada`, a caixa `Aprovado` fica desabilitada e o aviso aparece;
  - um 409 no PUT recarrega o momento e mostra `O pedidos.json mudou desde que você abriu.`;
  - `Gerar as aprovadas` chama `window.confirm` com o texto do orçamento; com `confirm` falso, nada é enviado;
  - o andamento mostra o `progresso` e, ao terminar, recarrega os momentos;
  - o ▶ chama `irPara(inicio)`.
- [ ] **Step 2:** Rodar `npm test`. Esperado: os novos falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar `npm test` e `npm run build`. Esperado: passam.
- [ ] **Step 5: Commit** `feat: bloco Imagens na tela do corte`.

### Task 9: Frontend: aba "Imagens" do episódio e tela "Configurações"

**Files:**
- Create: `painel-web/src/telas/Configuracoes.tsx`, `painel-web/src/componentes/ImagensDoEpisodio.tsx`, os testes de cada um
- Modify: `painel-web/src/App.tsx` (rota `/configuracoes` e link no topo), `painel-web/src/telas/Episodio.tsx` (aba nova), `painel-web/src/api.ts`, `painel-web/src/estilo.css`

**Interfaces:**
- Consumes: rotas da Task 7; `GET .../cortes/{n}/momentos` de cada corte, para o resumo por corte.
- Produces:
  - aba "Imagens" com o resumo por corte (momentos, fotos baixadas, prompts aprovados, imagens geradas) e os botões do episódio, com as mesmas confirmações da Task 8;
  - a tela "Configurações":
    - provedor;
    - para cada provedor: modelo, qualidade e preço (número ≥ 0);
    - o estado da chave: `Conectado` ou `Rode python -m esteira imagens conectar <provedor>`;
    - o botão `Salvar`.

- [ ] **Step 1: Testes que falham:**
  - a aba mostra os números por corte e o botão do episódio confirma com o orçamento do episódio;
  - as configurações mostram `Conectado`/`Rode …` conforme `chaves`, salvam com PUT e mostram o 422;
  - nenhum campo da tela pede a chave.
- [ ] **Step 2:** Rodar `npm test`. Esperado: falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar `npm test` e `npm run build`. Esperado: passam.
- [ ] **Step 5: Commit** `feat: aba Imagens do episódio e tela de configurações`.

### Task 10: Fumaça e conferência real

**Files:**
- Modify: `painel-web/e2e/preparar.mjs`, `painel-web/playwright.config.ts` (env `ESTEIRA_PAINEL_IMAGEM_FALSA=1`)
- Create: `painel-web/e2e/imagens.spec.ts`

- [ ] **Step 1:** No episódio falso, o corte 2 ganha um `pedidos.json` com um momento de IA (prompt sem pessoa) e um de foto com 2 candidatas falsas. O teste de ponta a ponta não busca nada no Wikimedia nem baixa fotos.
- [ ] **Step 2: Teste:**
  - abrir o corte 2 e marcar `Aprovado`;
  - clicar em `Gerar as aprovadas` e aceitar a confirmação;
  - esperar `Pronto`;
  - ver a miniatura da versão 1 no cartão.
  - O teste não deve depender da ordem dos outros specs: usar um corte diferente dos testes de música e de post.
- [ ] **Step 3:** `npm run build` e `npm run e2e`. Esperado: tudo passa.
- [ ] **Step 4: Conferência real (o controller, não o implementador):**
  - na CÓPIA DE TESTE, revisar os momentos de um corte;
  - buscar outras candidatas;
  - baixar fotos, com o sim do dono para o download;
  - gerar UMA imagem de IA de verdade, só se o dono tiver cadastrado a chave e aprovado o custo;
  - nunca no `2 - Cortes/` real.
- [ ] **Step 5: Commit** `test: fumaça das imagens no painel`.
