# Publicação agendada: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objetivo:** criar o comando `esteira publicar`. Ele agenda um corte aprovado no YouTube, no Instagram e no TikTok, a partir do vídeo de `video-final/` e do `post.md`, com o sim do dono do canal.

**Arquitetura:** pacote `esteira/publicar/`.
- A lógica pura fica em `post.py`, `fila.py`, `agendar.py` e `rodar.py`, e recebe as redes como objetos com `publicar(...)`. Assim os testes usam redes falsas.
- Cada rede tem um módulo HTTP próprio, em `urllib`, como o `rede.py`.
- Os segredos ficam no Gerenciador de Credenciais do Windows, via `keyring`.
- O Agendador de Tarefas do Windows roda `publicar rodar`.

**Tecnologias:** Python 3.12, pytest, `urllib`, `keyring`, `schtasks`, ffprobe (`bin/`, via `esteira.midia.sondar`).

**Spec:** `docs/superpowers/specs/2026-11-06-publicacao-design.md`

## Restrições globais

- Código, mensagens e docs em português do Brasil, com nomes em português, como no código atual.
- Nunca gravar id, segredo ou token de app em arquivo, log, mensagem ou saída de teste. Só via `keyring`, serviço `"tudo-e-politica"`, chave `"<rede>:<campo>"`.
- Toda escrita passa por `garantir_escrita`. A esteira só **lê** `video-final/` e nunca grava, apaga ou altera nada nela.
- A esteira nunca apaga nem edita nada nas redes.
- `agendar` sem `--confirmar` não envia nada e não grava a fila.
- Horário: sempre Brasília, com fuso fixo `-03:00` (`timezone(timedelta(hours=-3))`). O Brasil não tem horário de verão desde 2019, e o Windows não tem a base IANA sem o pacote `tzdata`.
- Estados da fila: `agendado`, `enviando`, `publicado`, `rascunho`, `privado`, `erro`, `conferir`, `cancelado`.
- Até 3 tentativas por item. Item em `enviando` no início do `rodar` vira `conferir`, nunca reenviado sozinho.
- Modos, em `Automacao/publicacao.json`: `{"youtube": "privado"|"agendado", "tiktok": "rascunho"|"direto"}`. Padrão: `privado` e `rascunho`. O Instagram não tem modo.
- Limites das redes: título do YouTube com até 100 caracteres, descrição com até 5000 e sem `<` nem `>`. Legenda do Instagram e do TikTok com até 2200 caracteres e até 30 hashtags no Instagram. YouTube Shorts com até 180 s.
- Instalar `keyring` é download: antes, pedir confirmação ao dono do canal, com nome, origem (PyPI) e tamanho.
- A pasta `Automacao/` não é repositório git: os passos "Commit" viram "rodar os testes da tarefa"; não há commit.
- A suíte completa leva mais de 10 min: rodar em segundo plano. Em cada tarefa, rodar só os testes dela.

## Foco da revisão

1. **PC desligado no meio do upload:** o item fica em `enviando`, e o `rodar` seguinte o marca `conferir` e não reenvia. Teste na Tarefa 7.
2. **Dois `rodar` ao mesmo tempo** (o gatilho de login e o de 15 min juntos): a segunda execução sai sem fazer nada. Uma trava com mais de 2 h é considerada abandonada e removida. Teste na Tarefa 2.
3. **`post.md` editado à mão com seção faltando, título vazio ou crédito da música removido:** o `agendar` recusa e diz qual rede e o quê. Teste na Tarefa 1.
4. **Data no passado ou num formato errado** (`08/11 18h`): o `agendar` recusa, com o formato esperado `AAAA-MM-DD HH:MM`. Teste na Tarefa 6.
5. **Token vencido e sem renovação:** o item vira `erro` com "reconecte com `publicar conectar <rede>`", sem gastar as 3 tentativas. Teste na Tarefa 7.

---

### Tarefa 1: ler e conferir o `post.md`

**Arquivos:**
- Criar: `esteira/publicar/__init__.py` (vazio), `esteira/publicar/post.py`
- Teste: `tests/test_publicar_post.py`

**Interfaces:**
- Produz:
  - `@dataclass Textos(youtube_titulo: str, youtube_descricao: str, instagram: str, tiktok: str)`
  - `class ErroPost(Exception)`
  - `ler_post(caminho: Path) -> Textos`, que levanta `ErroPost` se falta o arquivo ou uma seção
  - `conferir_textos(textos: Textos, credito: str | None, redes: set[str]) -> list[str]`, que devolve a lista de problemas (vazia = ok)

