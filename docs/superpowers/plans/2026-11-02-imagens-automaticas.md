# Imagens automáticas (Parte 3): plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A esteira busca, filtra e baixa as fotos de cada corte e encaixa as imagens do ChatGPT, deixando ao dono do canal só a aprovação dos downloads e a geração das imagens de IA.

**Architecture:** O Claude grava `pedidos.json` por corte. Três comandos novos (`imagens buscar`, `imagens lista`, `imagens baixar`) fazem o resto. Módulos pequenos: `rede.py` (HTTP), `wikimedia.py` (API e licença), `pedidos.py` (modelo, validação, tempos), `folhas.py` (folha de candidatas), `ingestao.py` (ia-entrada) e `fluxo_imagens.py` (os três comandos por episódio). O `imagens.md` e o motor continuam como estão.

**Tech Stack:** Python 3.12, urllib (stdlib), Pillow (já instalado), pytest.

**Spec:** `docs/superpowers/specs/2026-11-02-imagens-automaticas-design.md`

## Global Constraints

- API: `https://commons.wikimedia.org/w/api.php`, sempre com `format=json&formatversion=2`.
- User-Agent: `TudoEPoliticaEsteira/1.0`, sem e-mail nem dado pessoal.
- Licenças aceitas: CC0, domínio público, CC BY, CC BY-SA. Fora: qualquer licença com NC ou ND, uso justo, sem licença.
- Formatos aceitos: `image/jpeg`, `image/png`, `image/webp`. Lado menor ≥ 800 px.
- Até 6 candidatas por pedido; busca de 20 resultados.
- Miniaturas da folha: até 640 px, em pasta temporária apagada ao fim do comando.
- Downloads finais só pelo `thumburl` devolvido pela API (largura 1920), nunca por link montado à mão.
- Imagem na tela: 2 a 5 s (`receita.IMAGEM_MINIMA`, `receita.IMAGEM_MAXIMA`), sem sobreposição, dentro da duração principal.
- Tempos de `pedidos.json` são da linha do tempo da receita (os mesmos de `legenda.srt`), em segundos.
- Prompt de IA que cite pessoa do glossário é recusado.
- Escrita só em `Cortes/` e `Automacao/` (`caminhos.garantir_escrita`).
- Alterações em `Contexto/` e no `CLAUDE.md` só com o texto mostrado ao dono do canal e aprovado.

## Review Focus

1. Licença escrita de várias formas na Wikimedia ("CC BY-SA 4.0", "Public domain", "PD-US", "CC0", "CC BY-NC 2.0", "cc-by-nd-3.0"): NC/ND sempre fora, mesmo com "BY" no nome. Teste na Tarefa 1.
2. Autor vem em HTML na `extmetadata` (`<a href=...>Fulano</a>`): a folha e o `imagens.md` mostram só o texto. Teste na Tarefa 1.
3. Nome de pessoa no prompt com acento ou caixa diferente ("ayrton senna", "Hulkenberg") e nome curto dentro de outra palavra ("Lula" em "Lulalândia" não conta): comparação sem acento e por palavra inteira. Teste na Tarefa 2.
4. Dono do canal baixa uma imagem a mais ou a menos em `ia-entrada/`: nada é gravado, o comando diz quantas esperava e quantas achou. Teste na Tarefa 5.
5. Rodar `imagens baixar` de novo depois de uma falha: arquivos já baixados não são baixados de novo. Teste na Tarefa 5.

---

## Estrutura de arquivos

```text
esteira/
  rede.py           novo: abrir(url), baixar_url, USER_AGENT (saem de musica.py)
  musica.py         importa de rede.py (nomes públicos mantidos)
  wikimedia.py      novo: Candidata, licenca_aceita, buscar_candidatas, url_final, tamanho
  pedidos.py        novo: Momento, ler/gravar, validar, ajustar_tempos, pessoas_do_glossario
  folhas.py         novo: montar_folha
  ingestao.py       novo: arquivos_ia, encaixar_ia
  fluxo_imagens.py  novo: buscar_episodio, listar_episodio, baixar_episodio
  imagens.py        + secoes_sem_arquivo
  revisao.py        alerta de imagem sem arquivo
  cli.py            imagens [buscar|lista|baixar] <pasta>
tests/
  test_wikimedia.py, test_pedidos.py, test_folhas.py, test_ingestao.py,
  test_fluxo_imagens.py (novos); test_imagens.py, test_revisao.py, test_cli.py
```

