# Esteira de cortes: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar, a partir de um episódio publicado, rascunhos de cortes 9:16 com legenda, listas de imagens e textos de post para finalização no CapCut.

**Architecture:** Pacote Python `esteira` com módulos pequenos e uma CLI por estágio. Cada estágio lê e grava arquivos em `Cortes/<episódio>/`. As etapas de julgamento são feitas pelo Claude Code seguindo `docs/operacao.md`.

**Tech Stack:** Python 3.12, faster-whisper, ffmpeg, Pillow, pytest.

**Spec:** `docs/superpowers/specs/2026-11-01-esteira-de-cortes-design.md`

## Global Constraints

- Raiz do canal: `C:\Tudo é Política`; todos os caminhos saem de `esteira/caminhos.py`.
- Gravar somente em `Cortes/` e `Automacao/`. Pastas de episódios são somente leitura.
- Não apagar, mover ou renomear arquivos do canal. Não sobrescrever sem `--forcar`.
- Sem chaves de API e sem segredos em arquivos.
- Python 3.12 em `Automacao/.venv`. ffmpeg e ffprobe em `Automacao/bin/`. Não usar o ffmpeg do CapCut.
- Saída 1080x1920, 30 fps, H.264 e AAC.
- Faixa central de 23% a 77% da altura: `y=442`, altura `1036`. Fundo: mesmo vídeo em tela cheia com `gblur=sigma=40`.
- Legenda: Montserrat Bold, branca, contorno preto de 3 px, 48 px, centro em `(540,1613)`, até 2 linhas, 3 a 6 palavras.
- Duração alvo: 60 a 120 s. Manter "né" e "tá". Nunca mudar o sentido da fala.
- Encerramento: `Entre Assuntos/Juliano Viegas/Cortes/Final Vídeo.mp4`.
- Textos para o usuário em português do Brasil. Vídeos nunca entram no Git.

## Review Focus

1. Caminho com acento, espaço e parênteses (`Tudo é Política`): ffmpeg deve funcionar sem erro de filtro. Teste na Tarefa 6.
2. Vídeo vertical, sem áudio ou com taxa de quadros variável: parar com mensagem clara, ou normalizar para 30 fps. Teste na Tarefa 2.
3. Falha no meio de uma gravação: nenhum arquivo parcial deve parecer pronto; usar nome temporário e renomear no fim. Testes nas Tarefas 3 e 6.
4. Trecho com tempos fora do vídeo, ou sem palavras: um corte com erro é marcado e os outros seguem. Teste na Tarefa 7.
5. Falta de memória de vídeo durante a leitura preguiçosa dos segmentos do Whisper: repetir em modo mais leve desde o início. Teste na Tarefa 3.

---

## Estrutura de arquivos

```text
Automacao/
  pyproject.toml, .gitignore
  bin/                ffmpeg.exe, ffprobe.exe (fora do Git)
  assets/fonts/       Montserrat-Bold.ttf
  esteira/
    caminhos.py       raiz, pastas e proteção de escrita
    midia.py          ffmpeg, ffprobe e sondagem
    modelos.py        Palavra, Corte, Edicao, Cue
    episodio.py       cria pasta e episodio.json
    transcrever.py    faster-whisper
    validar.py        confere trechos aprovados
    limpeza.py        pausas, gaguejos e remapeamento
    legenda.py        glossário, cues, SRT e ASS
    render.py         filtros e geração dos vídeos
    cartao.py         cartão de notícia
    cli.py            comandos
  tests/
  docs/operacao.md    roteiro das etapas do Claude Code
```

### Tarefa 1: Ambiente, caminhos e proteção de escrita

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `esteira/__init__.py`, `esteira/caminhos.py`
- Test: `tests/test_caminhos.py`