Regras da leitura:
- As seções são cabeçalhos `## YouTube`, `## Instagram` e `## TikTok`.
- No YouTube, `Título:` é o resto da linha. `Descrição:` é tudo depois dessa linha, até a próxima seção `## `.
- Instagram e TikTok: o corpo inteiro da seção.
- Tudo com `strip()`. Outras seções são ignoradas.

- [ ] **Passo 1: escrever os testes que falham**

Usar como base o `post.md` real do corte 1 (copiar o texto para o teste).

```python
def test_le_secoes_do_post(tmp_path):
    textos = ler_post(_post(tmp_path, POST_CORTE_1))
    assert textos.youtube_titulo == "A Fórmula 1 faz sportswashing? 🏎️🌍 #Shorts"
    assert textos.youtube_descricao.startswith("A Fórmula 1 é usada por países")
    assert textos.youtube_descricao.endswith("#Sportswashing #Geopolítica #Shorts")
    assert "## Música" not in textos.tiktok

def test_secao_faltando(tmp_path):
    with pytest.raises(ErroPost, match="seção ## TikTok"):
        ler_post(_post(tmp_path, POST_CORTE_1.split("## TikTok")[0]))

def test_sem_post(tmp_path):
    with pytest.raises(ErroPost, match="post.md não encontrado"):
        ler_post(tmp_path / "post.md")

CREDITO = "Música: Ice Flow — Kevin MacLeod (incompetech.com), licença CC BY 4.0"

def test_textos_bons_sem_problemas(tmp_path):
    assert conferir_textos(ler_post(_post(tmp_path, POST_CORTE_1)), CREDITO, {"youtube", "instagram", "tiktok"}) == []

def test_problemas_dos_textos():
    t = Textos("", "a < b " + CREDITO, "x" * 2201 + CREDITO, "sem crédito")
    assert conferir_textos(t, CREDITO, {"youtube", "instagram", "tiktok"}) == [
        "youtube: título vazio",
        "youtube: descrição com < ou >",
        "instagram: texto com mais de 2200 caracteres",
        "tiktok: falta o crédito da música",
    ]

def test_confere_so_as_redes_pedidas():
    t = Textos("Título", "sem crédito", "sem crédito", "sem crédito")
    assert conferir_textos(t, CREDITO, {"tiktok"}) == ["tiktok: falta o crédito da música"]

def test_corte_sem_musica_nao_exige_credito():
    assert conferir_textos(Textos("T", "d", "i", "t"), None, {"youtube"}) == []

def test_instagram_com_mais_de_30_hashtags():
    t = Textos("T", "d", " ".join(f"#h{i}" for i in range(31)), "t")
    assert conferir_textos(t, None, {"instagram"}) == ["instagram: mais de 30 hashtags"]
```

Ordem dos problemas: por rede (youtube, instagram, tiktok) e, dentro da rede, título, tamanho, `<>`, hashtags e crédito. O crédito é conferido sem o ponto final (`credito.rstrip(".")`). Título do YouTube com mais de 100 caracteres: `"youtube: título com mais de 100 caracteres"`. Descrição com mais de 5000: `"youtube: descrição com mais de 5000 caracteres"`.

- [ ] **Passo 2:** `.venv\Scripts\python.exe -m pytest tests/test_publicar_post.py -q`. Esperado: falha de importação.
- [ ] **Passo 3:** implementar `ler_post` e `conferir_textos` em `esteira/publicar/post.py`.
- [ ] **Passo 4:** rodar de novo. Esperado: todos passam.

---

### Tarefa 2: fila `postagens.json` e trava

**Arquivos:**
- Criar: `esteira/publicar/fila.py`
- Teste: `tests/test_publicar_fila.py`

**Interfaces:**
- Produz:
  - `@dataclass Item(numero: int, rede: str, data: str, estado: str = "agendado", tentativas: int = 0, link: str = "", id_rede: str = "", erro: str = "")`. `data` em ISO com fuso, por exemplo `"2026-11-08T18:00:00-03:00"`.
  - `ARQUIVO = "postagens.json"`
  - `ler_fila(pasta_episodio: Path) -> list[Item]`, que devolve `[]` se o arquivo não existe
  - `gravar_fila(pasta_episodio: Path, itens: list[Item]) -> None`: grava com `garantir_escrita`, em `.tmp` e depois `replace`, com JSON `{"itens": [...]}`, `indent=2` e `ensure_ascii=False`
  - `achar(itens, numero, rede) -> Item | None`, que ignora itens `cancelado`
  - `class Ocupado(Exception)`
  - `trava(caminho: Path, idade_maxima: float = 7200)`: gerenciador de contexto que cria o arquivo com `os.open(..., O_CREAT | O_EXCL)`, levanta `Ocupado` se ele existe e é mais novo que `idade_maxima`, e o apaga ao sair