---

### Tarefa 1: rede e Wikimedia

**Files:**
- Create: `esteira/rede.py`, `esteira/wikimedia.py`, `tests/test_wikimedia.py`
- Modify: `esteira/musica.py` (remover `_abrir`, `baixar_url`, `USER_AGENT`; importar de `rede`)

**Interfaces:**
- Produces:
  - `rede.USER_AGENT = "TudoEPoliticaEsteira/1.0"`, `rede.abrir(url: str, metodo: str = "GET")` (context manager de resposta, timeout 60), `rede.baixar_url(url: str, destino: Path) -> None`. `musica.baixar_url` continua importável (re-export).
  - `Consulta = Callable[[dict], dict]`; `wikimedia.consultar(params: dict) -> dict` (GET na API com `format=json&formatversion=2`).
  - `@dataclass Candidata(titulo: str, pagina: str, miniatura: str, largura: int, altura: int, autor: str, licenca: str)`; `pagina` = `https://commons.wikimedia.org/wiki/<titulo com _>`.
  - `licenca_aceita(nome: str) -> bool`
  - `buscar_candidatas(busca: str, consultar: Consulta = consultar, limite: int = 6) -> list[Candidata]`: uma chamada com `generator=search&gsrsearch=<busca>&gsrnamespace=6&gsrlimit=20&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=640`; ordena pelo `index` da busca; filtra licença, mime e lado menor ≥ 800; ignora item sem `thumburl`. `licenca` = `LicenseShortName`; `autor` = `Artist` sem tags HTML e com espaços normalizados ("desconhecido" se vazio).
  - `url_final(titulo: str, consultar: Consulta = consultar) -> str | None`: `titles=<titulo>&prop=imageinfo&iiprop=url&iiurlwidth=1920`, devolve `thumburl` ou `None`.
  - `tamanho(url: str) -> int | None`: HEAD, `Content-Length`; `None` em erro.

- [ ] **Passo 1: testes que falham** (`tests/test_wikimedia.py`, com `consultar` falso que devolve um dicionário fixo)

```python
@pytest.mark.parametrize("nome,aceita", [
    ("CC BY-SA 4.0", True), ("CC BY 2.0", True), ("CC0", True), ("Public domain", True),
    ("PD-US", True), ("CC BY-NC 2.0", False), ("CC BY-NC-SA 4.0", False),
    ("cc-by-nd-3.0", False), ("Fair use", False), ("", False),
])
def test_licenca_aceita(nome, aceita): assert licenca_aceita(nome) is aceita

def test_filtra_licenca_formato_e_resolucao():
    # 5 páginas: ok (CC BY-SA, jpeg 3000x2000), NC, svg, 1200x700, sem thumburl
    assert [c.titulo for c in buscar_candidatas("x", falso)] == ["File:Ok.jpg"]

def test_ordem_da_busca_e_limite():  # 8 páginas válidas com index 8..1
    assert [c.titulo for c in buscar_candidatas("x", falso)][:2] == ["File:I1.jpg", "File:I2.jpg"]
    assert len(buscar_candidatas("x", falso)) == 6

def test_autor_sem_html():
    # Artist = '<a href="//x">Fulano  de\nTal</a>'
    assert buscar_candidatas("x", falso)[0].autor == "Fulano de Tal"

def test_busca_sem_resultado():  # resposta sem "query"
    assert buscar_candidatas("x", lambda p: {}) == []

def test_url_final_usa_thumburl():
    assert url_final("File:A.jpg", lambda p: {"query": {"pages": [{"imageinfo": [{"thumburl": "https://u/1920px-A.jpg", "url": "https://u/A.jpg"}]}]}}) == "https://u/1920px-A.jpg"
    assert url_final("File:A.jpg", lambda p: {"query": {"pages": [{"missing": True}]}}) is None

def test_consulta_pede_largura_640():  # o consultar falso guarda params
    buscar_candidatas("Senna", falso); assert params["iiurlwidth"] == 640 and params["gsrnamespace"] == 6
```