**Interfaces:**
- Produces: `RAIZ: Path`, `CONTEXTO: Path`, `CORTES: Path`, `AUTOMACAO: Path`, `BIN: Path`, `FONTES: Path`, `CARTAO_FINAL: Path`; `garantir_escrita(caminho: Path) -> Path`, que levanta `EscritaProibida` fora de `CORTES` e `AUTOMACAO`.

- [ ] **Step 1: Configurar o ambiente**

Instalar `uv` com `python -m pip install --user uv`, depois criar `.venv` com `uv venv --python 3.12 .venv`.
Baixar o ffmpeg release essentials da gyan.dev para `bin/`, conferindo o SHA-256 publicado, e Montserrat-Bold.ttf do repositório google/fonts.
Instalar `faster-whisper`, `pillow`, `pytest` e as bibliotecas NVIDIA exigidas pelo CTranslate2 para CUDA 12.
`.gitignore` inclui `.venv/`, `bin/`, `__pycache__/`, `*.mp4`, `*.mov`, `*.wav`.
Configurar `user.name` e `user.email` apenas neste repositório, com os dados informados pelo dono do canal, e registrar a spec já preparada.

- [ ] **Step 2: Verificar a GPU**

Run: `.venv/Scripts/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"`
Expected: `1`

- [ ] **Step 3: Escrever testes que falham**

```python
def test_permite_gravar_em_cortes(): assert garantir_escrita(CORTES / "x" / "a.json")
def test_bloqueia_pasta_de_episodio():
    with pytest.raises(EscritaProibida): garantir_escrita(RAIZ / "Entre Assuntos" / "a.mp4")
def test_bloqueia_caminho_com_ponto_ponto():
    with pytest.raises(EscritaProibida): garantir_escrita(CORTES / ".." / "Logos" / "a.png")
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_caminhos.py -v`
Expected: FAIL, módulo inexistente.

- [ ] **Step 5: Implementar `esteira/caminhos.py`**

Usar `Path.resolve()` antes de comparar com `is_relative_to`.

- [ ] **Step 6: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_caminhos.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

`git add .gitignore pyproject.toml esteira tests && git commit -m "feat: cria ambiente e proteção de escrita"`

### Tarefa 2: Sondagem de mídia e criação do episódio

**Files:**
- Create: `esteira/midia.py`, `esteira/modelos.py`, `esteira/episodio.py`
- Test: `tests/test_episodio.py`, `tests/auxiliares.py`

**Interfaces:**
- Consumes: `garantir_escrita`, `BIN`, `CORTES`
- Produces:
  - `@dataclass Palavra(texto: str, inicio: float, fim: float)`
  - `@dataclass Corte(numero: int, titulo: str, inicio: float, fim: float, clima: str)`
  - `@dataclass Edicao(inicio: float, fim: float, motivo: str, texto: str)`
  - `@dataclass Cue(inicio: float, fim: float, linhas: list[str])`
  - `@dataclass Midia(duracao: float, largura: int, altura: int, tem_audio: bool)`
  - `sondar(video: Path) -> Midia`
  - `executar_ffmpeg(args: list[str], cwd: Path | None = None) -> None`, que levanta `ErroMidia` com o final do stderr
  - `gerar_video_teste(saida: Path, segundos: float, largura: int = 1920, altura: int = 1080, audio: bool = True) -> Path` em `tests/auxiliares.py`, com `testsrc2` e `sine`
  - `criar_episodio(video: Path, quadro: str, numero: int, convidado: str, base: Path = CORTES) -> Path`
  - `slug(texto: str) -> str`

- [ ] **Step 1: Escrever testes que falham**