- [ ] **Passo 1: testes**

```python
def test_grava_e_le_fila(tmp_path): ...  # ida e volta de 2 itens, iguais
def test_fila_inexistente_vazia(tmp_path): assert ler_fila(tmp_path) == []
def test_achar_ignora_cancelado(): ...    # cancelado + agendado do mesmo corte/rede -> devolve o agendado
def test_trava_impede_segunda(tmp_path):
    with trava(tmp_path / "t.trava"):
        with pytest.raises(Ocupado):
            with trava(tmp_path / "t.trava"): pass
    assert not (tmp_path / "t.trava").exists()
def test_trava_velha_e_removida(tmp_path):
    p = tmp_path / "t.trava"; p.write_text("x")
    os.utime(p, (time.time() - 7300,) * 2)
    with trava(p): pass
```

- [ ] **Passo 2:** rodar `tests/test_publicar_fila.py`. Esperado: falha.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar. Esperado: todos passam.

---

### Tarefa 3: credenciais e OAuth local

**Arquivos:**
- Modificar: `pyproject.toml` (acrescentar `"keyring"` em `dependencies`)
- Criar: `esteira/publicar/credenciais.py`
- Teste: `tests/test_publicar_credenciais.py`

**Interfaces:**
- Produz:
  - `SERVICO = "tudo-e-politica"`
  - `ler(rede: str, campo: str) -> str | None` e `gravar(rede: str, campo: str, valor: str) -> None`, sobre `keyring.get_password` e `set_password`
  - `class ErroConexao(Exception)`: a mensagem sempre termina com `reconecte com publicar conectar <rede>`
  - `pedir_segredo(rotulo: str) -> str`: usa `getpass.getpass` e levanta `ErroConexao` se a resposta vem vazia
  - `esperar_codigo(porta: int, estado: str, abrir_url: str, abrir=webbrowser.open, tempo: float = 300) -> str`. Sobe um `http.server` em `127.0.0.1:porta`, abre `abrir_url` e espera **um** pedido `GET /retorno?code=...&state=...`. Responde com uma página "Pode fechar esta aba." e devolve `code`. Se `state` difere, se vem `error=` ou se o tempo acaba, levanta `ErroConexao`.
  - `PORTA = 8765`, `REDIRECIONAMENTO = "http://localhost:8765/retorno"`

- [ ] **Passo 0:** pedir ao dono do canal a confirmação do download do `keyring` (PyPI, cerca de 40 KB mais as dependências `jaraco.*` e `pywin32-ctypes`, menos de 1 MB). Com o sim, rodar `.venv\Scripts\python.exe -m pip install keyring`.
- [ ] **Passo 1: testes.** Usar um `keyring` falso com `monkeypatch` (um dicionário). Nunca o real.

```python
def test_grava_e_le(monkeypatch): ...   # gravar("youtube","token","abc"); ler(...) == "abc"; ler("x","y") is None
def test_esperar_codigo_devolve_code():
    # abrir= função que, numa thread, faz urllib GET em http://127.0.0.1:<porta livre>/retorno?code=C1&state=E1
    assert esperar_codigo(porta, "E1", "https://x", abrir=falso) == "C1"
def test_esperar_codigo_state_errado(): ...  # state=OUTRO -> ErroConexao
def test_esperar_codigo_tempo_esgotado(): ... # tempo=0.5, ninguém chama -> ErroConexao
```

- [ ] **Passo 2:** rodar `tests/test_publicar_credenciais.py`. Esperado: falha.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar. Esperado: todos passam.

---

### Tarefa 4: base HTTP e YouTube

**Arquivos:**
- Criar: `esteira/publicar/http.py`, `esteira/publicar/youtube.py`
- Teste: `tests/test_publicar_youtube.py`

**Interfaces:**
- Produz, em `http.py`:
  - `class ErroRede(Exception)`, com `temporario: bool`. É `True` para 429, 5xx e falha de conexão.
  - `pedir(metodo: str, url: str, corpo: bytes | None = None, cabecalhos: dict | None = None) -> tuple[int, dict, bytes]`, com `User-Agent` igual ao de `rede.USER_AGENT`. A abertura passa por `_urlopen`, como em `rede.py`, para os testes trocarem.
  - `json_de(corpo: bytes) -> dict`
- Produz, contrato comum a todas as redes:
  - `@dataclass Resultado(estado: str, link: str = "", id_rede: str = "")`
  - Cada rede expõe uma classe com `publicar(self, video: Path, textos: Textos, data: datetime, modo: str) -> Resultado`, que levanta `ErroRede` ou `ErroConexao`.
- Produz, em `youtube.py`:
  - `class YouTube` (consome `credenciais.ler/gravar("youtube", ...)`)
  - `conectar() -> None`