- [ ] **Passo 2:** `.venv\Scripts\python.exe -m pytest tests/test_wikimedia.py -q` → FAIL (módulo não existe).
- [ ] **Passo 3:** implementar `rede.py` e `wikimedia.py`. `licenca_aceita`: normalizar para minúsculas e trocar `-`/`_` por espaço; recusar se contém palavra `nc` ou `nd`; aceitar se começa com `cc0`, `public domain`, `pd` ou casa `^cc by( sa)? \d`.
- [ ] **Passo 4:** `.venv\Scripts\python.exe -m pytest tests/test_wikimedia.py tests/test_musica.py -q` → PASS.
- [ ] **Passo 5:** commit `feat: busca e filtro de licença na Wikimedia`.

---

### Tarefa 2: pedidos, validação e ajuste de tempo

**Files:**
- Create: `esteira/pedidos.py`, `tests/test_pedidos.py`

**Interfaces:**
- Consumes: `receita.IMAGEM_MINIMA`, `receita.IMAGEM_MAXIMA`; `episodio.slug`.
- Produces:
  - `TIPOS = ("foto", "noticia", "ia")`; `ARQUIVO = "pedidos.json"`.
  - `@dataclass Momento(inicio: float, fim: float, fala: str, tipo: str, nome: str, busca: str = "", titulo: str = "", veiculo: str = "", data: str = "", prompt: str = "", candidatas: list[dict] = [], escolha: int | None = None, descartar: bool = False, motivo: str = "", numero: int | None = None, url: str = "", bytes: int | None = None)`. `nome` é o rótulo curto ("Yas Marina"); `candidatas` guarda `asdict(Candidata)`; `escolha` é 1-based.
  - `ler_pedidos(pasta: Path) -> list[Momento]`, `gravar_pedidos(pasta: Path, momentos: list[Momento]) -> None` (JSON `{"momentos": [...]}`, UTF-8, indentado).
  - `pessoas_do_glossario(caminho: Path) -> list[str]`: nomes das seções `##` cujo título contém "Apresentadores", "Convidados" ou "Pessoas".
  - `validar_pedidos(momentos: list[Momento], duracao: float, pessoas: list[str]) -> list[str]`
  - `ajustar_tempos(momentos: list[Momento], duracao: float) -> list[str]`: altera a lista no lugar e devolve os avisos.

- [ ] **Passo 1: testes que falham**

```python
def test_valida_campos_por_tipo():
    m = [Momento(1, 3, "f", "foto", "A"), Momento(5, 7, "f", "noticia", "B", titulo="T"),
         Momento(9, 11, "f", "ia", "C"), Momento(13, 15, "f", "video", "D")]
    assert validar_pedidos(m, 60, []) == [
        "momento 1: foto sem busca", "momento 2: notícia sem veiculo",
        "momento 2: notícia sem data", "momento 3: ia sem prompt", "momento 4: tipo inválido 'video'"]

def test_tempo_fora_do_corte():
    assert validar_pedidos([Momento(58, 62, "f", "foto", "A", busca="x")], 60, []) == ["momento 1: fora do corte"]
    assert validar_pedidos([Momento(5, 5, "f", "foto", "A", busca="x")], 60, []) == ["momento 1: fora do corte"]

def test_prompt_com_pessoa_recusado():
    m = [Momento(1, 3, "f", "ia", "A", prompt="retrato de ayrton senna na chuva"),
         Momento(5, 7, "f", "ia", "B", prompt="carro igual ao do Hulkenberg"),
         Momento(9, 11, "f", "ia", "C", prompt="parque Lulalândia")]
    assert validar_pedidos(m, 60, ["Ayrton Senna", "Nico Hülkenberg", "Hülkenberg", "Lula"]) == [
        "momento 1: prompt cita pessoa real (Ayrton Senna)",
        "momento 2: prompt cita pessoa real (Hülkenberg)"]

def test_descartado_nao_e_validado():
    assert validar_pedidos([Momento(1, 3, "f", "video", "A", descartar=True)], 60, []) == []

def test_pessoas_do_glossario(tmp_path):
    (tmp_path / "g.md").write_text("# G\n\n## Canal\nTudo é Política\n\n## Pessoas citadas\nLula, Messi\n\n"
        "## Pessoas do automobilismo\nMax Verstappen\n\n## Automobilismo\nFerrari\n", "utf-8")
    assert pessoas_do_glossario(tmp_path / "g.md") == ["Lula", "Messi", "Max Verstappen"]

def test_estende_curto_para_frente():
    m = [Momento(10, 11, "f", "foto", "A")]
    assert ajustar_tempos(m, 60) == [] and (m[0].inicio, m[0].fim) == (10, 12)

def test_estende_para_tras_quando_encosta():
    m = [Momento(10, 11.5, "f", "foto", "A"), Momento(11.5, 14, "f", "foto", "B")]
    ajustar_tempos(m, 60); assert (m[0].inicio, m[0].fim) == (9.5, 11.5)

def test_corta_longo():
    m = [Momento(10, 18, "f", "foto", "A")]; ajustar_tempos(m, 60); assert m[0].fim == 15

def test_sem_espaco_descarta():
    m = [Momento(10, 12, "f", "foto", "A"), Momento(12, 13, "f", "foto", "B"), Momento(13, 15, "f", "foto", "C")]
    assert ajustar_tempos(m, 60) == ["momento 2 (B) descartado: não cabe em 2 s"]
    assert m[1].descartar and m[1].motivo == "não cabe em 2 s"

def test_fim_do_corte():
    m = [Momento(59, 59.5, "f", "foto", "A")]; ajustar_tempos(m, 60); assert (m[0].inicio, m[0].fim) == (58, 60)

def test_ida_e_volta_json(tmp_path):
    m = [Momento(1, 3, "f", "foto", "A", busca="x", candidatas=[{"titulo": "File:A.jpg"}], escolha=1)]
    gravar_pedidos(tmp_path, m); assert ler_pedidos(tmp_path) == m
```

