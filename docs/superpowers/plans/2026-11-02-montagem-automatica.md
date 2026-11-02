# Montagem automática (Parte 1): plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer a esteira entregar `final.mp4` pronto por corte, montado a partir de uma receita (`montagem.json`), e uma `revisao.md` por episódio para a aprovação única do dono do canal.

**Architecture:** O comando `cortar` vira `preparar`: limpa a fala, gera a legenda e grava `montagem.json`, sem render. O Claude marca destaques na receita. O comando `montar` lê a receita e gera `final.mp4` numa única passada do ffmpeg (segmentos, imagens, legenda ASS com destaque, música com ducking, encerramento). O comando `revisao` escreve `revisao.md`.

**Tech Stack:** Python 3.12, ffmpeg/ffprobe em `Automacao/bin/`, Pillow, pytest.

**Spec:** `docs/superpowers/specs/2026-11-02-montagem-automatica-design.md`

## Global Constraints

- Rodar tudo a partir de `Automacao/` com `.venv\Scripts\python.exe`. Testes: `.venv\Scripts\python.exe -m pytest`.
- Gravar somente em `Cortes/` e `Automacao/` (`garantir_escrita`). Pastas de episódios são somente leitura.
- Saída 1080x1920, 30 fps, H.264 (NVENC, com libx264 de reserva) e AAC 44,1 kHz estéreo, como em `render.py`.
- Legenda: estilo atual de `legenda.py` (Montserrat 90, branca, contorno preto 3, `\pos(540,1530)`). Destaque em amarelo, ASS `&H00FFFF&`, no máximo uma palavra por tela.
- Imagens: tela cheia, de 2 a 5 segundos, sem legenda durante a imagem, sem sobreposição entre imagens.
- Música: `volume_db` entre -22 e -18, ducking sob a voz, fade de entrada e saída, termina antes do encerramento.
- Duração final: soma das faixas mais o encerramento, tolerância de 0,5 s.
- `final.mp4` nunca é sobrescrito sem `--forcar`. Gravação sempre em `.tmp.mp4` e renomeada só depois das checagens.
- Deixam de ser gerados `corte.mp4` e `corte-sem-legenda.mp4`.
- Alterações em `Contexto/` e `CLAUDE.md` só depois de mostrar o texto ao dono do canal e receber aprovação.
- Textos para o usuário em português do Brasil. Vídeos não entram no Git.

## Review Focus

1. Imagem horizontal ou quadrada deve cobrir a tela 1080x1920 sem distorcer (escala para cobrir e recorte central). Teste na Tarefa 5.
2. Imagem que passa do fim do corte, que se sobrepõe a outra ou cujo arquivo não existe: a receita é rejeitada com mensagem clara e o corte fica marcado com erro, sem parar os outros. Testes nas Tarefas 2 e 6.
3. Música mais curta que o corte deve repetir; mais longa deve ser cortada; o vídeo final mantém a duração esperada. Teste na Tarefa 5.
4. Destaque com maiúscula, acento ou pontuação diferente do texto ("Gripen," e "gripen") deve casar com a palavra da tela. Teste na Tarefa 3.
5. Caminhos com acento e espaço (`Tudo é Política`) para imagens e música não podem quebrar o filtro: arquivos entram como `-i`, nunca dentro da string do filtro. Teste na Tarefa 5.

---

## Estrutura de arquivos

```text
esteira/
  modelos.py    + Corte.instagram, Corte.data; + Cue.destaque
  receita.py    NOVO: Imagem, Musica, Receita; ler, gravar, validar
  legenda.py    ASS com destaque; ocultar legenda durante imagens
  imagens.py    NOVO: lê imagens.md e acha os arquivos em imagens/
  midia.py      + pico_de_audio
  render.py     renderizar_final (passada única); remove queimar_legenda e renderizar_sem_legenda
  cortar.py     cortar_episodio vira preparar_episodio (sem render)
  montar.py     NOVO: montar_episodio
  revisao.py    NOVO: escrever_revisao
  cli.py        preparar, imagens, montar, revisao (sai cortar)
tests/
  test_receita.py, test_imagens.py, test_montar.py, test_revisao.py (novos)
  test_legenda.py, test_render.py, test_cortar.py (ajustados)
```

---

### Tarefa 1: Conferir como as imagens entram nos cortes de referência