Renovação do token:
- Sempre antes de enviar: `POST https://oauth2.googleapis.com/token`, com `grant_type=refresh_token`, `client_id`, `client_secret` e `refresh_token`, em form-urlencoded.
- Sem refresh token, ou com resposta 400/401: `ErroConexao("youtube: ...")`.

Envio retomável:
1. `POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status`, com `Authorization: Bearer`, `X-Upload-Content-Type: video/mp4`, `X-Upload-Content-Length` e o corpo JSON:
   - `snippet`: `title`, `description` e `categoryId: "22"`;
   - `status`: `privacyStatus: "private"` e `selfDeclaredMadeForKids: false`.
   - No modo `agendado`, acrescentar `publishAt` = data em UTC, formato `...Z`.
2. `PUT` no `Location` com os bytes do vídeo.
3. Resposta 200/201 com `id`.

Resultado: `estado` = `"publicado"` no modo `agendado` (fica agendado no YouTube) ou `"privado"` no modo `privado`. `link` = `https://youtube.com/shorts/<id>`.

Conectar:
- `pedir_segredo` para `client_id` e `client_secret`, que são gravados.
- URL `https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=REDIRECIONAMENTO&response_type=code&scope=https://www.googleapis.com/auth/youtube.upload&access_type=offline&prompt=consent&state=<secrets.token_urlsafe(16)>`.
- Trocar o código em `https://oauth2.googleapis.com/token` (`grant_type=authorization_code`) e gravar `refresh_token`.

- [ ] **Passo 1: testes**, com `_urlopen` falso que registra os pedidos e devolve respostas prontas.

```python
def test_envio_privado(...):
    r = YouTube().publicar(video, TEXTOS, DATA, "privado")
    assert r == Resultado("privado", "https://youtube.com/shorts/abc123", "abc123")
    meta = json.loads(pedidos[1].data)
    assert meta["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    assert meta["snippet"]["title"] == TEXTOS.youtube_titulo
def test_envio_agendado_tem_publish_at(...):  # DATA 2026-11-08 18:00 -03:00 -> "2026-11-08T21:00:00Z"; estado "publicado"
def test_sem_refresh_token_pede_reconexao(...): # ErroConexao, mensagem termina com "reconecte com publicar conectar youtube"
def test_503_e_temporario(...):                # ErroRede com temporario True
def test_token_nunca_aparece_no_erro(...):      # resposta 400 com corpo contendo o token -> str(erro) não contém o token
```

- [ ] **Passo 2:** rodar `tests/test_publicar_youtube.py`. Esperado: falha.
- [ ] **Passo 3:** implementar `http.py` e `youtube.py`. Mensagens de erro: código HTTP mais `error.message` do JSON, cortada em 200 caracteres e sem os cabeçalhos.
- [ ] **Passo 4:** rodar. Esperado: todos passam.

---

### Tarefa 5: Instagram e TikTok

**Arquivos:**
- Criar: `esteira/publicar/instagram.py`, `esteira/publicar/tiktok.py`
- Teste: `tests/test_publicar_instagram.py`, `tests/test_publicar_tiktok.py`

**Interfaces:**
- Consome: `http.pedir`, `ErroRede`, `Resultado`, `credenciais`
- Produz: `class Instagram`, `class TikTok` (contrato da Tarefa 4), `conectar()` em cada módulo, `VERSAO_GRAPH = "v21.0"`

**Instagram** (API com login do Instagram, `graph.instagram.com`):

Conectar:
- Por `pedir_segredo`, colar o token gerado no painel do app da Meta ("Gerar token" do testador do Instagram).
- Validar com `GET /me?fields=user_id,username` e gravar `token` e `user_id`. Imprimir o `username`.
- Motivo: a Meta só aceita endereço de retorno `https`, e não há um no PC.

Renovação:
- Se passaram mais de 24 h desde a última (`credenciais` campo `renovado_em`), chamar `GET /refresh_access_token?grant_type=ig_refresh_token&access_token=...` e gravar o token novo.
- Erro 190: `ErroConexao`.

Publicar:
1. `POST /{VERSAO_GRAPH}/{user_id}/media` com `media_type=REELS`, `upload_type=resumable` e `caption=textos.instagram`. Devolve `id` e `uri`.
2. `POST` no `uri` (rupload) com `Authorization: OAuth <token>`, `offset: 0`, `file_size` e os bytes.
3. Consultar `GET /{id}?fields=status_code` a cada 10 s, por até 10 min, até `FINISHED`. Com `ERROR`, ou se o tempo acaba: `ErroRede(temporario=False)`.
4. `POST /{user_id}/media_publish` com `creation_id`, e depois `GET /{media_id}?fields=permalink`.