```python
def test_sonda_video(tmp_path):
    m = sondar(gerar_video_teste(tmp_path / "a.mp4", 2))
    assert (m.largura, m.altura, m.tem_audio) == (1920, 1080, True)
def test_rejeita_video_vertical(tmp_path):
    v = gerar_video_teste(tmp_path / "v.mp4", 1, 1080, 1920)
    with pytest.raises(ErroMidia, match="horizontal"): criar_episodio(v, "Entre Assuntos", 3, "Arthur", tmp_path)
def test_rejeita_sem_audio(tmp_path):
    v = gerar_video_teste(tmp_path / "s.mp4", 1, audio=False)
    with pytest.raises(ErroMidia, match="áudio"): criar_episodio(v, "Entre Assuntos", 3, "Arthur", tmp_path)
def test_cria_pasta_e_json(tmp_path):
    p = criar_episodio(gerar_video_teste(tmp_path / "e.mp4", 1), "Entre Assuntos", 3, "Arthur Cerqueira", tmp_path)
    assert p.name == "Entre Assuntos 03 - Arthur Cerqueira"
    assert json.loads((p / "episodio.json").read_text("utf-8"))["convidado"] == "Arthur Cerqueira"
def test_slug(): assert slug("Como é o A-29?") == "como-e-o-a-29"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_episodio.py -v`
Expected: FAIL, funções inexistentes.

- [ ] **Step 3: Implementar**

`sondar` usa `ffprobe -print_format json -show_format -show_streams`. `episodio.json` guarda caminho, quadro, número, convidado, duração, tamanho e data de modificação do vídeo. Se `episodio.json` existir com outro vídeo, levantar `ErroMidia`.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_episodio.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

`git add esteira tests && git commit -m "feat: adiciona sondagem de mídia e episódio"`

### Tarefa 3: Transcrição

**Files:**
- Create: `esteira/transcrever.py`
- Test: `tests/test_transcrever.py`

**Interfaces:**
- Consumes: `Palavra`, `garantir_escrita`
- Produces:
  - `carregar_glossario(caminho: Path) -> list[str]`: nomes separados por vírgula nas seções do `glossario.md`
  - `transcrever(video: Path, pasta: Path, nomes: list[str], criar_modelo=criar_whisper, forcar: bool = False) -> list[Palavra]`
  - `ler_palavras(pasta: Path) -> list[Palavra]`
  - Saídas: `transcricao/palavras.json`, `transcricao/texto.md`

- [ ] **Step 1: Escrever testes que falham**

Usar um modelo falso cujo `transcribe` devolve um gerador.

```python
def test_grava_palavras_e_texto(tmp_path): ...
    # palavras.json preserva texto, inicio e fim; texto.md tem marca [00:00:01]
def test_oom_na_iteracao_repete_mais_leve_desde_o_inicio(tmp_path):
    # o primeiro gerador emite 1 segmento e levanta RuntimeError("CUDA failed: out of memory")
    # resultado contém só as palavras do segundo modelo
def test_falha_total_nao_deixa_saida(tmp_path):
    # todos falham: RuntimeError propaga e palavras.json não existe
def test_nao_sobrescreve_sem_forcar(tmp_path): ...
def test_glossario_extrai_nomes(tmp_path):
    # "## Convidados\nPio Pacelli, Juliano Viegas\n\nOs apresentadores..." devolve os 2 nomes
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_transcrever.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar**

Modos, nesta ordem: `("large-v3","cuda","float16")`, `("large-v3","cuda","int8_float16")`, `("medium","cuda","int8_float16")`.
`transcribe(language="pt", word_timestamps=True, vad_filter=True, initial_prompt=", ".join(nomes)[:200])`.
Consumir o gerador dentro do `try`. Só "out of memory" passa ao próximo modo; outros erros propagam. Em `carregar_glossario`, considerar só linhas com vírgula ou nome único sem ponto final.
Gravar em `.tmp` e usar `Path.replace` no fim.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_transcrever.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

`git add esteira tests && git commit -m "feat: adiciona transcrição com fallback de memória"`

### Tarefa 4: Validação de trechos e limpeza da fala

**Files:**
- Create: `esteira/validar.py`, `esteira/limpeza.py`
- Test: `tests/test_validar.py`, `tests/test_limpeza.py`

**Interfaces:**
- Consumes: `Palavra`, `Corte`, `Edicao`
- Produces:
  - `validar_trecho(palavras: list[Palavra], corte: Corte, duracao_video: float) -> list[str]`, com problemas em português; lista vazia significa válido
  - `planejar_limpeza(palavras: list[Palavra], inicio: float, fim: float) -> tuple[list[tuple[float, float]], list[Edicao]]`, com faixas mantidas e remoções
  - `remapear(t: float, faixas: list[tuple[float, float]]) -> float | None`: tempo original para tempo final

- [ ] **Step 1: Escrever testes que falham**

```python
def test_recusa_duracao_fora_de_60_a_120(): ...
def test_recusa_tempo_alem_do_video(): ...
def test_recusa_fim_no_meio_da_frase(): ...   # última palavra sem . ? !
def test_recusa_trecho_sem_palavras(): ...
def test_pausa_de_1s_fica_com_0_15s():
    faixas, edicoes = planejar_limpeza(p, 0, 3)
    assert edicoes[0].motivo == "pausa"