Investigação, sem código de produção. Define a constante `ZOOM_IMAGEM` usada na Tarefa 5.

**Files:**
- Leitura: `Por Trás do TCC/Tiago Avellar/Cortes/GRIPEN (definitivo).mp4`, `Por Trás do TCC/Gabriel Cronemberger/Cortes/Corte Lula 2002 (definitivo).mp4`
- Rascunho: pasta de scratchpad da sessão (nada é gravado no canal)

- [ ] **Step 1: Achar as trocas para imagem.** Rodar detecção de cena (`select='gt(scene,0.3)',showinfo`) nos dois cortes e anotar os tempos.
- [ ] **Step 2: Extrair quadros de 3 imagens por corte**, em +0,1 s, meio e -0,1 s de cada imagem, para o scratchpad.
- [ ] **Step 3: Comparar os quadros.** Se o enquadramento da imagem muda entre o início e o fim, é aproximação leve; estimar o fator (ex.: 1,06). Se não muda, é corte seco. Conferir também se há transição (fade) na entrada.
- [ ] **Step 4: Mostrar o resultado ao dono do canal**, com 2 quadros de exemplo, e a proposta de texto para `Contexto/estilo-de-imagens.md` (ex.: "Entrada: corte seco, sem animação" ou "Aproximação leve de cerca de 6% durante a imagem"). Salvar só depois da aprovação.
- [ ] **Step 5: Registrar a decisão** para a Tarefa 5: `ZOOM_IMAGEM = 1.0` (corte seco) ou o fator aprovado.

---

### Tarefa 2: Receita do corte

**Files:**
- Modify: `esteira/modelos.py`
- Create: `esteira/receita.py`
- Test: `tests/test_receita.py`

**Interfaces:**
- Produces:
  - `Corte` ganha `instagram: bool = False` e `data: str = ""` (data e hora sugeridas, ex.: `"2026-11-04 18:00"`).
  - `Cue` ganha `destaque: str | None = None`.
  - `@dataclass Imagem(inicio: float, fim: float, arquivo: str, licenca: str = "")`; `arquivo` é relativo à pasta do corte.
  - `@dataclass Musica(arquivo: str, volume_db: float = -20.0)`; `arquivo` absoluto.
  - `@dataclass Receita(faixas: list[tuple[float, float]], planos: list[Plano], legenda: list[Cue], imagens: list[Imagem] = [], musica: Musica | None = None, encerramento: bool = True, versao: int = 1)` (listas com `field(default_factory=list)`).
  - `duracao_principal(receita: Receita) -> float`: soma das faixas.
  - `gravar_receita(pasta: Path, receita: Receita) -> None` e `ler_receita(pasta: Path) -> Receita`, em `montagem.json`, no formato da seção 4 da spec (legenda com `linhas`).
  - `validar_receita(receita: Receita, pasta: Path) -> list[str]`: lista de problemas em português, vazia se ok.

- [ ] **Step 1: Escrever os testes**

```python
def test_receita_ida_e_volta(tmp_path):
    r = Receita([(1.0, 3.0)], [Plano(1.0, 3.0, 0.3, 0.5, 1.35)],
                [Cue(0.0, 1.0, ["o gripen"], "gripen")],
                [Imagem(0.5, 1.5, "imagens/01-a.jpg")], Musica("C:/m.mp3", -20))
    gravar_receita(tmp_path, r)
    assert ler_receita(tmp_path) == r

def test_receita_valida_nao_tem_problemas(tmp_path): ...       # imagem e música existentes -> []
def test_imagem_fora_do_corte(tmp_path): ...                  # fim > duracao_principal -> "imagem 1 passa do fim do corte"
def test_imagens_sobrepostas(tmp_path): ...                   # -> "imagens 1 e 2 se sobrepõem"
def test_imagem_curta_ou_longa(tmp_path): ...                 # 1,5 s e 5,5 s -> "imagem 1 fora de 2 a 5 segundos"
def test_arquivo_de_imagem_inexistente(tmp_path): ...         # -> "imagem 1 não encontrada: imagens/01-a.jpg"
def test_musica_inexistente_ou_volume_fora(tmp_path): ...     # -> "música não encontrada", "volume da música fora de -22 a -18 dB"
def test_destaque_ausente_da_tela(tmp_path): ...              # Cue(.., ["o caça"], "gripen") -> "destaque 'gripen' não está na tela 1"
def test_corte_aceita_campos_novos(): assert Corte(1, "t", 0, 60, "leve").instagram is False
```