Resultado: `Resultado("publicado", permalink, media_id)`. O tempo de espera é injetável (`esperar=time.sleep`) para os testes.

**TikTok** (`open.tiktokapis.com/v2`):

Conectar:
- `pedir_segredo` para `client_key` e `client_secret`.
- Autorização em `https://www.tiktok.com/v2/auth/authorize/` com `client_key`, `scope=user.info.basic,video.upload,video.publish`, `response_type=code`, `redirect_uri=REDIRECIONAMENTO` e `state`.
- Troca em `POST /v2/oauth/token/` (`grant_type=authorization_code`). Gravar `refresh_token` e `open_id`.

Renovação: sempre, com `grant_type=refresh_token`. Erro: `ErroConexao`.

Envio em partes:
- `tamanho_parte = 10 * 1024 * 1024`, `total = max(1, tamanho // tamanho_parte)`. A última parte leva o resto.
- Com vídeo de até 64 MB, uma parte só, do tamanho do vídeo.
- Cada `PUT` no `upload_url` leva `Content-Range: bytes a-b/total_bytes` e `Content-Type: video/mp4`.

Modo `rascunho`:
- `POST /v2/post/publish/inbox/video/init/` com `source_info: {source: "FILE_UPLOAD", video_size, chunk_size, total_chunk_count}`, e depois as partes.
- Resultado: `Resultado("rascunho", "", publish_id)`.
- O rascunho **não leva o texto**: a fila guarda o aviso "cole o texto do post.md no app".

Modo `direto`:
- `POST /v2/post/creator_info/query/` primeiro. Se `PUBLIC_TO_EVERYONE` não está em `privacy_level_options`: `ErroRede(temporario=False, "tiktok: conta não permite público")`.
- Depois `POST /v2/post/publish/video/init/` com `post_info: {title: textos.tiktok, privacy_level: "PUBLIC_TO_EVERYONE", disable_comment: false, disable_duet: false, disable_stitch: false}` e o mesmo `source_info`, e então as partes.
- Consultar `POST /v2/post/publish/status/fetch/` até `PUBLISH_COMPLETE` (10 s, até 10 min).
- Resultado: `Resultado("publicado", "https://www.tiktok.com/@tudoepoliticabr", publish_id)`.

- [ ] **Passo 1: testes**, com `_urlopen` e `esperar` falsos.

```python
# instagram
def test_reels_publicado(...):  # sequência media -> rupload -> status IN_PROGRESS, FINISHED -> media_publish -> permalink
    assert r == Resultado("publicado", "https://www.instagram.com/reel/X/", "M1")
    assert "Ice Flow" in parse_qs(pedidos[0].data)["caption"][0]
def test_status_error_nao_e_temporario(...)
def test_erro_190_pede_reconexao(...)
# tiktok
def test_partes_de_85_mb(...):    # 85_593_673 bytes -> 8 partes; última com 85_593_673 - 7*10_485_760 bytes; Content-Range da última termina em "/85593673"
def test_video_pequeno_uma_parte(...)
def test_rascunho_usa_inbox(...):  # URL termina em /inbox/video/init/; estado "rascunho"
def test_direto_sem_publico_falha(...)
```

- [ ] **Passo 2:** rodar os dois arquivos de teste. Esperado: falha.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar. Esperado: todos passam.

---

### Tarefa 6: `agendar` (resumo e confirmação)

**Arquivos:**
- Criar: `esteira/publicar/agendar.py`, `esteira/publicar/config.py`
- Teste: `tests/test_publicar_agendar.py`

**Interfaces:**
- Consome: `ler_post`, `conferir_textos`, `fila.*`, `Resultado`, `midia.sondar(video) -> Midia` (com `largura`, `altura` e `duracao`), `cortar.ler_aprovados`, `cortar.pasta_do_corte`, `receita.ler_receita`
- Produz:
  - `config.ler_modos(caminho: Path = AUTOMACAO / "publicacao.json") -> dict[str, str]`, com o padrão `{"youtube": "privado", "tiktok": "rascunho"}` se o arquivo não existe. Modo desconhecido levanta `ValueError`.
  - `FUSO = timezone(timedelta(hours=-3))`, `REDES = ("youtube", "instagram", "tiktok")`
  - `ler_data(texto: str, agora: datetime) -> datetime`, que levanta `ErroAgendar("data inválida: use AAAA-MM-DD HH:MM")` ou `ErroAgendar("data no passado")`
  - `@dataclass Pedido(pasta: Path, numero: int, video: Path, textos: Textos, data: datetime, redes: list[str])`
  - `class ErroAgendar(Exception)`
  - `preparar_pedido(pasta_episodio: Path, numero: int, data: str, redes: list[str], agora: datetime) -> Pedido`, que levanta `ErroAgendar` com **todos** os problemas, um por linha
  - `resumo(pedido: Pedido, modos: dict) -> str`
  - `confirmar(pedido: Pedido, modos: dict, redes_api: dict[str, object]) -> list[Item]`

