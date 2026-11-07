# Painel de revisão: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Painel web local (notebook e celular na Wi-Fi) para revisar os cortes de um episódio e editar o `post.md`, lendo os mesmos arquivos da esteira.

**Architecture:** Backend FastAPI no pacote `esteira/painel/`, que reaproveita `revisao.dados_revisao` e `publicar.post`. Frontend React + TypeScript + Vite em `painel-web/`, compilado para `esteira/painel/estatico/` e servido pelo próprio FastAPI. Um processo, um comando: `python -m esteira painel`.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, pytest; Node 24, React 18, TypeScript, Vite, react-router-dom 6, react-markdown 9, Vitest, Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-07-painel-de-revisao-design.md`

Comandos rodam a partir de `Automacao/`. Python: `.venv\Scripts\python.exe`. Testes: `.venv\Scripts\python.exe -m pytest`.

## Global Constraints

- Responder, nomear e escrever mensagens em português do Brasil (código, testes, mensagens da API).
- Porta padrão `8765`. Sem `--rede`: host `127.0.0.1`, sem login. Com `--rede`: host `0.0.0.0`, login obrigatório.
- Keyring: serviço `tudo-e-politica-painel`, campos `codigo` (sal e hash) e `chave_sessao`. Nunca gravar código, chave ou hash em arquivo.
- Código de acesso: 8 caracteres de `ABCDEFGHJKMNPQRSTUVWXYZ23456789`, gerado com `secrets`.
- Cookie `painel_sessao`: `HttpOnly`, `SameSite=Strict`, validade de 30 dias, assinado com HMAC-SHA256 pela `chave_sessao`.
- Trava: 5 erros seguidos travam o login por 60 s (resposta 429).
- Única gravação: `post.md`, via `caminhos.garantir_escrita()`, atômica (`os.replace`). Nunca escrever em `1 - Programas/` nem em `video-final/`.
- Todo caminho vindo da URL precisa resolver para dentro de `CORTES` (resposta 403 se não resolver).
- Versão do post: SHA-256 hexadecimal dos bytes do arquivo.
- Selo, em ordem de prioridade: `erro`, `com alerta`, `sem vídeo final`, `pronto`.
- Limites: título do YouTube 100, Instagram e TikTok 2200 (vêm de `publicar/post.py`). Atraso para conferir o rascunho: 400 ms.
- Dependências Python novas só no extra `painel` (`fastapi>=0.115`, `uvicorn>=0.30`). FastAPI é importado só dentro do comando `painel`.
- Markdown exibido sem HTML embutido (react-markdown sem `rehype-raw`).
- `esteira/painel/estatico/` e `painel-web/node_modules/` no `.gitignore`.

## Review Focus

1. Nome de episódio com acento, espaços e parênteses (`Entre Assuntos 03 - Arthur Cerqueira (teste capcut)`) na URL precisa abrir a página, nos dois sentidos (codificar no front, decodificar na API). Teste na Task 4 (API) e na Task 8 (`api.test.ts`).
2. `post.md` com fim de linha CRLF (salvo pelo Bloco de Notas) precisa sobreviver à ida e volta sem virar LF. Teste na Task 2.
3. `video-final/` com `.MOV` maiúsculo ou com dois arquivos: listar os dois e servir com o tipo certo. Teste na Task 4.
4. Corte presente em `aprovados.json` mas ainda não montado: selo `erro`, e a página do corte abre sem resposta 500. Teste na Task 4.
5. Reiniciar o servidor não pode derrubar quem já entrou pelo celular (a chave fica no keyring). Teste na Task 6.

---

### Task 0: Pré-requisito: commit do trabalho de publicação

O painel importa `esteira/publicar/post.py`, que ainda não tem commit.

- [ ] **Step 1:** Rodar `git status --short` e mostrar a lista ao dono do canal. Pedir confirmação para commitar o trabalho de publicação como está. Sem um sim, parar.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest -q`. Esperado: tudo passa. Se algo falhar, parar e relatar.
- [ ] **Step 3:** Com o sim, commitar os arquivos listados (`git add` por caminho, nunca `-A`) com a mensagem `feat: publicação e agendamento nas redes`.

### Task 1: `dados_revisao` e nomes suspeitos

**Files:**
- Modify: `esteira/revisao.py`
- Modify: `docs/operacao.md` (etapa 10)
- Test: `tests/test_revisao.py`

**Interfaces:**
- Produces:
  - `@dataclass BlocoRevisao`: `numero: int`, `titulo: str`, `pasta: str` (nome da pasta do corte), `clima: str`, `instagram: bool`, `redes: list[str]` (`["youtube", "tiktok"]` ou `["youtube", "tiktok", "instagram"]`), `data: str`, `musica: str | None` (título ou nome do arquivo), `antes: str`, `depois: str`, `alertas: list[str]`, `video_final: list[str]`, `tem_guia: bool`, `erro: str | None`.
  - `dados_revisao(pasta: Path) -> list[BlocoRevisao]`.
  - `ler_nomes_suspeitos(pasta: Path) -> tuple[dict[int, list[str]], str | None]`: devolve os nomes por corte e um alerta geral (`"nomes-suspeitos.json ilegível"`) ou `None`.
  - `escrever_revisao(pasta: Path) -> Path`: mesma assinatura e mesmo Markdown de hoje.
  - `NOMES_SUSPEITOS = "nomes-suspeitos.json"`.