Tolerância de 0,05 s nas comparações de tempo. A comparação de destaque usa `legenda._chave` em cada palavra das linhas.

- [ ] **Step 2: Rodar** `.venv\Scripts\python.exe -m pytest tests/test_receita.py -v`. Esperado: FAIL (módulo inexistente).
- [ ] **Step 3: Implementar** `modelos.py` e `receita.py` com as assinaturas acima. JSON com `ensure_ascii=False, indent=2`.
- [ ] **Step 4: Rodar** os testes da tarefa e a suíte toda. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: adiciona receita do corte`.

---

### Tarefa 3: Legenda com destaque e oculta durante imagens

**Files:**
- Modify: `esteira/legenda.py`
- Test: `tests/test_legenda.py`

**Interfaces:**
- Consumes: `Cue.destaque` (Tarefa 2).
- Produces:
  - `escrever_ass(cues, caminho)` passa a pintar de amarelo a primeira palavra de cada cue cuja `_chave` é igual à `_chave(cue.destaque)`: `{\c&H00FFFF&}palavra{\c&HFFFFFF&}`. Pontuação colada fica fora da cor.
  - `ocultar_durante(cues: list[Cue], intervalos: list[tuple[float, float]]) -> list[Cue]`: remove cues inteiramente dentro de um intervalo; encurta as que cruzam a borda; uma cue que contém o intervalo inteiro fica só com a parte mais longa.

- [ ] **Step 1: Escrever os testes**

```python
def test_ass_pinta_destaque(tmp_path):
    escrever_ass([Cue(0, 1, ["o Gripen, sueco"], "gripen")], tmp_path / "a.ass")
    assert r"{\c&H00FFFF&}Gripen{\c&HFFFFFF&}," in (tmp_path / "a.ass").read_text("utf-8")

def test_ass_sem_destaque_nao_muda(tmp_path): ...     # texto igual ao comportamento atual
def test_destaque_pinta_so_uma_palavra(tmp_path): ... # "lula e lula" -> uma ocorrência pintada
def test_ocultar_remove_cue_dentro(): assert ocultar_durante([Cue(1, 2, ["a"])], [(0.5, 2.5)]) == []
def test_ocultar_encurta_borda(): assert ocultar_durante([Cue(1, 3, ["a"])], [(2, 4)]) == [Cue(1, 2, ["a"])]
def test_ocultar_cue_que_contem_imagem():
    assert ocultar_durante([Cue(0, 10, ["a"])], [(2, 4)]) == [Cue(4, 10, ["a"])]
```

- [ ] **Step 2: Rodar** `.venv\Scripts\python.exe -m pytest tests/test_legenda.py -v`. Esperado: FAIL nos testes novos.
- [ ] **Step 3: Implementar** as duas mudanças em `legenda.py`.
- [ ] **Step 4: Rodar** `tests/test_legenda.py`. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: destaca palavra e oculta legenda durante imagem`.

---

### Tarefa 4: Ler imagens de imagens.md

**Files:**
- Create: `esteira/imagens.py`
- Test: `tests/test_imagens.py`

**Interfaces:**
- Consumes: `Imagem` (Tarefa 2).
- Produces: `ler_imagens(pasta: Path) -> list[Imagem]`. Lê os títulos `## N. HH:MM:SS a HH:MM:SS — nome` de `imagens.md` (aceita `,mmm` opcional nos tempos) e procura em `imagens/` um arquivo `NN-*` (`.jpg`, `.jpeg`, `.png`, `.webp`). Sugestão sem arquivo é ignorada (não foi aprovada). `licenca` vem da linha `Autor e licença:`. Sem `imagens.md`, retorna `[]`.

- [ ] **Step 1: Escrever os testes**