O que `preparar_pedido` confere:
- O corte existe no `aprovados.json`.
- Há exatamente um `.mp4` em `video-final/`, o vídeo é 1080x1920 e, se o YouTube está nas redes, tem até 180 s.
- `conferir_textos` passa, com o crédito do `montagem.json` (`None` se o corte não tem música).
- A data é válida.
- O corte não tem item ativo (diferente de `cancelado` e de `erro`) naquela rede.

`resumo` traz, nesta ordem:
- a linha do corte (`Corte 1: A Fórmula 1 faz sportswashing?`);
- o vídeo, com o nome, a duração em `m:ss` e `1080x1920`;
- a data, como `sábado, 08/11/2026 às 18:00 (Brasília)`;
- para cada rede, o modo e o texto exato. Exemplos de modo: `YouTube (privado: você muda para agendado no Studio)` e `TikTok (rascunho: o texto não vai junto; cole no app)`.

`confirmar`:
- Grava um `Item("agendado")` por rede.
- Para o YouTube, envia logo: marca `enviando`, grava, chama `publicar` e grava o resultado. Falha temporária volta a `agendado`, com tentativa +1, para o `rodar` tentar de novo. `ErroConexao` vai para `erro`.
- Devolve os itens.

- [ ] **Passo 1: testes** (pasta de episódio montada com `tests.auxiliares.preparar_episodio_teste` e um `video-final/Corte 1.mp4` falso, com `sondar` trocado por `monkeypatch`)

```python
AGORA = datetime(2026, 11, 6, 12, 0, tzinfo=FUSO)
def test_ler_data(): assert ler_data("2026-11-08 18:00", AGORA) == datetime(2026, 11, 8, 18, 0, tzinfo=FUSO)
def test_ler_data_formato_errado(): ...  # "08/11 18h" -> "data inválida: use AAAA-MM-DD HH:MM"
def test_ler_data_passado(): ...         # "2026-11-05 18:00" -> "data no passado"
def test_sem_video_final(...): ...       # mensagem contém "video-final/ sem vídeo"
def test_dois_videos(...): ...           # "video-final/ com 2 vídeos: deixe só um"
def test_video_horizontal(...): ...      # 1920x1080 -> "vídeo 1920x1080, esperado 1080x1920"
def test_junta_todos_os_problemas(...):  # sem vídeo e sem post.md -> as duas linhas na mesma exceção
def test_ja_agendado(...): ...           # item agendado do corte 1 no youtube -> "youtube: corte 1 já agendado"
def test_resumo(...):
    texto = resumo(pedido, {"youtube": "privado", "tiktok": "rascunho"})
    assert "sábado, 08/11/2026 às 18:00 (Brasília)" in texto
    assert "cole no app" in texto and TEXTOS.instagram in texto
def test_confirmar_envia_youtube_e_agenda_resto(...):
    itens = confirmar(pedido, modos, {"youtube": RedeFalsa(Resultado("privado", "L", "I"))})
    assert [(i.rede, i.estado) for i in itens] == [("youtube", "privado"), ("instagram", "agendado"), ("tiktok", "agendado")]
    assert ler_fila(pasta) == itens
def test_confirmar_youtube_falha_temporaria_fica_agendado(...)
def test_nao_grava_nada_em_video_final(...):  # lista de arquivos de video-final igual antes e depois
```

- [ ] **Passo 2:** rodar `tests/test_publicar_agendar.py`. Esperado: falha.
- [ ] **Passo 3:** implementar. Dias da semana em português, numa tupla própria, sem `locale`.
- [ ] **Passo 4:** rodar. Esperado: todos passam.

---

### Tarefa 7: `rodar` (publicar o que venceu)

**Arquivos:**
- Criar: `esteira/publicar/rodar.py`
- Teste: `tests/test_publicar_rodar.py`

**Interfaces:**
- Consome: `fila.*`, `config.ler_modos`, `ler_post`, as classes de rede
- Produz:
  - `MAX_TENTATIVAS = 3`
  - `rodar_episodio(pasta: Path, agora: datetime, modos: dict, redes_api: dict) -> list[str]`, que devolve linhas de relato (`"01 instagram: publicado https://..."`)
  - `rodar_tudo(base: Path = CORTES, agora=None, redes_api=None) -> list[str]`. Usa a trava `AUTOMACAO / "publicar.trava"`: com `Ocupado`, devolve `["outra execução em andamento"]`. Percorre `base/*/postagens.json`, e um erro num episódio não impede os outros.