- [ ] **Passo 2:** `.venv\Scripts\python.exe -m pytest tests/test_pedidos.py -q` → FAIL.
- [ ] **Passo 3:** implementar. Pessoa no prompt: comparar sem acento e em minúsculas, por palavra inteira (`\b`), relatando o nome do glossário como escrito. `ajustar_tempos` percorre os não descartados em ordem de `inicio`: corta em 5 s; se < 2 s, estende o fim até `min(inicio + 2, próximo.inicio, duracao)`, depois o início para trás até `max(fim - 2, anterior.fim, 0)`; se ainda < 2 s (tolerância `receita.TOLERANCIA`), descarta com o aviso do teste.
- [ ] **Passo 4:** mesmo comando → PASS.
- [ ] **Passo 5:** commit `feat: pedidos de imagem com validação e ajuste de tempo`.

---

### Tarefa 3: folha de candidatas

**Files:**
- Create: `esteira/folhas.py`, `tests/test_folhas.py`

**Interfaces:**
- Consumes: `wikimedia.Candidata`; fonte `cartao.ARQUIVO_FONTE`.
- Produces: `montar_folha(titulo: str, candidatas: list[Candidata], miniaturas: list[Path | None], saida: Path) -> Path`. Grade 3x2, célula 400x400 (miniatura inteira, centralizada), legenda de 2 linhas por célula: `N · vertical|horizontal` (vertical se altura/largura ≥ `render.PROPORCAO_TELA_CHEIA`) e `autor · licença` truncado a 45 caracteres. Cabeçalho com `titulo`. Miniatura `None` ou ilegível vira célula cinza "sem miniatura". Sem candidatas: folha só com o cabeçalho e "nenhuma". JPEG, qualidade 85.

- [ ] **Passo 1: testes que falham** (miniaturas sintéticas geradas com Pillow em `tmp_path`)

```python
def test_folha_com_seis(tmp_path):
    saida = montar_folha("01-1 Yas Marina", [cand(i) for i in range(6)], [mini(tmp_path, i) for i in range(6)], tmp_path / "f.jpg")
    with Image.open(saida) as img: assert img.size == (1200, ALTURA_FOLHA) and img.format == "JPEG"

def test_miniatura_ausente_ou_quebrada(tmp_path):
    ruim = tmp_path / "ruim.jpg"; ruim.write_bytes(b"<html>")
    montar_folha("x", [cand(0), cand(1)], [None, ruim], tmp_path / "f.jpg")  # não levanta

def test_sem_candidatas(tmp_path):
    assert montar_folha("x", [], [], tmp_path / "f.jpg").exists()
```