```python
MD = """## 1. 00:00:18 a 00:00:21 — Gripen
Tipo: foto livre
Autor e licença: FAB, CC BY 2.0

## 2. 00:00:40 a 00:00:43 — Sem arquivo
"""

def test_le_imagens_com_arquivo(tmp_path):
    (tmp_path / "imagens.md").write_text(MD, "utf-8")
    (tmp_path / "imagens").mkdir(); (tmp_path / "imagens" / "01-gripen.jpg").write_bytes(b"x")
    assert ler_imagens(tmp_path) == [Imagem(18.0, 21.0, "imagens/01-gripen.jpg", "FAB, CC BY 2.0")]

def test_sem_imagens_md(tmp_path): assert ler_imagens(tmp_path) == []
def test_tempo_com_milissegundos(tmp_path): ...  # "00:00:18,500 a 00:00:21,000" -> 18.5, 21.0
```

- [ ] **Step 2: Rodar** `.venv\Scripts\python.exe -m pytest tests/test_imagens.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar** `ler_imagens`.
- [ ] **Step 4: Rodar** de novo. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: lê imagens aprovadas de imagens.md`.

---

### Tarefa 5: Render final em passada única

**Files:**
- Modify: `esteira/render.py`, `esteira/midia.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Receita`, `duracao_principal` (Tarefa 2); `escrever_ass`, `ocultar_durante` (Tarefa 3); `ZOOM_IMAGEM` (Tarefa 1).
- Produces:
  - `pico_de_audio(video: Path) -> float` em `midia.py`: `max_volume` em dB do filtro `volumedetect`.
  - `renderizar_final(receita: Receita, video: Path, cartao: Path, pasta: Path, saida: Path, sobreposicao: Path | None = None) -> list[str]` em `render.py`. Retorna alertas (ex.: `"sem música"`, `"áudio perto de saturar: -0.1 dB"` quando o pico passa de -0,5 dB). Lança `ErroMidia` em falha.

Filtro, nesta ordem, reaproveitando `filtro_9x16`, `dividir_em_segmentos` e `_codificar`:
1. Segmentos como hoje, concatenados em `[vprin][aprin]` (sem o encerramento).
2. Cada imagem é uma entrada `-loop 1 -framerate 30 -t <dur> -i <arquivo>`, com `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920`; se `ZOOM_IMAGEM > 1`, aproximação linear até esse fator durante a imagem; `setpts=PTS-STARTPTS+<inicio>/TB`; `overlay=enable='between(t,<inicio>,<fim>)':eof_action=pass`.
3. Legenda: `ocultar_durante(receita.legenda, intervalos das imagens)` gravada em ASS e aplicada com `ass=.legenda_tmp/legenda.ass:fontsdir=.legenda_tmp`, com `cwd=saida.parent`, como faz `queimar_legenda` hoje.
4. Música: entrada `-stream_loop -1 -i <arquivo>`; `atrim=duration=D`, `volume=<volume_db>dB`, `afade` de entrada 0,5 s e de saída 1,5 s no fim de D; `sidechaincompress` com a voz como controle (`threshold=0.05:ratio=4:attack=20:release=300`); `amix=inputs=2:duration=first:normalize=0` com a voz.
5. Concatenação com o encerramento, com a mesma sobreposição de logo de hoje.
6. `_codificar` com duração esperada `duracao_principal + duração do cartão`; depois `pico_de_audio`.

- [ ] **Step 1: Escrever os testes** (reaproveitando `_cenario` e `gerar_video_teste`)

```python
def test_final_sem_imagem_nem_musica(tmp_path): ...       # 1080x1920, duração faixas+cartão, alertas contém "sem música"
def test_imagem_aparece_no_tempo(tmp_path):
    # imagem vermelha 800x600 (horizontal) de 0.5 a 2.5 s; quadro em 1.5 s tem (540, 100) e (540, 1800) vermelhos
def test_legenda_some_durante_imagem(tmp_path): ...        # cue de 0 a 3 s; quadro em 1.5 s sem pixel branco em y≈1530
def test_musica_curta_repete_e_duracao_mantem(tmp_path): ...  # música de 1 s, corte de 3 s: duração ok, áudio presente
def test_caminhos_com_acento_em_imagem_e_musica(tmp_path): ... # arquivos em "Tudo é Política (teste)/imagens/01-ação.png"
def test_falha_nao_deixa_final(tmp_path): ...              # vídeo inexistente -> ErroMidia, sem final.mp4 nem *.tmp.mp4
```