Em cada episódio:
1. Itens em `enviando` viram `conferir`, com o erro "envio interrompido: confira no app e use publicar marcar".
2. Itens `agendado` com `data <= agora` passam, em ordem de data, pelos passos:
   - marcar `enviando` e **gravar a fila**;
   - reler o `post.md` e o vídeo de `video-final/` (se mudaram, vale o atual);
   - chamar `publicar`;
   - gravar o resultado, com estado, link e `id_rede`.

Atraso não tem limite.

Tratamento de falhas:
- `ErroRede` temporário: volta a `agendado`, com tentativa +1. Na terceira tentativa, `erro`.
- `ErroRede` não temporário e `ErroConexao`: `erro` direto, com a mensagem.
- `ErroPost` ou vídeo ausente: `erro`, com a mensagem.

- [ ] **Passo 1: testes**

```python
def test_publica_vencido(...)                 # agendado 18:00, agora 18:05 -> publicado, link gravado
def test_nao_publica_futuro(...)
def test_atrasado_dois_dias_publica(...)      # decisão do dono: sem limite de atraso
def test_enviando_vira_conferir(...)          # rede falsa NÃO é chamada
def test_temporario_tres_vezes_vira_erro(...) # 3 rodadas com falha temporária -> estados agendado, agendado, erro
def test_conexao_vai_direto_para_erro(...)    # 1 rodada -> erro com "reconecte com publicar conectar instagram"
def test_grava_enviando_antes_de_chamar(...)  # a rede falsa lê a fila do disco durante publicar() e vê "enviando"
def test_trava_ocupada(...)                   # com trava ativa -> ["outra execução em andamento"], rede não chamada
def test_erro_num_episodio_nao_para_outro(...)
def test_rascunho_tiktok_guarda_aviso(...)    # estado "rascunho", erro/aviso "cole o texto do post.md no app"
```

- [ ] **Passo 2:** rodar `tests/test_publicar_rodar.py`. Esperado: falha.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar. Esperado: todos passam.

---

### Tarefa 8: comandos `publicar` e tarefa do Windows

**Arquivos:**
- Modificar: `esteira/cli.py` (subcomando `publicar`, com sub-ações)
- Criar: `esteira/publicar/tarefa.py`
- Teste: `tests/test_publicar_cli.py`

**Interfaces:**
- Consome: tudo acima
- Produz, na CLI:
  - `publicar conectar {youtube,instagram,tiktok}`
  - `publicar agendar PASTA --numero N --data "AAAA-MM-DD HH:MM" [--redes youtube,instagram,tiktok] [--confirmar]`
  - `publicar fila [PASTA]`
  - `publicar rodar`
  - `publicar cancelar PASTA --numero N [--redes ...]`
  - `publicar marcar PASTA --numero N --rede R {feito,reenviar}`
  - `publicar instalar-tarefa [--confirmar]`
- Produz, em `tarefa.py`:
  - `NOMES = ("Tudo é Política - publicar", "Tudo é Política - publicar ao entrar")`
  - `comandos_schtasks(python: Path, automacao: Path) -> list[list[str]]`:
    - `["schtasks", "/Create", "/F", "/TN", NOMES[0], "/SC", "MINUTE", "/MO", "15", "/TR", <linha>]`;
    - o mesmo com `NOMES[1]` e `"/SC", "ONLOGON"`.
    - `<linha>` = `cmd /c cd /d "<automacao>" && "<python>" -m esteira publicar rodar >> logs\publicar.log 2>&1`.

Comportamento:
- `agendar` sem `--confirmar` imprime o `resumo` e a linha final "Nada foi enviado. Para confirmar, rode de novo com --confirmar.", e devolve 0. Com `--confirmar`, imprime o estado de cada rede.
- `fila`, sem pasta, lista todos os episódios. Colunas: corte, rede, data, estado, link e erro. Itens `cancelado` não aparecem.
- `cancelar`:
  - `agendado` vira `cancelado`;
  - `privado`/`publicado`/`rascunho` não mudam, e o comando imprime "<rede> já enviado: apague no app se quiser" (no YouTube: "apague no Studio");
  - `enviando`/`conferir` ficam como estão, com aviso.
- `marcar`, só para item em `conferir`: `feito` vira `publicado`; `reenviar` vira `agendado`, com tentativas 0.
- `instalar-tarefa` sem `--confirmar` imprime os comandos. Com `--confirmar`, cria `Automacao/logs/` e roda os dois comandos.
- Erros novos (`ErroAgendar`, `ErroPost`, `ErroConexao`, `ErroRede`) entram no `except` de `principal`, que imprime `Erro: ...` e devolve 1.