(`ALTURA_FOLHA` é constante exportada pelo módulo: cabeçalho + 2 linhas de células com legenda.)

- [ ] **Passo 2:** `.venv\Scripts\python.exe -m pytest tests/test_folhas.py -q` → FAIL.
- [ ] **Passo 3:** implementar com Pillow (`Image.thumbnail`, `ImageDraw`, `ImageFont.truetype(ARQUIVO_FONTE, 22)`).
- [ ] **Passo 4:** mesmo comando → PASS.
- [ ] **Passo 5:** commit `feat: folha de candidatas`.

---

### Tarefa 4: `buscar_episodio` e `listar_episodio`

**Files:**
- Create: `esteira/fluxo_imagens.py`, `tests/test_fluxo_imagens.py`

**Interfaces:**
- Consumes: Tarefas 1 a 3; `cortar.ler_aprovados`, `cortar.pasta_do_corte`; `receita.ler_receita`, `receita.duracao_principal`; `episodio.slug`.
- Produces:
  - `buscar_episodio(pasta: Path, numeros: set[int] | None, pessoas: list[str], consultar: Consulta = wikimedia.consultar, baixar: Callable[[str, Path], None] = rede.baixar_url) -> dict[int, str]`
  - `listar_episodio(pasta: Path, numeros: set[int] | None, pessoas: list[str], consultar: Consulta = wikimedia.consultar, medir: Callable[[str], int | None] = wikimedia.tamanho) -> dict[int, str]`
  - Resultado por corte: `"ok"`, `"ok com alertas: ..."`, `"erro: ..."` (mesmo padrão de `preparar`). Corte sem `pedidos.json` não aparece no resultado.

`buscar_episodio`:
1. Para cada corte com `pedidos.json`: valida (`validar_pedidos` com a duração principal da receita). Erro → `"erro: ..."` e o corte fica como está.
2. Fase de rede, sem gravar nada: `buscar_candidatas` para cada momento `foto` não descartado. `OSError`/`ValueError` da API → levanta `ErroBusca("Wikimedia indisponível: ...")` (exceção do módulo) e nada é gravado.
3. Miniaturas em `tempfile.TemporaryDirectory()`; falha de uma miniatura vira `None`.
4. Grava `candidatas` (e zera `escolha`) no `pedidos.json` e a folha `candidatas/NN-M.jpg` (NN = corte, M = posição do momento, 1-based). Momento sem candidata: alerta `momento M sem candidata`.

`listar_episodio`:
1. Valida de novo (cobre troca para IA). Momento `foto` sem `escolha` válida → `"erro: momento M sem escolha"` e nada é gravado nesse corte.
2. `ajustar_tempos`; avisos viram alertas.
3. Numera os não descartados (`numero` = 1..n, em ordem de `inicio`). Para cada foto escolhida: `url = url_final(titulo)`, `bytes = medir(url)`. `url` `None` → alerta e o momento é descartado com motivo "sem link de download".
4. Grava `pedidos.json` e o `imagens.md` do corte no formato atual: título `## N. HH:MM:SS,mmm a HH:MM:SS,mmm — <nome>`, depois `Tipo:` (`foto livre`, `notícia`, `ilustração de IA`), `Fala: "<fala>"`, `Origem:` (página / `cartão do canal` / `gerada no ChatGPT (OpenAI) a partir do prompt acima`), `Baixar: <url>` só para foto, `Prompt:` só para IA, `Autor e licença:` (`<autor>, <licença>` / `cartão do canal, <veículo>` / `ilustração de IA, ChatGPT (OpenAI)`).
5. No episódio: `lista-imagens.md` (mesmo formato do F1: uma seção por corte, linha `- N. início a fim — nome — <arquivo> — <KB> KB`, `tamanho desconhecido` sem `bytes`, `gerar por IA`, `cartão do canal`); `prompts-chatgpt.md` (mesmo texto de cabeçalho e bloco do F1, prompts numerados na ordem corte → número, e a seção "Para onde vai cada imagem"); cria `ia-entrada/`.

- [ ] **Passo 1: testes que falham** (episódio mínimo em `tmp_path` com `aprovados.json`, pasta do corte e um `montagem.json` gravado por `gravar_receita` com uma faixa `(0, 60)`; `consultar` falso; `baixar` falso grava uma imagem sintética)