- [ ] **Step 2: Rodar** `.venv\Scripts\python.exe -m pytest tests/test_render.py -v`. Esperado: FAIL nos testes novos.
- [ ] **Step 3: Implementar** `pico_de_audio` e `renderizar_final`.
- [ ] **Step 4: Rodar** `tests/test_render.py`. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: monta vídeo final com imagens, legenda e música`.

---

### Tarefa 6: Preparar e montar o episódio

**Files:**
- Modify: `esteira/cortar.py`, `esteira/cli.py`, `esteira/render.py` (remover `renderizar_sem_legenda` e `queimar_legenda` depois que nada mais usar)
- Create: `esteira/montar.py`
- Test: `tests/test_cortar.py`, `tests/test_montar.py`, `tests/test_render.py` (remover testes das funções removidas)

**Interfaces:**
- Consumes: Tarefas 2 a 5.
- Produces:
  - `preparar_episodio(pasta, numeros=None, forcar=False, nomes=None) -> dict[int, str]` (substitui `cortar_episodio`): para cada corte de `aprovados.json`, valida o trecho, gera `legenda.srt`, `edicoes.md`, pasta `imagens/` e `montagem.json` com faixas, planos de `enquadramento.json`, cues e imagens de `ler_imagens`. Não renderiza. Sem `--forcar`, não sobrescreve `montagem.json` existente (preserva destaques).
  - `atualizar_imagens(pasta_corte: Path) -> int`: troca só o campo `imagens` da receita pelo resultado de `ler_imagens`; retorna a quantidade.
  - `montar_episodio(pasta, numeros=None, forcar=False, cartao=None) -> dict[int, str]` em `montar.py`: para cada corte com `montagem.json`, valida a receita, chama `renderizar_final` para `final.mp4`, grava `registro.json` com `resultado` e `alertas`. Resultados: `"ok"`, `"ok com alertas: ..."` ou `"erro: ..."`. Com `final.mp4` existente e sem `forcar`: `"erro: final.mp4 já existe, use --forcar"`. Um erro não para os outros.
  - CLI: `preparar <pasta> [--numero N] [--forcar]`, `imagens <pasta> [--numero N]`, `montar <pasta> [--numero N] [--forcar]`. Sai o comando `cortar`.

- [ ] **Step 1: Ajustar e escrever os testes**

```python
# test_cortar.py (preparar)
def test_preparar_gera_receita_sem_video(tmp_path): ...   # montagem.json, legenda.srt, edicoes.md; nenhum .mp4
def test_preparar_nao_sobrescreve_receita(tmp_path): ...  # destaque editado sobrevive sem --forcar
def test_preparar_usa_enquadramento_gravado(tmp_path): ...
def test_atualizar_imagens_preserva_destaques(tmp_path): ...