- [ ] **Passo 1: testes** (no estilo de `tests/test_cli.py`, com `monkeypatch` nas funções)

```python
def test_agendar_sem_confirmar_nao_envia(...)  # confirmar() não é chamado; saída termina com "Nada foi enviado..."
def test_agendar_com_confirmar(...)
def test_agendar_erro_devolve_1(...)           # ErroAgendar("data no passado") -> stderr "Erro: data no passado", código 1
def test_cancelar_youtube_ja_enviado_avisa(...)
def test_marcar_so_em_conferir(...)            # item agendado -> Erro, código 1
def test_comandos_schtasks():
    c = comandos_schtasks(Path("C:/A/.venv/Scripts/python.exe"), Path("C:/A"))
    assert c[0][:9] == ["schtasks", "/Create", "/F", "/TN", "Tudo é Política - publicar", "/SC", "MINUTE", "/MO", "15"]
    assert c[1][5:7] == ["/SC", "ONLOGON"]
    assert c[0][-1].endswith("-m esteira publicar rodar >> logs\\publicar.log 2>&1")
def test_instalar_sem_confirmar_so_mostra(...) # subprocess.run não é chamado
```

- [ ] **Passo 2:** rodar `tests/test_publicar_cli.py`. Esperado: falha.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar este arquivo e `tests/test_cli.py`. Esperado: todos passam.

---

### Tarefa 9: documentação e regras

**Arquivos:**
- Modificar: `docs/operacao.md` (nova seção "11. Publicar"), `docs/arquitetura.md` (pacote `publicar`)
- Modificar, só com aprovação: `Contexto/redes-e-publicacao.md` e `CLAUDE.md` (raiz)
- Criar: `Automacao/publicacao.json` = `{"youtube": "privado", "tiktok": "rascunho"}`

Conteúdo da seção 11 em `operacao.md`:
- **Cadastro único.** Passo a passo, com links:
  - Google Cloud: criar o projeto, ativar a YouTube Data API v3, configurar a tela de consentimento e criar o "ID do cliente OAuth" do tipo "App para computador".
  - Meta for Developers: criar o app com o caso de uso "Instagram API", adicionar a conta como testadora e usar "Gerar token".
  - TikTok for Developers: criar o app com Login Kit e Content Posting API e registrar o retorno `http://localhost:8765/retorno`.
  - Depois, `publicar conectar <rede>` e `publicar instalar-tarefa`.
- **Auditorias.**
  - YouTube: formulário de auditoria da YouTube API Services. Depois da aprovação, trocar para `"agendado"`.
  - TikTok: revisão do app para Direct Post. Depois, `"direto"`.
- **Fluxo.** Pedido do dono, `agendar` sem `--confirmar`, mostrar o resumo, sim claro, `agendar --confirmar`.
  - O sim vale para aquele corte, aquelas redes e aquela data. Um pedido novo pede um sim novo.
  - Nunca rodar `--confirmar` sem o sim.
  - Nunca agendar corte sem vídeo em `video-final/`.
- **Acompanhamento.** O que fazer com `conferir`, `erro` e `rascunho`, com os comandos `fila`, `marcar` e `cancelar`.

- [ ] **Passo 1:** escrever a seção 11 em `operacao.md`, a linha em `arquitetura.md` e o `publicacao.json`.
- [ ] **Passo 2:** mostrar ao dono do canal o texto exato das mudanças em `Contexto/redes-e-publicacao.md` e `CLAUDE.md`, e pedir aprovação. Proposta:
  - `redes-e-publicacao.md`, depois de "A postagem só acontece depois da aprovação humana.": "No agendamento pela esteira, essa aprovação é o sim do dono do canal ao resumo do `publicar agendar`, para aquele corte, aquelas redes e aquela data."
  - `CLAUDE.md`, troca de "O resultado é o vídeo final para aprovação do dono do canal. Não publique nada sem essa aprovação." por: "O resultado é o vídeo final para aprovação do dono do canal. Publicar ou agendar só com o sim dele ao resumo de `publicar agendar` (ver `Automacao/docs/operacao.md`, etapa 11)."
- [ ] **Passo 3:** salvar só o que foi aprovado.
- [ ] **Passo 4:** rodar a suíte completa em segundo plano. Esperado: todos passam.

---

### Depois do plano (com o dono do canal, fora das tarefas)

1. Ele cria os três apps e roda `publicar conectar` em cada rede.
2. `publicar instalar-tarefa`: mostrar os comandos e esperar o sim.
3. Primeiro envio real: um corte escolhido por ele, com o resumo e o sim. Conferir o resultado em cada rede e ajustar o que a API real mostrar de diferente.