```python
def test_buscar_grava_candidatas_e_folha(tmp_path): ...
    assert buscar_episodio(ep, None, [], falso, baixar) == {1: "ok"}
    assert len(ler_pedidos(corte)[0].candidatas) == 2 and (corte / "candidatas" / "01-1.jpg").exists()

def test_buscar_api_fora_nao_grava(tmp_path):
    with pytest.raises(ErroBusca): buscar_episodio(ep, None, [], quebra, baixar)
    assert ler_pedidos(corte)[0].candidatas == [] and not (corte / "candidatas").exists()

def test_buscar_recusa_prompt_com_pessoa(tmp_path):
    assert buscar_episodio(ep, None, ["Ayrton Senna"], falso, baixar)[1].startswith("erro: momento 2: prompt cita pessoa real")

def test_buscar_sem_candidata_alerta(tmp_path):
    assert buscar_episodio(ep, None, [], lambda p: {}, baixar) == {1: "ok com alertas: momento 1 sem candidata"}

def test_listar_exige_escolha(tmp_path):
    assert listar_episodio(ep, None, [], falso, lambda u: 1000) == {1: "erro: momento 1 sem escolha"}
    assert not (corte / "imagens.md").exists()

def test_listar_escreve_imagens_md_lido_pelo_leitor(tmp_path):
    # foto escolhida 10.0–11.0, ia 20–23, noticia 30–33; criar imagens/01-*,02-*,03-* falsos depois
    listar_episodio(ep, None, [], falso, lambda u: 2048)
    assert [(i.inicio, i.fim) for i in ler_imagens(corte)] == [(10.0, 12.0), (20.0, 23.0), (30.0, 33.0)]
    assert "Baixar: https://u/1920px-A.jpg" in (corte / "imagens.md").read_text("utf-8")

def test_listar_lista_e_prompts(tmp_path):
    lista = (ep / "lista-imagens.md").read_text("utf-8")
    assert "— 2 KB" in lista and "gerar por IA" in lista and "cartão do canal" in lista
    assert "1 → corte 01, imagem 2" in (ep / "prompts-chatgpt.md").read_text("utf-8")
    assert (ep / "ia-entrada").is_dir()

def test_listar_sem_link_descarta(tmp_path):  # url_final devolve None
    assert "sem link de download" in listar_episodio(ep, None, [], sem_thumb, lambda u: 1)[1]
```

- [ ] **Passo 2:** `.venv\Scripts\python.exe -m pytest tests/test_fluxo_imagens.py -q` → FAIL.
- [ ] **Passo 3:** implementar as duas funções em `fluxo_imagens.py`. Nome de arquivo final: `imagens/NN-<slug(nome)>.<ext>` (`jpg` para foto, `png` para notícia, extensão original para IA); a função auxiliar `nome_arquivo(m: Momento, ext: str) -> str` fica pública para a Tarefa 5.
- [ ] **Passo 4:** mesmo comando → PASS.
- [ ] **Passo 5:** commit `feat: comandos de busca e lista de imagens`.

---

### Tarefa 5: ingestão de IA e `baixar_episodio`

**Files:**
- Create: `esteira/ingestao.py`, `tests/test_ingestao.py`
- Modify: `esteira/fluxo_imagens.py`, `esteira/imagens.py`, `esteira/revisao.py`, `tests/test_fluxo_imagens.py`, `tests/test_imagens.py`, `tests/test_revisao.py`

**Interfaces:**
- Consumes: `fluxo_imagens.nome_arquivo`; `cartao.gerar_cartao(manchete, veiculo, data, saida)`; `cortar.atualizar_imagens(pasta_corte) -> int`.
- Produces:
  - `ingestao.arquivos_ia(pasta: Path) -> list[Path]`: arquivos de imagem (`imagens.EXTENSOES`) de `ia-entrada/`, sem ocultos, ordenados por data de modificação e depois nome.
  - `ingestao.encaixar_ia(pasta: Path, destinos: list[tuple[Path, str, str]]) -> list[Path]`: `destinos` = (pasta do corte, nome de arquivo sem extensão, rótulo `NN\tM\tnome\tprompt`). Se `len(arquivos) != len(destinos)`, levanta `ValueError("ia-entrada/: esperadas X imagens, encontradas Y")` sem gravar. Senão copia cada arquivo para `<corte>/imagens/<nome><ext original>` e grava `ia-entrada/.mapa.tsv` (uma linha por rótulo + nome do arquivo de origem).
  - `fluxo_imagens.baixar_episodio(pasta: Path, numeros: set[int] | None, baixar: Callable[[str, Path], None] = rede.baixar_url) -> dict[int, str]`
  - `imagens.secoes_sem_arquivo(pasta: Path) -> list[int]`: números das seções do `imagens.md` sem arquivo em `imagens/`.