# test_montar.py
def test_montar_gera_final(tmp_path): ...                 # {1: "ok com alertas: sem música"}, final.mp4 e registro.json
def test_receita_invalida_nao_para_os_outros(tmp_path): ...  # corte 1 com imagem inexistente -> "erro: ..."; corte 2 ok
def test_nao_sobrescreve_final_sem_forcar(tmp_path): ...
def test_forcar_com_falha_nao_deixa_final_antigo(tmp_path): ...
```

O auxiliar `preparar` de `test_cortar.py` passa a ser compartilhado via `tests/auxiliares.py` (`preparar_episodio_teste(tmp_path, cortes)`).

- [ ] **Step 2: Rodar** `.venv\Scripts\python.exe -m pytest tests/test_cortar.py tests/test_montar.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar** `preparar_episodio`, `atualizar_imagens`, `montar_episodio` e os comandos. Remover as funções e testes antigos de render.
- [ ] **Step 4: Rodar** a suíte inteira. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: separa preparação e montagem do corte`.

---

### Tarefa 7: Revisão do episódio

**Files:**
- Create: `esteira/revisao.py`
- Modify: `esteira/cli.py`
- Test: `tests/test_revisao.py`

**Interfaces:**
- Consumes: `ler_aprovados`, `pasta_do_corte` (`cortar.py`); `registro.json` (Tarefa 6); `ler_receita`, `Receita.musica`, `Imagem.licenca` (Tarefa 2); `ler_palavras`.
- Produces:
  - `contexto_do_trecho(palavras: list[Palavra], inicio: float, fim: float, n: int = 15) -> tuple[str, str]`: as `n` palavras antes do início e depois do fim.
  - `escrever_revisao(pasta: Path) -> Path`: grava `revisao.md` e retorna o caminho.
  - CLI: `revisao <pasta>`.

Formato de cada bloco:

```markdown
## 1. Título do corte
Vídeo: [final.mp4](01-titulo/final.mp4)
Redes: YouTube, TikTok e Instagram        (ou "YouTube e TikTok")
Publicação sugerida: 2026-11-04 18:00     (ou "sem data")
Antes: "... últimas palavras antes do corte"
Depois: "primeiras palavras depois do corte ..."
Alertas: sem música; imagem 2 sem licença registrada
```

Corte com erro na montagem mostra `Erro: <motivo>` no lugar do vídeo. No fim: `Candidatos descartados: ver [candidatos.md](candidatos.md).`

- [ ] **Step 1: Escrever os testes**

```python
def test_contexto_do_trecho(): ...           # palavras 0..29, trecho 10..20, n=3 -> ("p7 p8 p9", "p21 p22 p23")
def test_revisao_tem_bloco_por_corte(tmp_path): ...   # link, redes conforme instagram, data, Antes/Depois
def test_revisao_mostra_alertas_e_erros(tmp_path): ... # sem música, imagem sem licença, corte com erro
```

- [ ] **Step 2: Rodar** `.venv\Scripts\python.exe -m pytest tests/test_revisao.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implementar** `revisao.py` e o comando.
- [ ] **Step 4: Rodar** a suíte inteira. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: gera revisão do episódio`.

---

### Tarefa 8: Roteiro e regras do canal

**Files:**
- Modify: `docs/operacao.md` (Git da Automacao)
- Modify, com aprovação: `../CLAUDE.md`, `../Contexto/estilo-dos-cortes.md`, `../Contexto/estilo-de-legenda.md`, `../Contexto/estilo-de-imagens.md`, `../Contexto/redes-e-publicacao.md`

- [ ] **Step 1: Reescrever `docs/operacao.md`** com o fluxo sem pausa da seção 3 da spec:
  1. transcrever;
  2. escolher até 8 a 10 cortes e gravar `aprovados.json` com `instagram: true` nos 4 mais fortes (o arquivo guarda os cortes escolhidos pela esteira); registrar descartados e motivo em `candidatos.md`;
  3. `validar`, `planos` e enquadramento, sem pausa;
  4. `preparar`;
  5. marcar destaques em `montagem.json` (no máximo uma palavra por tela, não em todas, só nomes, números e a palavra central);
  6. imagens (manual até a Parte 3) e `imagens`;
  7. `montar`;
  8. textos, calendário (TikTok e Shorts 1 a 2 por dia, Instagram nos horários fixos, tudo antes do próximo episódio) e campo `data` em `aprovados.json`;
  9. `revisao`; o Claude acrescenta aos alertas de cada corte os nomes que podem ter saído errados na legenda (comparando com `glossario.md`) e para.
  Incluir o formato de `aprovacao.json` da seção 6 da spec, gravado depois da resposta do dono do canal, e como corrigir um corte (editar `montagem.json` e `montar --numero N --forcar`).
- [ ] **Step 2: Mostrar ao dono do canal o texto exato** das mudanças da seção 8 da spec em `CLAUDE.md` e nos quatro arquivos de `Contexto/`. Esperar aprovação.
- [ ] **Step 3: Salvar** os textos aprovados.
- [ ] **Step 4: Commit** de `docs/operacao.md`: `docs: atualiza roteiro para montagem automática`. (`Contexto/` e `CLAUDE.md` estão fora do Git.)

---

### Tarefa 9: Teste real com um episódio

Feita com o dono do canal.

- [ ] **Step 1: Escolher o episódio** com o dono do canal (de preferência um que ainda não tenha cortes).
- [ ] **Step 2: Rodar o fluxo de `operacao.md`** do início até `revisao.md`, sem pausas. Medir o tempo total.
- [ ] **Step 3: Comparar visualmente** dois cortes com `Contexto/cortes-de-referencia.md` (quadros com imagem, legenda e destaque).
- [ ] **Step 4: Registrar em `docs/resultados/`**: cortes gerados, aprovados, correções pedidas e tempo. Critérios: pelo menos 6 aprovados sem editor, nenhum muda o sentido da fala, nomes principais corretos.
- [ ] **Step 5: Commit** `docs: registra teste da montagem automática`.