def test_pausa_de_0_3s_fica_intacta(): ...
def test_repeticao_remove_a_primeira_ocorrencia(): ...   # "o o Brasil" -> "o Brasil"
def test_mantem_ne_ta_e_nao_nao(): ...                   # "não não" é ênfase
def test_remove_hesitacao(): ...                         # "hum", "hã", "ahn", "éé"
def test_remapear_dentro_e_fora(): ...
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_validar.py tests/test_limpeza.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar**

Pausa: intervalo acima de `0.5` s entre palavras, mantendo `0.15` s. Margens de `0.05` s em volta das palavras. Fronteira de frase: pontuação `.?!` na palavra anterior ou intervalo acima de `0.7` s. Tolerância de início e fim: `0.25` s. Comparar palavras sem pontuação e sem caixa.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_validar.py tests/test_limpeza.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

`git add esteira tests && git commit -m "feat: adiciona validação e limpeza da fala"`

### Tarefa 5: Legenda

**Files:**
- Create: `esteira/legenda.py`
- Test: `tests/test_legenda.py`

**Interfaces:**
- Consumes: `Palavra`, `Cue`, `remapear`
- Produces:
  - `corrigir_palavras(palavras: list[Palavra], nomes: list[str]) -> list[Palavra]`
  - `montar_cues(palavras: list[Palavra], faixas: list[tuple[float, float]]) -> list[Cue]`
  - `escrever_srt(cues: list[Cue], caminho: Path) -> None`
  - `escrever_ass(cues: list[Cue], caminho: Path) -> None`

- [ ] **Step 1: Escrever testes que falham**

```python
def test_tres_a_seis_palavras_e_duas_linhas(): ...
def test_quebra_em_virgula_antes_do_limite(): ...
def test_minusculas_preservando_nomes_e_siglas():
    # "O Gripen" vira "o Gripen"; "ONU" continua "ONU"
def test_remove_pontuacao_final(): ...
def test_palavra_removida_nao_aparece(): ...        # fora das faixas
def test_tempos_usam_faixas_finais(): ...
def test_corrige_nome_ignorando_acento_e_caixa(): ...   # "cronemberguer" sem acento não entra; "pio pacelli" vira "Pio Pacelli"
def test_srt_formato(): ...                         # 00:00:01,000 --> 00:00:02,500
def test_ass_estilo():
    # contém Montserrat, 48, \pos(540,1613)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_legenda.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar**

Máximo de `28` caracteres por linha. Sigla é palavra toda em maiúsculas com 2 letras ou mais. Nome próprio vem do glossário ou mantém maiúscula no meio da frase. Escapar `{`, `}` e `\` no ASS. Abrir SRT e ASS em UTF-8.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_legenda.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

`git add esteira tests && git commit -m "feat: gera legendas SRT e ASS"`

### Tarefa 6: Renderização

**Files:**
- Create: `esteira/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `executar_ffmpeg`, `sondar`, `escrever_ass`, `garantir_escrita`, `CARTAO_FINAL`, `FONTES`
- Produces:
  - `filtro_9x16() -> str`
  - `renderizar_sem_legenda(video: Path, faixas: list[tuple[float, float]], cartao: Path, saida: Path) -> None`
  - `queimar_legenda(base: Path, ass: Path, saida: Path) -> None`