`baixar_episodio`:
1. Junta os destinos de IA de todos os cortes selecionados e chama `encaixar_ia` primeiro; `ValueError` → todos os cortes recebem `"erro: <mensagem>"` e nada mais é feito.
2. Por momento: foto → se o arquivo final não existe, baixa para um `.parcial`, confere com `PIL.Image.open(...).verify()` e renomeia; falha (rede ou não-imagem) → alerta `imagem N: download falhou` e o `.parcial` é apagado. Notícia → `gerar_cartao(titulo, veiculo, data, ...)` se não existir.
3. `atualizar_imagens(pasta_corte)`; resultado `"ok: N imagens"` ou `"ok com alertas: ..."`.

`revisao._alertas` passa a acrescentar `imagem N sem arquivo` para cada número de `secoes_sem_arquivo`.

- [ ] **Passo 1: testes que falham**

```python
# test_ingestao.py
def test_ordem_por_data(tmp_path):  # cria b.png com mtime 100 e a.png com mtime 200 (os.utime)
    assert [p.name for p in arquivos_ia(ep)] == ["b.png", "a.png"]

def test_ignora_mapa_e_ocultos(tmp_path):  # .mapa.tsv, .x.png, nota.txt
    assert arquivos_ia(ep) == []

def test_contagem_diferente_nao_grava(tmp_path):
    with pytest.raises(ValueError, match="esperadas 2 imagens, encontradas 1"): encaixar_ia(ep, dois_destinos)
    assert not (corte / "imagens").exists() or not any((corte / "imagens").iterdir())

def test_encaixa_e_grava_mapa(tmp_path):
    encaixar_ia(ep, [(corte, "02-chuva", "01\t2\tChuva\tprompt")])
    assert (corte / "imagens" / "02-chuva.png").exists()
    assert (ep / "ia-entrada" / ".mapa.tsv").read_text("utf-8").startswith("01\t2\tChuva\tprompt\t")

# test_fluxo_imagens.py
def test_baixar_foto_cartao_e_ia(tmp_path):  # após listar_episodio; 1 arquivo em ia-entrada
    assert baixar_episodio(ep, None, baixar_imagem) == {1: "ok: 3 imagens"}
    assert len(ler_receita(corte).imagens) == 3

def test_baixar_falha_isolada(tmp_path):  # baixar grava "<html>" no lugar da foto
    assert baixar_episodio(ep, None, baixar_html)[1] == "ok com alertas: imagem 1: download falhou"
    assert not list((corte / "imagens").glob("*.parcial"))

def test_baixar_nao_repete_download(tmp_path):
    baixar_episodio(ep, None, baixar_imagem); chamadas.clear()
    baixar_episodio(ep, None, baixar_imagem); assert chamadas == []

def test_baixar_contagem_ia_errada(tmp_path):  # 0 arquivos em ia-entrada
    assert baixar_episodio(ep, None, baixar_imagem) == {1: "erro: ia-entrada/: esperadas 1 imagens, encontradas 0"}

# test_imagens.py
def test_secoes_sem_arquivo(tmp_path):
    _pasta(tmp_path, MD, "01-gripen.jpg"); assert secoes_sem_arquivo(tmp_path) == [2]

# test_revisao.py
def test_alerta_imagem_sem_arquivo(...):  # corte montado com imagens.md de 2 seções e 1 arquivo
    assert "imagem 2 sem arquivo" in revisao_texto
```

- [ ] **Passo 2:** `.venv\Scripts\python.exe -m pytest tests/test_ingestao.py tests/test_fluxo_imagens.py tests/test_imagens.py tests/test_revisao.py -q` → FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** mesmo comando → PASS.
- [ ] **Passo 5:** commit `feat: download de fotos e encaixe das imagens de IA`.