- [ ] **Step 1: Testes que falham** em `tests/test_revisao.py`, reaproveitando `_episodio` e `_montado`:
  - `test_dados_revisao_campos`: corte `a` do teste atual, com `Musica("m.mp3", titulo="Ice Flow")`. Afirma `bloco.redes == ["youtube", "tiktok", "instagram"]`, `bloco.musica == "Ice Flow"`, `bloco.antes == "p0 p1 p2 p3 p4 p5 p6 p7 p8 p9"`, `bloco.video_final == []`, `bloco.tem_guia is False`, `bloco.erro is None`.
  - `test_dados_revisao_nao_montado`: sem `_montado`. Afirma `bloco.erro == "corte não montado"`.
  - `test_dados_revisao_video_final_ordenado`: cria `video-final/b.MOV` e `video-final/A.mp4`. Afirma `bloco.video_final == ["A.mp4", "b.MOV"]`.
  - `test_nomes_suspeitos_entram_nos_alertas`: `nomes-suspeitos.json` = `{"1": ["Massa: conferir 'Felipe Massa'"]}` e registro com `alertas=["fora de quadro"]`. Afirma `bloco.alertas == ["fora de quadro", "Massa: conferir 'Felipe Massa'"]` e que o `revisao.md` contém `Alertas: fora de quadro; Massa: conferir 'Felipe Massa'`.
  - `test_nomes_suspeitos_ilegivel`: conteúdo `{quebrado`. Afirma `"nomes-suspeitos.json ilegível" in bloco.alertas` para todos os cortes.
  - `test_nomes_suspeitos_ausente`: `ler_nomes_suspeitos(pasta) == ({}, None)`.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_revisao.py -q`. Esperado: os testes novos falham (ImportError de `dados_revisao`) e os antigos passam.
- [ ] **Step 3:** Implementar. `dados_revisao` reproduz exatamente a lógica atual de `_bloco` (mesmas mensagens de erro, inclusive `"registro ilegível"`, `"montagem ilegível"` e o texto depois de `erro:`). Nos blocos com erro, os campos que não puderam ser lidos ficam vazios. `escrever_revisao` vira só formatação: bloco com `erro` gera `## N. Título` + `Erro: <erro>` + linha em branco; os outros geram as mesmas linhas de hoje, com `Redes` mapeada de volta para "YouTube e TikTok" / "YouTube, TikTok e Instagram" e `Música: nenhuma (sem música para o clima X)` quando `musica is None`.
- [ ] **Step 4:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_revisao.py -q`. Esperado: todos passam, inclusive os antigos sem mudança.
- [ ] **Step 5: Texto do `operacao.md`.** Mostrar ao dono do canal a troca abaixo na etapa 10 e esperar aprovação. Só então salvar.
  - Remover: "O comando `revisao` regrava o arquivo; por isso, rodá-lo antes de acrescentar à mão qualquer alerta." e "Antes de parar, acrescentar aos alertas de cada corte os nomes que podem ter saído errados na legenda, comparando com `Contexto/glossario.md`."
  - Inserir antes do comando: "Antes de rodar, gravar em `nomes-suspeitos.json`, na pasta do episódio, os nomes que podem ter saído errados na legenda, comparando com `Contexto/glossario.md`. Formato: `{\"4\": [\"Massa: conferir 'Felipe Massa'\"]}`, com o número do corte como chave. O `revisao` e o painel mostram esses nomes nos alertas. Não editar o `revisao.md` à mão."
- [ ] **Step 6: Commit**

```bash
git add esteira/revisao.py tests/test_revisao.py docs/operacao.md
git commit -m "refactor: dados_revisao como fonte única e nomes-suspeitos.json"
```

### Task 2: `gravar_textos` e versão do post

**Files:**
- Modify: `esteira/publicar/post.py`
- Test: `tests/test_publicar_post.py`

**Interfaces:**
- Consumes: `Textos`, `ler_post`, `_secoes` (já existentes).
- Produces:
  - `versao_post(caminho: Path) -> str`: SHA-256 hexadecimal dos bytes.
  - `gravar_textos(caminho: Path, textos: Textos) -> str`: grava e devolve a nova versão. Levanta `ErroPost` se o arquivo não tiver as seções obrigatórias.
  - `secoes_somente_leitura(caminho: Path) -> dict[str, str]`: as seções que não são YouTube, Instagram nem TikTok, na ordem em que aparecem.

- [ ] **Step 1: Testes que falham**, usando `tests/dados_post_corte1.md` copiado para `tmp_path`:
  - `test_gravar_sem_mudar_e_identico`: `gravar_textos(c, ler_post(c))` deixa `c.read_bytes()` igual ao original e devolve `versao_post(c)`.
  - `test_gravar_crlf_identico`: o mesmo arquivo convertido para `\r\n`. A ida e volta mantém os bytes, e uma troca do texto do Instagram mantém `\r\n` em todas as linhas.
  - `test_gravar_troca_so_os_campos`: troca os quatro campos. `ler_post` devolve os novos valores, e `secoes_somente_leitura` continua igual antes e depois (inclusive a seção `Música`). A linha `Título:` vira `Título: <novo>`.
  - `test_gravar_e_atomico`: depois de gravar, não sobra nenhum arquivo `*.tmp` na pasta.
  - `test_gravar_fora_de_cortes_recusa`: um caminho fora de `CORTES` e `AUTOMACAO` levanta `EscritaProibida`.
  - `test_versao_muda_com_conteudo`: versões diferentes para conteúdos diferentes, e 64 caracteres hexadecimais.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_publicar_post.py -q`. Esperado: os novos falham.
- [ ] **Step 3:** Implementar. Ler os bytes, detectar `\r\n` e trabalhar em linhas. Em cada parte trocada, substituir só a faixa que vai da primeira à última linha não vazia do corpo, mantendo as linhas em branco em volta. O título é só o resto da linha `Título:`. A descrição é o que vem depois da linha `Descrição:` até o fim da seção YouTube. Textos com várias linhas entram com o fim de linha do arquivo. Gravar em `<post>.tmp` na mesma pasta, depois de `garantir_escrita`, e `os.replace`.
- [ ] **Step 4:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_publicar_post.py -q`. Esperado: tudo passa.
- [ ] **Step 5: Commit**

```bash
git add esteira/publicar/post.py tests/test_publicar_post.py
git commit -m "feat: gravar_textos preserva o post.md byte a byte"
```

### Task 3: Leitura de episódios, segurança de caminho e selos

**Files:**
- Create: `esteira/painel/__init__.py` (vazio), `esteira/painel/leitura.py`
- Modify: `pyproject.toml` (extra `painel = ["fastapi>=0.115", "uvicorn>=0.30"]`; `httpx` no extra `dev`, exigido pelo `TestClient`)
- Test: `tests/test_painel_leitura.py`, `tests/auxiliares_painel.py`

**Interfaces:**
- Consumes: `dados_revisao`, `BlocoRevisao` (Task 1); `ler_post`, `conferir_textos`, `ErroPost` (publicar.post); `ler_aprovados`, `pasta_do_corte` (cortar).
- Produces, em `leitura.py` (sem importar FastAPI):
  - `class CaminhoProibido(Exception)` e `class NaoEncontrado(Exception)`.
  - `resolver_episodio(cortes: Path, nome: str) -> Path`: recusa nome vazio, com `/`, `\` ou `..`, ou que resolva fora de `cortes` (inclusive por link simbólico), com `CaminhoProibido`. Pasta inexistente levanta `NaoEncontrado`.
  - `resolver_arquivo(pasta: Path, nome: str, extensoes: set[str]) -> Path`: mesmas regras, mais extensão (comparada em minúsculas) dentro de `extensoes`.
  - `avisos_post(pasta_corte: Path, redes: list[str]) -> list[str]`: `conferir_textos` com o crédito de `montagem.json`. `ErroPost` vira `["post: <mensagem>"]`.
  - `selo(bloco: BlocoRevisao, avisos: list[str]) -> str`.
  - `resumo_episodio(pasta: Path, agora: datetime) -> dict`: `{"nome", "total", "prontos", "proxima_data", "aviso"}`. `prontos` conta os blocos com `video_final` não vazio. `proxima_data` é a menor `data` (`AAAA-MM-DD HH:MM`) a partir de `agora`, ou `None`. Sem `aprovados.json`: `total=0` e `aviso="sem cortes aprovados"`.
  - `listar_episodios(cortes: Path, agora: datetime) -> list[dict]`: pastas ordenadas por nome.
  - `bloco_json(bloco: BlocoRevisao, avisos: list[str]) -> dict`: os campos do bloco mais `"avisos_post"` e `"selo"`.
- `tests/auxiliares_painel.py`: `criar_episodio(cortes: Path, nome: str, cortes_aprovados: list[Corte], montados: set[int], post: bool = True) -> Path`, reaproveitando o padrão de `_episodio`/`_montado` de `test_revisao.py` e copiando `tests/dados_post_corte1.md` como `post.md`.

- [ ] **Step 1: Testes que falham** em `tests/test_painel_leitura.py`:
  - `test_resolver_episodio_com_acento_e_parenteses`: o nome `Entre Assuntos 03 - Arthur Cerqueira (teste capcut)` resolve.
  - `test_resolver_episodio_recusa` (parametrizado): `".."`, `"../Automacao"`, `"a/b"`, `"a\\b"`, `""`, um caminho absoluto. Todos levantam `CaminhoProibido`.
  - `test_resolver_episodio_link_para_fora`: pular com `pytest.skip` se `os.symlink` levantar `OSError`. Um link dentro de `cortes` apontando para `tmp_path/fora` levanta `CaminhoProibido`.
  - `test_resolver_arquivo_extensao`: `.MOV` aceito em `{".mp4", ".mov"}`; `.md` recusado.
  - `test_selo_prioridade`: erro supera alerta, alerta supera "sem vídeo final", e um bloco sem nada vira `pronto`.
  - `test_resumo_episodio`: 3 cortes, 1 com vídeo final, datas `2026-11-06 18:00` e `2026-11-09 12:00`, `agora=2026-11-07 10:00`. Afirma `prontos == 1` e `proxima_data == "2026-11-09 12:00"`.
  - `test_resumo_sem_aprovados`: `aviso == "sem cortes aprovados"`.
  - `test_avisos_post_sem_credito`: post sem o crédito que está em `montagem.json`. Afirma que `"youtube: falta o crédito da música"` está na lista.
  - `test_avisos_post_instagram_so_quando_marcado`: com `redes=["youtube", "tiktok"]`, nenhum aviso começa com `instagram:`.
- [ ] **Step 2:** Instalar o extra com `.venv\Scripts\python.exe -m pip install -e ".[painel,dev]"` e rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_leitura.py -q`. Esperado: falham por ImportError.
- [ ] **Step 3:** Implementar `leitura.py`.
- [ ] **Step 4:** Rodar os testes. Esperado: passam.
- [ ] **Step 5: Commit**

```bash
git add pyproject.toml esteira/painel/__init__.py esteira/painel/leitura.py tests/test_painel_leitura.py tests/auxiliares_painel.py
git commit -m "feat: leitura dos episódios e selos do painel"
```

### Task 4: API de leitura e arquivos

**Files:**
- Create: `esteira/painel/app.py`, `esteira/painel/rotas.py`
- Test: `tests/test_painel_api.py`

**Interfaces:**
- Consumes: tudo da Task 3.
- Produces:
  - `criar_app(cortes: Path, rede: bool = False, cofre: Cofre | None = None, relogio: Callable[[], float] = time.time, agora: Callable[[], datetime] = datetime.now, estatico: Path | None = None) -> FastAPI`. O `Cofre` é definido na Task 6; nesta task, `rede=False` e o parâmetro existe mas é ignorado.
  - Tratadores: `CaminhoProibido` vira 403 e `NaoEncontrado` vira 404, ambos com `{"detail": "<mensagem em português>"}`.
  - Rotas, com as respostas abaixo:
    - `GET /api/episodios` → `list[resumo]`.
    - `GET /api/episodios/{ep}` → `{"resumo": ..., "cortes": [bloco_json...]}`.
    - `GET /api/episodios/{ep}/calendario` → `{"itens": [{"numero", "titulo", "data", "redes"}], "texto": str}`, com `itens` ordenados por data (sem data, no fim) e `texto` vazio se não houver `calendario.md`.
    - `GET /api/episodios/{ep}/descartados` → `{"texto": str}`.
    - `GET /api/episodios/{ep}/cortes/{n}` → `{"bloco": ..., "guia": str | None, "imagens": [nomes .jpg/.jpeg/.png ordenados]}`. Corte fora de `aprovados.json` dá 404.
    - `GET .../cortes/{n}/video`, `.../video-final/{arquivo}` (`{".mp4", ".mov"}`) e `.../imagens/{arquivo}` (`{".jpg", ".jpeg", ".png"}`) → `FileResponse` com o tipo certo (`.mov` como `video/quicktime`).

- [ ] **Step 1: Testes que falham** com `TestClient(criar_app(tmp_path / "cortes", agora=lambda: datetime(2026, 11, 7, 10)))`:
  - `test_lista_episodios`.
  - `test_episodio_nome_com_acento_na_url`: `client.get("/api/episodios/" + quote("Entre Assuntos 03 - Arthur Cerqueira (teste capcut)"))` dá 200.
  - `test_episodio_caminho_malicioso`: `/api/episodios/..%2FAutomacao` dá 403 ou 404, nunca 200.
  - `test_corte_nao_montado_abre`: dá 200 e `bloco.selo == "erro"`.
  - `test_corte_inexistente_404`.
  - `test_video_com_range`: `corte.mp4` com 1000 bytes e header `Range: bytes=0-99`. Esperado: 206 e 100 bytes.
  - `test_video_final_mov_maiusculo`: dois arquivos listados. Pedir `b.MOV` dá 200 com `content-type` `video/quicktime`.
  - `test_imagem_extensao_proibida`: `.../imagens/guia.md` dá 403.
  - `test_calendario_ordenado`.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_api.py -q`. Esperado: falham.
- [ ] **Step 3:** Implementar `app.py` e `rotas.py`. As rotas ficam num `APIRouter` com prefixo `/api`. O `criar_app` guarda `cortes` e `agora` em `app.state`.
- [ ] **Step 4:** Rodar os testes. Esperado: passam. Se `test_video_com_range` falhar porque a versão do Starlette não suporta range, subir o piso para `fastapi>=0.115.6` / `starlette>=0.40` e rodar de novo.
- [ ] **Step 5: Commit**

```bash
git add esteira/painel/app.py esteira/painel/rotas.py tests/test_painel_api.py
git commit -m "feat: API de leitura do painel"
```

### Task 5: API do post

**Files:**
- Modify: `esteira/painel/rotas.py`
- Test: `tests/test_painel_post.py`

**Interfaces:**
- Consumes: `ler_post`, `gravar_textos`, `versao_post`, `secoes_somente_leitura`, `conferir_textos` (Task 2); `avisos_post` (Task 3).
- Produces (os campos JSON têm os mesmos nomes de `Textos`: `youtube_titulo`, `youtube_descricao`, `instagram`, `tiktok`):
  - `GET .../cortes/{n}/post` → `{"campos", "somente_leitura": {seção: texto}, "credito": str | None, "redes": list[str], "versao": str, "avisos": list[str], "erro": None}`. Com `ErroPost`, a resposta é 200 com `{"erro": "<mensagem>", "versao": null}` e os outros campos nulos.
  - `POST .../post/conferir` com `{"campos"}` → `{"avisos"}`, sem gravar.
  - `PUT .../post` com `{"versao", "campos"}` → 200 `{"versao", "avisos"}`. Se a versão não bater: 409 `{"detail": "O post.md mudou desde que você abriu.", "versao_atual": str}`. Sem post.md: 404. Corpo inválido: 422 (Pydantic).

- [ ] **Step 1: Testes que falham:**
  - `test_get_post`: os campos batem com `ler_post`, `"Música" in somente_leitura` e `len(versao) == 64`.
  - `test_conferir_nao_grava`: os bytes do arquivo continuam iguais.
  - `test_put_grava_e_devolve_versao_nova`.
  - `test_put_conflito_409`: alterar o arquivo por fora entre o GET e o PUT. Esperado: 409 com `versao_atual == versao_post(c)`, e o arquivo continua com o conteúdo de fora.
  - `test_put_com_avisos_grava_mesmo_assim`: título com 101 caracteres. Esperado: 200, e `"youtube: título com mais de 100 caracteres"` em `avisos`.
  - `test_post_quebrado_devolve_erro`: post sem `## TikTok`. Esperado: 200 e `erro == "post.md sem a seção ## TikTok"`.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_post.py -q`. Esperado: falham.
- [ ] **Step 3:** Implementar. O PUT calcula `versao_post` imediatamente antes de gravar e compara.
- [ ] **Step 4:** Rodar os testes. Esperado: passam.
- [ ] **Step 5: Commit**

```bash
git add esteira/painel/rotas.py tests/test_painel_post.py
git commit -m "feat: edição do post.md pelo painel com conflito 409"
```

### Task 6: Código de acesso e sessão

**Files:**
- Create: `esteira/painel/acesso.py`
- Modify: `esteira/painel/app.py`, `esteira/painel/rotas.py` (`POST /api/entrar`)
- Test: `tests/test_painel_acesso.py`

**Interfaces:**
- Produces:
  - `class Cofre(Protocol)`: `ler(campo: str) -> str | None` e `gravar(campo: str, valor: str) -> None`. `CofreKeyring()` usa `keyring` com o serviço `tudo-e-politica-painel`, importado dentro dos métodos, como em `publicar/credenciais.py`.
  - `gerar_codigo(cofre: Cofre) -> str`: gera o código e grava `codigo` como `"<sal hex>$<pbkdf2_hmac sha256, 200_000 iterações, hex>"`. Também grava uma `chave_sessao` nova (`secrets.token_hex(32)`). Devolve o código em claro.
  - `class Porteiro`: `__init__(cofre: Cofre, relogio: Callable[[], float])`. Métodos:
    - `entrar(codigo: str) -> str`: devolve o valor do cookie. Levanta `CodigoErrado` ou `Travado(segundos_restantes: int)`.
    - `sessao_valida(cookie: str | None) -> bool`.
  - Cookie: `"<expira_epoch>.<hmac hex de expira_epoch>"`.
  - Em `criar_app`, quando `rede=True`: middleware que, para `/api/*` exceto `/api/entrar`, responde 401 `{"detail": "Entre com o código de acesso."}` sem sessão válida. Sem `rede`, nenhum login.
  - `POST /api/entrar` com `{"codigo"}`: 204 com `Set-Cookie: painel_sessao=...; HttpOnly; SameSite=Strict; Max-Age=2592000; Path=/`. Código errado: 401. Travado: 429 com `{"detail": "Muitas tentativas. Tente de novo em N s."}`.
  - O código digitado vale em maiúsculas ou minúsculas.

- [ ] **Step 1: Testes que falham**, com `CofreFalso` (um dicionário) e `relogio` controlável:
  - `test_codigo_tem_formato`: 8 caracteres, todos do alfabeto definido.
  - `test_cofre_nao_guarda_codigo_em_claro`: o código não aparece em nenhum valor do cofre.
  - `test_sem_rede_nao_pede_login`.
  - `test_com_rede_sem_sessao_401`.
  - `test_entrar_e_usar_cookie`: depois de entrar, `GET /api/episodios` dá 200, e o `Set-Cookie` contém `HttpOnly`, `SameSite=Strict` e `Max-Age=2592000`.
  - `test_codigo_minusculo_aceito`.
  - `test_trava_depois_de_5_erros`: o 6º pedido, mesmo com o código certo, dá 429. Avançando o relógio 61 s, entra.
  - `test_sessao_expira_em_30_dias`: relógio +30 dias +1 s dá 401.
  - `test_reiniciar_servidor_mantem_sessao`: um cookie emitido por um app continua válido num segundo `criar_app` com o mesmo cofre.
  - `test_novo_codigo_derruba_sessoes`: depois de `gerar_codigo` de novo, o cookie antigo dá 401.
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_acesso.py -q`. Esperado: falham.
- [ ] **Step 3:** Implementar. Comparações com `hmac.compare_digest`. A trava fica em memória: o contador de erros seguidos zera ao acertar.
- [ ] **Step 4:** Rodar os testes. Esperado: passam.
- [ ] **Step 5: Commit**

```bash
git add esteira/painel/acesso.py esteira/painel/app.py esteira/painel/rotas.py tests/test_painel_acesso.py
git commit -m "feat: código de acesso e sessão do painel na rede local"
```

### Task 7: Comando `painel` e arquivos estáticos

**Files:**
- Modify: `esteira/cli.py`, `esteira/painel/app.py`, `.gitignore`
- Test: `tests/test_painel_cli.py`

**Interfaces:**
- Produces:
  - `python -m esteira painel [--rede] [--porta 8765] [--cortes <pasta>]`. O padrão de `--cortes` é `caminhos.CORTES`. A opção serve para o teste de fumaça e para a demo do portfólio.
  - `python -m esteira painel codigo`: chama `gerar_codigo(CofreKeyring())` e mostra `Código de acesso: XXXXXXXX (anote; ele não será mostrado de novo)`.
  - `_painel(args, servir=uvicorn.run) -> int`: o `servir` é injetável nos testes. FastAPI e uvicorn são importados dentro da função.
  - Em `criar_app`, com `estatico` existente: monta os arquivos e, para qualquer `GET` fora de `/api` que não seja arquivo, devolve `index.html` (rotas do React).
- Mensagens:
  - Sem `estatico/index.html`: `Painel sem build: rode "npm install" e "npm run build" em painel-web/` e saída 1.
  - `--rede` sem código no cofre: `Sem código de acesso: rode "python -m esteira painel codigo"` e saída 1.
  - Com `--rede`, antes de servir: `Painel na rede: http://<ip local>:<porta>`. O IP é o do socket UDP de saída (`connect(("8.8.8.8", 80))`, sem enviar nada), com `127.0.0.1` se falhar. Também: `Use só na Wi-Fi de casa. Não use em rede pública.`
  - Sem `--rede`: `Painel em http://127.0.0.1:<porta>`.

- [ ] **Step 1: Testes que falham:**
  - `test_sem_build_sai_com_erro`.
  - `test_rede_sem_codigo_sai_com_erro` (cofre falso via monkeypatch).
  - `test_local_serve_em_127`: o `servir` falso recebe `host="127.0.0.1"` e `port=8765`.
  - `test_rede_serve_em_0000_e_mostra_aviso`: `host="0.0.0.0"`, e a saída contém `Não use em rede pública`.
  - `test_rota_do_react_devolve_index`: com `estatico/index.html` falso, `GET /episodios/x` dá 200 e o HTML, e `GET /api/nao-existe` dá 404.
  - `test_cli_funciona_sem_fastapi`: `principal(["revisao", ...])` não importa `fastapi` (`"fastapi" not in sys.modules` depois, num subprocesso).
- [ ] **Step 2:** Rodar `.venv\Scripts\python.exe -m pytest tests/test_painel_cli.py -q`. Esperado: falham.
- [ ] **Step 3:** Implementar. Acrescentar ao `.gitignore`: `esteira/painel/estatico/`, `painel-web/node_modules/`, `painel-web/test-results/`, `painel-web/playwright-report/`.
- [ ] **Step 4:** Rodar `.venv\Scripts\python.exe -m pytest -q` (suíte inteira). Esperado: tudo passa.
- [ ] **Step 5: Commit**

```bash
git add esteira/cli.py esteira/painel/app.py .gitignore tests/test_painel_cli.py
git commit -m "feat: comando painel com --rede e código de acesso"
```

### Task 8: Frontend: base, telas de episódios e calendário

**Files:**
- Create: `painel-web/` com `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/api.ts`, `src/estilo.css`, `src/telas/Entrada.tsx`, `src/telas/Episodios.tsx`, `src/telas/Episodio.tsx`, `src/componentes/Selo.tsx`, `src/componentes/Markdown.tsx`, `src/componentes/Calendario.tsx`
- Test: `src/componentes/Selo.test.tsx`, `src/componentes/Calendario.test.tsx`, `src/api.test.ts`

**Interfaces:**
- Consumes: o JSON das Tasks 4 a 6.
- Produces:
  - `src/api.ts`: tipos `Resumo`, `Bloco`, `Calendario`, `CorteDetalhe`, `Post` com os nomes de campos da API. A função `pedir<T>(caminho: string, init?: RequestInit): Promise<T>` codifica os segmentos com `encodeURIComponent` (`caminhoEpisodio(ep: string)`), lança `ErroApi { status: number; detail: string }`, e no status 401 redireciona para `/entrar`.
  - Rotas: `/entrar`, `/` (Episódios), `/episodios/:ep` (abas Cortes, Calendário, Descartados), `/episodios/:ep/cortes/:n` (Task 9).
  - `<Selo valor={...}/>`: texto e cor por valor (`erro` vermelho, `com alerta` âmbar, `sem vídeo final` cinza, `pronto` verde). Ícone mais texto, nunca só cor.
  - `<Markdown texto/>`: react-markdown sem `rehype-raw`.
  - `<Calendario itens/>`: agrupa por dia (`AAAA-MM-DD`). Em cada dia, uma linha "TikTok e Shorts" com todos os cortes e uma linha "Instagram" só com os que têm `instagram` nas redes. Sem data vai para o grupo "Sem data", no fim.
  - Layout: uma coluna abaixo de 768 px. Os alvos de toque têm pelo menos 44 px.
- Dependências: `react@18`, `react-dom@18`, `react-router-dom@6`, `react-markdown@9`. Dev: `vite@5`, `@vitejs/plugin-react`, `typescript@5`, `vitest@2`, `@testing-library/react`, `@testing-library/user-event`, `jsdom`, `@playwright/test`. O `vite.config.ts` usa `build.outDir: "../esteira/painel/estatico"`, `emptyOutDir: true` e proxy de `/api` para `http://127.0.0.1:8765`.
- Scripts: `dev`, `build` (`tsc -b && vite build`), `test` (`vitest run`), `e2e` (`playwright test`).

- [ ] **Step 1:** Pedir confirmação ao dono do canal antes do `npm install` (baixa os pacotes do npm, cerca de 150 MB em `node_modules`). Com o sim, criar o projeto e instalar.
- [ ] **Step 2: Testes que falham:**
  - `Selo.test.tsx`: cada valor mostra o texto exato (`"erro"`, `"com alerta"`, `"sem vídeo final"`, `"pronto"`).
  - `Calendario.test.tsx`: os itens `{1, "2026-11-08 18:00", [youtube,tiktok,instagram]}`, `{2, "2026-11-08 12:00", [youtube,tiktok]}` e `{3, "", ...}` geram o dia `2026-11-08` com os cortes 2 e 1 em TikTok, nessa ordem, e só o 1 em Instagram. O 3 fica em "Sem data".
  - `api.test.ts`: `caminhoEpisodio("Entre Assuntos 03 - Arthur Cerqueira (teste capcut)")` é igual a `"/api/episodios/Entre%20Assuntos%2003%20-%20Arthur%20Cerqueira%20(teste%20capcut)"`. Um `fetch` falso com 401 leva a `location` para `/entrar`.
- [ ] **Step 3:** Rodar `npm test` em `painel-web/`. Esperado: falham.
- [ ] **Step 4:** Implementar as telas e os componentes.
- [ ] **Step 5:** Rodar `npm test` e `npm run build`. Esperado: tudo passa e `esteira/painel/estatico/index.html` existe.
- [ ] **Step 6: Commit** (`git add painel-web` sem `node_modules`, que está no `.gitignore`):

```bash
git add painel-web
git commit -m "feat: frontend do painel com episódios e calendário"
```

### Task 9: Frontend: tela do corte e editor do post

**Files:**
- Create: `src/telas/Corte.tsx`, `src/componentes/EditorPost.tsx`, `src/componentes/Players.tsx`
- Test: `src/componentes/EditorPost.test.tsx`, `src/componentes/Players.test.tsx`

**Interfaces:**
- Consumes: `pedir`, `Post`, `CorteDetalhe` (Task 8).
- Produces:
  - `<Players ep n videoFinal: string[]/>`: abas "Corte" e um botão por arquivo do vídeo final. `<video controls playsInline preload="metadata">`.
  - `<EditorPost ep n/>`: quatro campos com contador `x/limite` (vermelho acima do limite), as seções só de leitura, o crédito com o botão "Copiar crédito" e o botão "Salvar". Mensagens exatas:
    - salvo: `Salvo.`
    - conflito: `O post.md mudou desde que você abriu.`, com o botão `Carregar a versão nova` (o rascunho fica nos campos até clicar);
    - post quebrado: o `erro` da API, com os campos desabilitados.
  - Avisos: chamar `POST .../post/conferir` 400 ms depois da última digitação e mostrar a lista. O salvar não fica bloqueado pelos avisos.
  - Na tela do corte: players, informações (redes, data, música, antes e depois, alertas, erro), `<Markdown texto={guia}/>`, grade de miniaturas (`<img loading="lazy">` de `.../imagens/<nome>`) e o editor.

- [ ] **Step 1: Testes que falham** em `EditorPost.test.tsx`, com `fetch` falso e `vi.useFakeTimers()`:
  - `contador fica vermelho acima de 100`: título com 101 caracteres mostra `101/100` com a classe `acima`.
  - `confere uma vez 400 ms depois de parar de digitar`: digitar 3 caracteres e avançar 399 ms dá 0 chamadas a `/conferir`; avançar mais 1 ms dá 1 chamada.
  - `conflito mantém o rascunho`: o PUT responde 409. Esperado: a mensagem aparece e o campo continua com o texto digitado.
  - `post quebrado desabilita`: o GET responde com `erro`. Esperado: a mensagem aparece e os campos ficam `disabled`.
  - `salvar envia a versão lida`: o corpo do PUT tem a `versao` do GET.
  - `Players.test.tsx`: com `videoFinal=["A.mp4", "b.MOV"]`, aparecem três botões, e clicar em `b.MOV` troca o `src` para `.../video-final/b.MOV`.
- [ ] **Step 2:** Rodar `npm test`. Esperado: falham.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar `npm test` e `npm run build`. Esperado: passam.
- [ ] **Step 5: Commit**

```bash
git add painel-web
git commit -m "feat: tela do corte e editor do post.md"
```

### Task 10: Teste de fumaça, docs e verificação real

**Files:**
- Create: `painel-web/playwright.config.ts`, `painel-web/e2e/preparar.ts` (globalSetup), `painel-web/e2e/fumaca.spec.ts`, `docs/painel.md`
- Modify: `docs/operacao.md` (uma seção curta "Painel de revisão" que aponta para `docs/painel.md`)

**Interfaces:**
- Consumes: o comando da Task 7 (`--cortes`, `--porta`).
- `preparar.ts` cria em `painel-web/test-results/cortes/` um episódio chamado `Entre Assuntos 99 - Convidado (teste)` com 2 cortes. Grava `aprovados.json`, `transcricao/palavras.json` e, para cada corte, `corte.mp4` vazio (o `.mp4` está no `.gitignore`), `trabalho/registro.json`, `trabalho/montagem.json` com um crédito e `post.md` (cópia de `tests/dados_post_corte1.md`). O corte 2 fica sem `corte.mp4`.
- `webServer`: `..\.venv\Scripts\python.exe -m esteira painel --cortes test-results/cortes --porta 8766`, com `url` `http://127.0.0.1:8766`.

- [ ] **Step 1: Teste** `fumaca.spec.ts`: abre `/`, clica no episódio, vê o corte 1 e o selo `erro` no corte 2, abre o corte 1, troca o texto do TikTok, clica em "Salvar" e vê `Salvo.`. Recarrega a página e vê o texto novo.
- [ ] **Step 2:** Pedir confirmação antes de `npx playwright install chromium` (baixa o Chromium, cerca de 150 MB). Com o sim, rodar `npm run build` e `npm run e2e`. Esperado: 1 passed.
- [ ] **Step 3:** Escrever `docs/painel.md`:
  - como gerar o build;
  - como abrir no notebook e no celular;
  - `painel codigo`;
  - o aviso sobre Wi-Fi pública e firewall;
  - o que o painel grava (só o `post.md`).
- [ ] **Step 4: Verificação real:** rodar `python -m esteira painel` e abrir `http://127.0.0.1:8765` no navegador do app. Conferir o episódio `Entre Assuntos 03 - Arthur Cerqueira`:
  - os 10 cortes aparecem com selo;
  - o player toca e o vídeo final aparece;
  - o calendário bate com o `aprovados.json`.

  Não salvar nenhum post real nessa conferência. Depois, `.venv\Scripts\python.exe -m pytest -q` e `npm test`. Esperado: tudo passa.
- [ ] **Step 5: Commit**

```bash
git add painel-web/playwright.config.ts painel-web/e2e docs/painel.md docs/operacao.md
git commit -m "test: fumaça do painel e documentação de uso"
```