- [ ] **Step 1: Escrever testes que falham**

```python
def test_filtro_tem_faixa_e_fundo():
    f = filtro_9x16()
    assert "overlay=0:442" in f and "1036" in f and "gblur=sigma=40" in f
def test_render_em_caminho_com_acento(tmp_path):
    pasta = tmp_path / "Tudo é Política (teste)"; pasta.mkdir()
    # gera origem e cartão, renderiza e queima legenda
    m = sondar(saida); assert (m.largura, m.altura) == (1080, 1920)
def test_duracao_soma_faixas_e_cartao(tmp_path): ...    # tolerância de 0.2 s
def test_cartao_sem_audio_recebe_silencio(tmp_path): ...
def test_falha_nao_deixa_arquivo_final(tmp_path):
    with pytest.raises(ErroMidia): renderizar_sem_legenda(tmp_path / "nao.mp4", ...)
    assert not saida.exists()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_render.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar**

Usar `trim`/`atrim` por faixa e `concat`, com `fps=30` e `aresample=44100`. Normalizar o cartão para 1080x1920.
Tentar `h264_nvenc -cq 19`, e cair para `libx264 -crf 18` se NVENC indisponível. Áudio AAC a 192 kb/s.
Para a legenda, rodar ffmpeg com `cwd` na pasta do corte, copiar o ASS como `legenda.ass` e usar filtro `ass=legenda.ass:fontsdir=fontes`, com cópia temporária da fonte em `fontes/`. Isso evita escapar o caminho com acento.
Gravar em `.tmp.mp4` e usar `Path.replace` só depois de conferir a duração.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_render.py -v`
Expected: PASS

- [ ] **Step 5: Conferência visual**

Gerar quadro aos 5 s de um corte de teste e comparar a posição com `Entre Assuntos/Pio Pacelli - Reitor/Cortes/Oque Motiva ele a continuar (definitivo).mp4`.
Expected: faixa e legenda nas mesmas regiões.

- [ ] **Step 6: Commit**

`git add esteira tests && git commit -m "feat: renderiza corte vertical com legenda"`

### Tarefa 7: CLI e cartão de notícia

**Files:**
- Create: `esteira/cortar.py`, `esteira/cartao.py`, `esteira/cli.py`, `esteira/__main__.py`
- Test: `tests/test_cortar.py`, `tests/test_cartao.py`

**Interfaces:**
- Consumes: todas as funções acima
- Produces:
  - `ler_aprovados(pasta: Path) -> list[Corte]`, a partir de `{"cortes":[{"numero":1,"titulo":"...","inicio":754.1,"fim":831.4,"clima":"leve"}]}`
  - `cortar_episodio(pasta: Path, numeros: set[int] | None = None, forcar: bool = False) -> dict[int, str]`, com `"ok"` ou erro por corte
  - `gerar_cartao(manchete: str, veiculo: str, data: str, saida: Path) -> Path`
  - Comandos: `python -m esteira transcrever <video> --quadro Q --numero N --convidado C`, `validar <pasta>`, `cortar <pasta> [--numero N] [--forcar]`, `cartao --manchete M --veiculo V --data D --saida S`

- [ ] **Step 1: Escrever testes que falham**