---

### Tarefa 6: CLI

**Files:**
- Modify: `esteira/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: Tarefas 2, 4 e 5; `caminhos.CONTEXTO`.
- Produces: `esteira imagens [atualizar|buscar|lista|baixar] <pasta> [--numero N ...]`. Sem ação = `atualizar` (comportamento atual, preservado). `acao` é posicional com `nargs="?"`, `choices` e `default="atualizar"`, declarado antes de `pasta`. `buscar` e `lista` passam `pessoas_do_glossario(CONTEXTO / "glossario.md")`. Saída por corte com `_imprimir`. `ErroBusca` entra no `except` de `principal` (mensagem `Erro: ...`, código 1).

- [ ] **Passo 1: testes que falham**

```python
def test_imagens_sem_acao_continua_atualizando(...):  # mesmo cenário do teste atual de `imagens`
    assert principal(["imagens", str(ep)]) == 0

def test_imagens_buscar_chama_fluxo(monkeypatch, ...):
    monkeypatch.setattr(cli, "buscar_episodio", lambda p, n, pessoas: {1: "ok"})
    assert principal(["imagens", "buscar", str(ep)]) == 0

def test_imagens_buscar_api_fora(monkeypatch, capsys, ...):
    def quebra(*a): raise ErroBusca("Wikimedia indisponível: x")
    monkeypatch.setattr(cli, "buscar_episodio", quebra)
    assert principal(["imagens", "buscar", str(ep)]) == 1 and "Wikimedia indisponível" in capsys.readouterr().err

def test_imagens_baixar_erro_retorna_1(monkeypatch, ...):
    monkeypatch.setattr(cli, "baixar_episodio", lambda p, n: {1: "erro: x"})
    assert principal(["imagens", "baixar", str(ep)]) == 1
```

- [ ] **Passo 2:** `.venv\Scripts\python.exe -m pytest tests/test_cli.py -q` → FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** suíte completa `.venv\Scripts\python.exe -m pytest -q` → todos passando.
- [ ] **Passo 5:** commit `feat: comandos imagens buscar, lista e baixar`.

---

### Tarefa 7: regras e documentação (com aprovação)

**Files:**
- Modify: `docs/operacao.md` (seção de imagens), `../Contexto/estilo-de-imagens.md`, `../Contexto/glossario.md`, `../CLAUDE.md`

O controlador mostra cada texto ao dono do canal e só salva depois da aprovação.

- [ ] **Passo 1:** `operacao.md`: substituir o roteiro manual pelo fluxo de 7 passos da spec (seção 3), com o formato de `pedidos.json` (inclusive `nome` e `data` da notícia), como escolher (`escolha`, troca para `ia`, `descartar`) e os três comandos.
- [ ] **Passo 2:** `estilo-de-imagens.md`: trocar "A esteira sugere de 4 a 8 imagens por corte" por "A esteira sugere de 4 a 6 imagens por corte" e acrescentar "Fotos da internet: só Wikimedia Commons, com licença CC0, domínio público, CC BY ou CC BY-SA."
- [ ] **Passo 3:** `glossario.md`: mover os pilotos e dirigentes da seção "Automobilismo" para a nova seção "## Pessoas do automobilismo" (Max Verstappen, Lando Norris, Charles Leclerc, Fernando Alonso, Felipe Massa, Rubens Barrichello, Nelson Piquet, Alain Prost, Michael Schumacher, Gabriel Bortoleto, Rafael Câmara, Kimi Antonelli, Oliver Bearman, Nico Hülkenberg, Logan Sargeant, Stefano Domenicali). A correção da transcrição não muda (`carregar_glossario` lê todas as seções).
- [ ] **Passo 4:** `CLAUDE.md`, após a regra de downloads: "Miniaturas de pré-visualização (até 640 px, apagadas ao fim do comando) não precisam de confirmação."
- [ ] **Passo 5:** commit `docs: regras das imagens automáticas`.

---

### Teste real (fora das tarefas, depois do merge da branch)

Refazer do zero as imagens de um episódio: o Claude grava os pedidos, roda `buscar`, escolhe pelas folhas, roda `lista`; o dono do canal aprova e gera as imagens de IA; `baixar`, `montar --forcar` (com autorização) e revisão. Registrar em `docs/resultados/`.