```python
def test_um_corte_invalido_nao_para_os_outros(tmp_path):
    resultado = cortar_episodio(pasta)
    assert resultado[1] == "ok" and resultado[2].startswith("erro")
    assert (pasta / "02-titulo" / "registro.json").exists()
def test_gera_todos_os_arquivos(tmp_path): ...
    # corte.mp4, corte-sem-legenda.mp4, legenda.srt, edicoes.md, imagens/, registro.json
def test_nao_sobrescreve_sem_forcar(tmp_path): ...
def test_cartao_tamanho_e_manchete_longa(tmp_path):
    # 1080x1920 com manchete de 200 caracteres sem ultrapassar margens
def test_cartao_contem_fonte(tmp_path): ...  # chamada de desenho inclui "Fonte: O Globo, 14/08/2002"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_cortar.py tests/test_cartao.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar**

Pasta do corte: `f"{numero:02d}-{slug(titulo)}"`. Validar antes de renderizar. Capturar `ErroMidia` e problemas de validação por corte. `registro.json` guarda vídeo, tempos, faixas, versão do ffmpeg, data e resultado.
Cartão: fundo preto, `Logos/Logo sem Fundo.png` no topo, manchete em Montserrat Bold branca, fonte menor abaixo, reduzindo o tamanho até caber. Sem nome ou visual imitando veículos.

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -v`
Expected: todos passam.

- [ ] **Step 5: Commit**

`git add esteira tests && git commit -m "feat: adiciona CLI, orquestração e cartão"`

### Tarefa 8: Roteiro das etapas do Claude Code

**Files:**
- Create: `docs/operacao.md`

**Interfaces:**
- Consumes: comandos da Tarefa 7 e arquivos em `Contexto/`

- [ ] **Step 1: Escrever `docs/operacao.md`**

Roteiro em português com:
- Ordem dos comandos e como escolher a versão publicada do episódio.
- Modelos de `candidatos.md`, `aprovados.json`, `imagens.md` e `post.md`, conforme a spec.
- Leitura obrigatória de `Contexto/` antes de sugerir.
- Regras: conferir antes e depois do trecho; 5 a 10 candidatos; 4 a 8 imagens; download só após aprovação; nada de IA de pessoa real; nada de página imitando veículo; aviso de IA quando aplicável.

- [ ] **Step 2: Conferir contra a spec**

Run: `git grep -n "aprovados.json" docs/operacao.md`
Expected: ao menos uma linha.

- [ ] **Step 3: Commit**

`git add docs/operacao.md && git commit -m "docs: adiciona roteiro de operação"`

### Tarefa 9: Teste real com o episódio do F1

**Files:**
- Create: `docs/resultados/2026-piloto-f1.md`

**Interfaces:**
- Consumes: todos os comandos e `docs/operacao.md`

Esta tarefa exige o dono do canal para aprovar trechos e avaliar no CapCut.

- [ ] **Step 1: Transcrever**

Run: `.venv/Scripts/python -m esteira transcrever "C:\Tudo é Política\Entre Assuntos\Arthur Cerqueira - F1\Podcast Bruto\FÓRMULA 1 Senna, Hamilton e os brasileiros na pista  Arthur Cerqueira  Entre Assuntos #03.mp4" --quadro "Entre Assuntos" --numero 3 --convidado "Arthur Cerqueira"`
Expected: `palavras.json` e `texto.md` criados, com nomes principais corretos.

- [ ] **Step 2: Sugerir e aprovar**

Gerar `candidatos.md`, receber a aprovação e gravar `aprovados.json`.
Expected: `python -m esteira validar <pasta>` sem problemas.

- [ ] **Step 3: Cortar, sugerir imagens e escrever textos**

Run: `.venv/Scripts/python -m esteira cortar "<pasta>"`
Expected: 3 a 5 pastas completas.

- [ ] **Step 4: Avaliar no CapCut**

Registrar em `docs/resultados/2026-piloto-f1.md`: critérios da spec, tempo gasto, erros novos do glossário e qualidade do enquadramento central.
Expected: decisão registrada sobre manter o recorte central ou abrir novo ciclo.

- [ ] **Step 5: Commit**

`git add docs/resultados && git commit -m "docs: registra resultado do piloto F1"`
