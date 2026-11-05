# Cortes para o CapCut: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objetivo:** a esteira entrega `corte.mp4` sem imagens, com zoom em quem fala decidido por voz e rosto, e uma pasta `imagens-sugeridas/` com fotos prontas e `guia.md` para o dono do canal montar no CapCut.

**Arquitetura:** arquivos internos de cada corte vão para `trabalho/`. A inserção de imagens sai do render. Quatro módulos novos (`vozes`, `rostos`, `pessoas`, `enquadrar`) geram o `enquadramento.json`. A lógica de `enquadrar` é pura e recebe vozes e rostos como dados. O fluxo de imagens troca `lista`/`baixar` por `resumo`/`sugerir`.

**Tecnologias:** Python 3.12, pytest, ffmpeg (`bin/`), Pillow, pyannote.audio 3.x + torch CUDA, opencv-python (YuNet e SFace).

**Spec:** `docs/superpowers/specs/2026-11-05-cortes-para-capcut-design.md`

## Restrições globais

- Responder e escrever docs em português do Brasil; nomes de código em português, como o código atual.
- Nunca gravar em `1 - Programas/`; toda escrita passa por `garantir_escrita` (`2 - Cortes/` e `Automacao/`).
- Token do Hugging Face só por `HF_TOKEN` (variável de ambiente); nunca em arquivo, log ou mensagem.
- Todo download (pacotes, modelos, fotos) só depois de confirmação do dono do canal com nome, origem e tamanho.
- A esteira nunca grava, apaga ou altera nada dentro de `video-final/`.
- Zoom em níveis 1,0 / 1,35 / 1,7 / 2,0; meta do rosto 28% da altura da faixa; nunca acima de 2,0.
- Turno de voz < 2 s não divide; nenhum trecho de enquadramento < 2 s; fala sobreposta > 1 s gera alerta.
- Fotos: Wikimedia Commons, licenças CC0, domínio público, CC BY, CC BY-SA; 1 a 3 por momento; saída 1080x1920.
- Nome dos arquivos sugeridos: `MMSS-nome-K.jpg` (foto) e `MMSS-nome.png` (notícia), `MMSS` = início no `corte.mp4`.
- Rodar comandos de `Automacao/` com `.venv\Scripts\python.exe`. A suíte completa leva mais de 2 min: rodar em segundo plano.

## Foco da revisão

1. Voz que nunca aparece sozinha em close (ex.: apresentador sempre de costas): fica sem pessoa, os trechos dela viram "fora da tela" com alerta, sem erro. Teste na Tarefa 6.
2. Rosto falso ou pequeno (logo do canal no fundo, pessoa ao fundo): YuNet com score ≥ 0,8 e rosto ≥ 6% da altura do quadro; menores são ignorados. Teste na Tarefa 5.
3. Rodar `planos` de novo não sobrescreve `enquadramento.json` nem `pessoas.json` editados à mão sem `--forcar`. Teste na Tarefa 7.
4. `escolhas` fora da faixa das candidatas, repetidas ou mais de 3: erro claro do momento, os outros cortes seguem. Teste na Tarefa 8.
5. `montar --forcar` com vídeo em `video-final/`: o vídeo continua intacto. Teste na Tarefa 2.

---

### Tarefa 0: Registrar a renomeação de pastas pendente

O repositório tem mudanças sem commit (`caminhos.py`, `tests/test_caminhos.py`, `docs/operacao.md`, spec de 2026-11-01, `musicas/proposta.md`, `assets/encerramento.png`) da troca para `1 - Programas/`, `2 - Cortes/` e `3 - Identidade/`. Elas não são deste plano, mas tudo depende delas.

- [ ] **Passo 1:** mostrar `git status` e `git diff --stat` ao dono do canal e pedir confirmação para o commit.
- [ ] **Passo 2:** rodar a suíte. Esperado: todos passando.
- [ ] **Passo 3:** commit `chore: pastas numeradas do canal` com esses arquivos.

---

### Tarefa 1: Pasta `trabalho/` no corte

**Arquivos:**
- Modificar: `esteira/cortar.py`, `esteira/cli.py` (`_planos`, `_musica`), `esteira/fluxo_imagens.py`, `esteira/revisao.py`, `esteira/montar.py`
- Testes: `tests/test_cortar.py`, `tests/test_cli.py`, `tests/test_fluxo_imagens.py`, `tests/test_revisao.py`, `tests/test_montar.py`

**Interfaces:**
- Produz: em `esteira/cortar.py`, `TRABALHO = "trabalho"`, `IMAGENS_SUGERIDAS = "imagens-sugeridas"`, `VIDEO_FINAL = "video-final"`, `CORTE_MP4 = "corte.mp4"` e `pasta_de_trabalho(destino: Path) -> Path` (cria e devolve `destino / "trabalho"`).
- Regra: as funções que recebem `pasta` (`gravar_planos`, `ler_planos`, `gravar_receita`, `ler_receita`, `ler_pedidos`, `gravar_pedidos`, `atualizar_musica`, `registrar`) continuam iguais. Quem chama passa `pasta_de_trabalho(destino)`. `legenda.srt`, `edicoes.md`, `registro.json`, `montagem.json`, `enquadramento.json`, `pedidos.json`, `planos.jpg` e `candidatas/` ficam em `trabalho/`. `post.md` fica na pasta do corte.

- [ ] **Passo 1: testes que falham**
  - `test_preparar_grava_em_trabalho`: depois de `preparar_episodio`, existem `trabalho/montagem.json`, `trabalho/legenda.srt`, `trabalho/edicoes.md` e `trabalho/registro.json`, e não existe `montagem.json` na raiz do corte.
  - `test_planos_grava_em_trabalho` (cli): `trabalho/enquadramento.json` e `trabalho/planos.jpg`.
  - `test_buscar_grava_candidatas_em_trabalho`: `trabalho/candidatas/01-1.jpg`, lendo `trabalho/pedidos.json`.
  - Ajustar os testes atuais que usam esses caminhos na raiz do corte.
- [ ] **Passo 2:** rodar `pytest tests/test_cortar.py tests/test_cli.py tests/test_fluxo_imagens.py tests/test_revisao.py tests/test_montar.py -q`. Esperado: FALHA nos novos.
- [ ] **Passo 3:** trocar os chamadores para `pasta_de_trabalho(destino)`. Tirar `(destino / "imagens").mkdir` de `_preparar_um`.
- [ ] **Passo 4:** rodar a suíte em segundo plano. Esperado: tudo passando.
- [ ] **Passo 5:** commit `refactor: arquivos internos do corte em trabalho/`.

---

### Tarefa 2: Render sem imagens e `corte.mp4`

**Arquivos:**
- Modificar: `esteira/render.py` (sai `_tela_cheia`, `_filtro_imagem`, `ZOOM_IMAGEM`, `PROPORCAO_TELA_CHEIA` e o laço de imagens; legenda sem `ocultar_durante`), `esteira/receita.py` (sai `Imagem`, o campo `imagens` e as validações de imagem; `ler_receita` ignora a chave `"imagens"` antiga), `esteira/legenda.py` (sai `ocultar_durante`), `esteira/montar.py`, `esteira/cortar.py` (sai `atualizar_imagens` e o uso de `ler_imagens`), `esteira/cli.py` (sai a ação `imagens atualizar`)
- Apagar: o conteúdo atual de `esteira/imagens.py` (`ler_imagens`, `secoes_sem_arquivo`) e os testes dele; o arquivo volta com outro conteúdo na Tarefa 8
- Testes: `tests/test_render.py`, `tests/test_receita.py`, `tests/test_montar.py`, `tests/test_legenda.py`, `tests/test_imagens.py`

**Interfaces:**
- Produz: `montar_episodio(...)` grava `destino / CORTE_MP4` e cria `destino / IMAGENS_SUGERIDAS` e `destino / VIDEO_FINAL` vazias (`mkdir(exist_ok=True)`). Assinatura de `renderizar_final` mantida.

- [ ] **Passo 1: testes que falham**
  - `test_montar_gera_corte_mp4`: existe `corte.mp4`, não existe `final.mp4`, e existem as pastas `imagens-sugeridas/` e `video-final/`.
  - `test_montar_nao_sobrescreve_corte_sem_forcar`: mensagem `erro: corte.mp4 já existe, use --forcar`.
  - `test_montar_forcar_preserva_video_final` (foco 5): com `video-final/meu.mp4` de bytes conhecidos, `montar --forcar` mantém o arquivo byte a byte.
  - `test_ler_receita_ignora_imagens_antigas`: um `montagem.json` com `"imagens": [...]` é lido sem erro.
  - Tirar os testes de imagem de `test_render.py`, `test_receita.py` e `test_legenda.py`.
- [ ] **Passo 2:** rodar os arquivos de teste acima. Esperado: FALHA nos novos.
- [ ] **Passo 3:** implementar as remoções e a troca de `final.mp4` por `CORTE_MP4` em `montar.py` e `revisao.py`.
- [ ] **Passo 4:** rodar a suíte em segundo plano. Esperado: tudo passando.
- [ ] **Passo 5:** commit `feat: corte.mp4 sem imagens, pastas imagens-sugeridas e video-final`.

---

### Tarefa 3: Enquadramento por quem fala (lógica pura)

**Arquivos:**
- Criar: `esteira/enquadrar.py`
- Teste: `tests/test_enquadrar.py`

**Interfaces:**
- Consome: `Plano` de `esteira/planos.py`.
- Produz:
  ```python
  NIVEIS = (1.0, 1.35, 1.7, 2.0)
  META_ROSTO = 0.28
  TURNO_MINIMO = 2.0
  TRECHO_MINIMO = 2.0
  SOBREPOSICAO_MAXIMA = 1.0

  @dataclass
  class TrechoVoz:   # inicio, fim em segundos do episódio
      inicio: float; fim: float; voz: str

  @dataclass
  class Rosto:       # coordenadas de 0 a 1 no quadro original
      pessoa: str; x: float; y: float; largura: float; altura: float

  @dataclass
  class Cena:        # plano de câmera com rostos médios visíveis
      inicio: float; fim: float; rostos: list[Rosto]

  def nivel_zoom(altura_rosto: float) -> float
  def enquadrar_rosto(rosto: Rosto) -> Plano   # inicio/fim preenchidos por quem chama
  def falante_em(vozes: list[TrechoVoz], inicio: float, fim: float) -> str | None
  def enquadrar_cena(cena: Cena, vozes: list[TrechoVoz], ligacao: dict[str, str]) -> tuple[list[Plano], list[str]]
  ```

Regras (da spec 4.4 e 4.5):
- `nivel_zoom`: `z = META_ROSTO / altura_rosto`, nível mais próximo de `NIVEIS`, limitado a 2,0; `altura_rosto <= 0` dá 1,0.
- `enquadrar_rosto`: `x = rosto.x`; olhos em `rosto.y - rosto.altura * 0.1`, onde `y` é o centro da caixa; `y = olhos + 1 / (6 * z)`, que põe os olhos no terço superior do recorte. `recorte()` já limita à imagem.
- `falante_em`: a voz com mais tempo dentro do intervalo; `None` se ninguém fala.
- `enquadrar_cena`, nesta ordem:
  1. Pega as vozes que tocam a cena e descarta turnos com menos de `TURNO_MINIMO`.
  2. Divide a cena nos pontos de troca de voz.
  3. Junta trechos com menos de `TRECHO_MINIMO` ao vizinho anterior (o primeiro, ao seguinte).
  4. Para cada trecho, escolhe o enquadramento:
     - a pessoa ligada à voz está em `cena.rostos`: `enquadrar_rosto`;
     - senão, com 1 rosto: esse rosto;
     - com 2 ou mais rostos: zoom 1,0, `x` na média dos centros, `y` 0,5;
     - com 0 rostos: `Plano` padrão e o alerta `"MM:SS sem rosto"`.
  5. Duas vozes ao mesmo tempo por mais de `SOBREPOSICAO_MAXIMA`: o trecho repete o enquadramento anterior e gera o alerta `"MM:SS fala sobreposta"`.
  6. Uma voz sem ligação gera o alerta `"MM:SS voz Vn sem pessoa"`.
  - Os tempos dos alertas são relativos ao início da cena.

- [ ] **Passo 1: testes que falham**
  - `test_nivel_zoom`: `nivel_zoom(0.28) == 1.0`, `nivel_zoom(0.20) == 1.35`, `nivel_zoom(0.165) == 1.7`, `nivel_zoom(0.10) == 2.0`, `nivel_zoom(0.0) == 1.0`.
  - `test_close_nao_da_zoom`: rosto com `altura=0.45` dá zoom 1,0.
  - `test_divide_na_troca_de_voz`: cena de 0 a 20 s, V1 de 0 a 8, V2 de 8 a 20, ligação V1→P1 e V2→P2, dois rostos: dois planos com troca em 8,0, cada um centrado no seu rosto (`x` igual ao do rosto).
  - `test_turno_curto_nao_divide`: V2 de 8,0 a 9,5 no meio de V1 dá um plano só.
  - `test_trecho_minimo`: troca de V1 para V2 em 19,0 numa cena de 20 s: nenhum plano com menos de 2 s.
  - `test_falante_fora_da_tela_um_rosto`: fala V2 (P2), só P1 visível: plano no P1.
  - `test_falante_fora_da_tela_varios_rostos`: fala V3 (P3), P1 e P2 visíveis: zoom 1,0, `x` na média.
  - `test_sem_rosto_alerta`: cena sem rostos: `Plano` padrão e alerta contendo `"sem rosto"`.
  - `test_fala_sobreposta`: V1 e V2 juntas por 1,5 s: mantém o plano anterior e alerta `"fala sobreposta"`.
  - `test_voz_sem_pessoa` (foco 1): V3 sem ligação, P1 visível: plano no P1 e alerta `"voz V3 sem pessoa"`.
- [ ] **Passo 2:** rodar `pytest tests/test_enquadrar.py -v`. Esperado: FALHA (módulo inexistente).
- [ ] **Passo 3:** implementar `esteira/enquadrar.py`.
- [ ] **Passo 4:** rodar `pytest tests/test_enquadrar.py -v`. Esperado: PASSA.
- [ ] **Passo 5:** commit `feat: enquadramento por quem fala`.

---

### Tarefa 4: Vozes (diarização)

**Arquivos:**
- Criar: `esteira/vozes.py`
- Modificar: `esteira/cli.py` (comando `vozes`), `pyproject.toml` (extra `vozes = ["torch", "pyannote.audio>=3.1,<4"]`, para quem não diariza não precisar instalar)
- Teste: `tests/test_vozes.py`

**Interfaces:**
- Consome: `TrechoVoz` da Tarefa 3.
- Produz:
  ```python
  MODELO = "pyannote/speaker-diarization-3.1"
  class ErroVozes(Exception): ...
  def criar_pipeline() -> Callable[[Path, int], list[tuple[float, float, str]]]  # lê HF_TOKEN; ErroVozes se faltar
  def separar_vozes(video: Path, pasta: Path, pessoas: int, criar=criar_pipeline, forcar: bool = False) -> list[TrechoVoz]
  def ler_vozes(pasta: Path) -> list[TrechoVoz]   # ErroVozes se faltar transcricao/vozes.json
  ```
- `separar_vozes`:
  - extrai o áudio para um WAV mono de 16 kHz temporário com `executar_ffmpeg`;
  - chama a pipeline com `num_speakers=pessoas`;
  - renomeia os rótulos para `V1`, `V2`, ... em ordem de primeira aparição;
  - grava `transcricao/vozes.json` (`{"trechos": [...]}`) de forma atômica (`.tmp` + `replace`), como em `transcrever._gravar`;
  - com o arquivo já existente e sem `forcar`, dá `FileExistsError`.
- CLI: `vozes <video> <pasta> --pessoas 3 [--forcar]`. Imprime `N vozes, M trechos`. Sem `HF_TOKEN`, imprime a mensagem e devolve 1:
  `HF_TOKEN não definido: crie o token no Hugging Face, aceite os termos de pyannote/speaker-diarization-3.1 e defina a variável de ambiente.`

- [ ] **Passo 1: testes que falham**
  - `test_separar_vozes_grava_e_renomeia`: com uma pipeline falsa que devolve `[(0,5,"SPEAKER_01"),(5,9,"SPEAKER_00")]`, o resultado tem as vozes `V1` e `V2` nessa ordem e o `vozes.json` existe.
  - `test_nao_sobrescreve_sem_forcar`.
  - `test_sem_token` com `monkeypatch.delenv("HF_TOKEN")`: `criar_pipeline()` dá `ErroVozes`, e a mensagem não contém nenhum valor de token.
  - `test_ler_vozes_sem_arquivo`: dá `ErroVozes`.
  - `test_cli_vozes_sem_token_retorna_1`.
- [ ] **Passo 2:** rodar `pytest tests/test_vozes.py -v`. Esperado: FALHA.
- [ ] **Passo 3:** implementar. Fazer `import pyannote` só dentro de `criar_pipeline`, para que os testes não precisem do pacote. Chamar `_registrar_dlls_nvidia` de `transcrever.py`.
- [ ] **Passo 4:** rodar `pytest tests/test_vozes.py -v`. Esperado: PASSA.
- [ ] **Passo 5: instalação real.** Informar ao dono do canal os pacotes (`torch` com CUDA 12, de download.pytorch.org, cerca de 2,5 GB; `pyannote.audio`, do PyPI, cerca de 50 MB; modelo `pyannote/speaker-diarization-3.1`, do Hugging Face, cerca de 30 MB). Só instalar com o "sim". Depois, pedir que ele crie o token e defina `HF_TOKEN`. O token é dele: não pedir nem ver o valor.
- [ ] **Passo 6:** rodar `vozes` no vídeo do Entre Assuntos #03 numa pasta de teste. Esperado: 3 vozes e `vozes.json` gravado.
- [ ] **Passo 7:** commit `feat: comando vozes (diarização)`.

---

### Tarefa 5: Rostos

**Arquivos:**
- Criar: `esteira/rostos.py`, `modelos/LEIA.md` (de onde vêm os modelos, com links e licenças)
- Modificar: `pyproject.toml` (`opencv-python`), `.gitignore` (`modelos/*.onnx`)
- Teste: `tests/test_rostos.py`

**Interfaces:**
- Consome: `Rosto`, `Cena` da Tarefa 3; `detectar_cortes` de `planos.py`.
- Produz:
  ```python
  PASSO = 0.5
  SCORE_MINIMO = 0.8
  ALTURA_MINIMA = 0.06       # fração da altura do quadro
  LIMIAR_MESMA_PESSOA = 0.363  # cosseno SFace
  MODELOS = AUTOMACAO / "modelos"   # face_detection_yunet_2023mar.onnx, face_recognition_sface_2021dec.onnx

  @dataclass
  class Deteccao:
      tempo: float; x: float; y: float; largura: float; altura: float; assinatura: list[float]

  def detectar(video: Path, inicio: float, fim: float, detector=None) -> list[Deteccao]
  def filtrar(deteccoes_brutas: list[tuple[float, tuple, float, list[float]]], largura: int, altura: int) -> list[Deteccao]
  def agrupar(deteccoes: list[Deteccao], conhecidas: dict[str, list[float]]) -> tuple[list[str], dict[str, list[float]]]
  def cenas_com_rostos(deteccoes: list[Deteccao], pessoas: list[str], limites: list[float]) -> list[Cena]
  ```
- `detectar`: lê quadros a cada `PASSO` com ffmpeg (para um diretório temporário, 640 px de largura), roda YuNet e SFace e chama `filtrar`. O `detector` injetável recebe um quadro e devolve detecções brutas.
- `filtrar`: descarta score < `SCORE_MINIMO` e altura < `ALTURA_MINIMA`; normaliza as coordenadas de 0 a 1; `x`, `y` = centro da caixa.
- `agrupar`: atribui cada detecção à pessoa conhecida mais parecida, com cosseno ≥ limiar; se nenhuma serve, cria uma pessoa nova `P{n}`. A assinatura da pessoa é a média das detecções atribuídas. Devolve a pessoa de cada detecção e o dicionário atualizado.
- `cenas_com_rostos`: os limites são os cortes de cena. Por cena e por pessoa, um `Rosto` com a média das caixas, só se a pessoa aparece em pelo menos 50% das amostras da cena.

- [ ] **Passo 1: testes que falham**
  - `test_filtrar_descarta_fraco_e_pequeno` (foco 2): score 0,7 e altura 0,04 ficam fora; score 0,9 e altura 0,2 ficam.
  - `test_filtrar_normaliza_centro`: caixa `(100, 50, 200, 300)` num quadro de 1000x1000 dá `x=0.2`, `y=0.2`, `largura=0.2`, `altura=0.3`.
  - `test_agrupar_mesma_pessoa`: duas assinaturas iguais dão a mesma pessoa; uma ortogonal dá pessoa nova.
  - `test_agrupar_usa_conhecidas`: uma assinatura parecida com a de `P2` em `conhecidas` recebe `P2`.
  - `test_cenas_presenca_minima`: pessoa em 1 de 4 amostras da cena não entra em `rostos`.
- [ ] **Passo 2:** rodar `pytest tests/test_rostos.py -v`. Esperado: FALHA.
- [ ] **Passo 3:** implementar. Fazer `import cv2` só dentro de `detectar`, quando `detector` é `None`.
- [ ] **Passo 4:** rodar `pytest tests/test_rostos.py -v`. Esperado: PASSA.
- [ ] **Passo 5: download.** Informar ao dono do canal `opencv-python` (PyPI, cerca de 40 MB) e os dois `.onnx` (github.com/opencv/opencv_zoo, cerca de 0,3 MB e 37 MB). Só baixar com o "sim". Os modelos vão em `modelos/`.
- [ ] **Passo 6:** commit `feat: detecção e reconhecimento de rostos`.

---

### Tarefa 6: Ligar voz e pessoa

**Arquivos:**
- Criar: `esteira/pessoas.py`
- Teste: `tests/test_pessoas.py`

**Interfaces:**
- Consome: `TrechoVoz`, `Cena` (Tarefas 3 e 5).
- Produz:
  ```python
  ARQUIVO = "pessoas.json"   # em transcricao/
  def ligar(vozes: list[TrechoVoz], cenas: list[Cena]) -> dict[str, str]
  def gravar_pessoas(pasta: Path, ligacao: dict[str, str], assinaturas: dict[str, list[float]], nomes: dict[str, str]) -> None
  def ler_pessoas(pasta: Path) -> tuple[dict[str, str], dict[str, list[float]], dict[str, str]] | None
  def folha_pessoas(video: Path, amostras: dict[str, tuple[float, Rosto]], ligacao: dict[str, str], tempo_de_fala: dict[str, float], nomes: dict[str, str], saida: Path) -> Path
  ```
- `ligar`: só usa cenas com exatamente 1 rosto. Para cada voz, soma o tempo que ela fala em cada uma dessas cenas, por pessoa visível. A voz fica com a pessoa de maior soma. Duas vozes não ficam com a mesma pessoa: vence a de maior soma, e a outra fica com a próxima pessoa livre ou sem ligação. Voz sem nenhum close fica fora do dicionário.
- `pessoas.json`: `{"ligacao": {"V1": "P2"}, "assinaturas": {"P2": [...]}, "nomes": {"P2": ""}}`. Os nomes são preenchidos pelo Claude ao conferir a folha.
- `folha_pessoas`: uma célula por pessoa, com um recorte do rosto (até 640 px, em arquivo temporário), `P2 = V1 · Nome · 312 s de fala`.

- [ ] **Passo 1: testes que falham**
  - `test_liga_pelo_close`: P1 sozinho de 0 a 10 s com V2 falando, e P2 sozinho de 10 a 20 s com V1: `{"V2": "P1", "V1": "P2"}`.
  - `test_voz_sem_close_fica_fora` (foco 1): V3 só fala em cenas com 2 rostos e não está no resultado.
  - `test_nao_repete_pessoa`: V1 e V2 com a maior soma em P1: só uma fica com P1.
  - `test_gravar_e_ler_pessoas` (ida e volta).
- [ ] **Passo 2:** rodar `pytest tests/test_pessoas.py -v`. Esperado: FALHA.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar `pytest tests/test_pessoas.py -v`. Esperado: PASSA.
- [ ] **Passo 5:** commit `feat: ligação entre voz e pessoa`.

---

### Tarefa 7: Comando `planos` automático e folha nova

**Arquivos:**
- Modificar: `esteira/cli.py` (`_planos`), `esteira/planos.py` (`gerar_folha`)
- Criar: `esteira/fluxo_planos.py` (orquestração, para não inchar a CLI)
- Testes: `tests/test_fluxo_planos.py`, `tests/test_planos.py`, `tests/test_cli.py`

**Interfaces:**
- Consome: `ler_vozes`, `detectar`, `agrupar`, `cenas_com_rostos`, `ligar`, `gravar_pessoas`, `ler_pessoas`, `folha_pessoas`, `enquadrar_cena`, `detectar_cortes`, `pasta_de_trabalho`.
- Produz:
  ```python
  def planejar_episodio(pasta: Path, numeros: set[int] | None, forcar: bool = False, detectar=rostos.detectar) -> dict[int, str]
  def gerar_folha(video: Path, planos: list[Plano], saida: Path, rotulos: list[str] | None = None) -> Path
  ```
- `planejar_episodio`:
  1. `ler_vozes` (com `ErroVozes`, devolve `{0: "erro: ..."}`, e a CLI devolve 1).
  2. Para cada corte, detecta as cenas (`detectar_cortes`) e os rostos.
  3. Agrupa com as assinaturas de `pessoas.json`, se existir.
  4. Liga as vozes. Com `pessoas.json` existente e sem `forcar`, mantém a ligação e os nomes dele e só acrescenta pessoas novas.
  5. Grava `pessoas.json` e `transcricao/pessoas.jpg`.
  6. Para cada corte sem `trabalho/enquadramento.json` (ou com `forcar`), chama `enquadrar_cena` por cena, grava os planos e os alertas em `trabalho/alertas-planos.json` (lista de strings).
  7. Gera `planos.jpg` com rótulos `"{n} {Nome ou Pn} · {primeiras 6 palavras}"` e uma caixa no rosto escolhido.
  - Retorno por corte: `"ok"`, `"ok com alertas: ..."` ou `"mantido (já existe)"`.
- `preparar` passa a juntar `alertas-planos.json` aos alertas do `registro.json`.

- [ ] **Passo 1: testes que falham** (com `detectar` falso e vozes fixas)
  - `test_planejar_grava_enquadramento_e_pessoas`.
  - `test_planejar_nao_sobrescreve_sem_forcar` (foco 3): um `enquadramento.json` editado continua igual e o resultado é `"mantido (já existe)"`.
  - `test_planejar_preserva_nomes_de_pessoas` (foco 3): o nome `"Arthur"` gravado em `pessoas.json` continua depois de rodar de novo.
  - `test_planejar_sem_vozes_para`: sem `vozes.json`, erro e nenhum `enquadramento.json` criado.
  - `test_preparar_leva_alertas_de_planos`.
  - `test_folha_com_rotulos`: gera o JPEG sem erro com rótulos.
- [ ] **Passo 2:** rodar `pytest tests/test_fluxo_planos.py tests/test_planos.py tests/test_cli.py -q`. Esperado: FALHA nos novos.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar a suíte em segundo plano. Esperado: tudo passando.
- [ ] **Passo 5:** commit `feat: planos automáticos por voz e rosto`.

---

### Tarefa 8: Imagens sugeridas

**Arquivos:**
- Criar: `esteira/imagens.py` (preparo 1080x1920)
- Modificar: `esteira/pedidos.py` (`escolhas: list[int]` no lugar de `escolha`; sai `numero`; `url` e `bytes` viram listas paralelas a `escolhas`), `esteira/fluxo_imagens.py` (sai `listar_episodio`, `baixar_episodio`, `lista-imagens.*`, `prompts-chatgpt.md`, `ia-entrada`, `.origens.json`, `imagens.md`; entra `resumir_episodio`, `sugerir_episodio`), `esteira/cli.py` (`imagens {buscar,resumo,sugerir}`)
- Apagar: `esteira/ingestao.py` e `tests/test_ingestao.py` (encaixe das imagens de IA, que deixa de existir)
- Testes: `tests/test_imagens.py`, `tests/test_pedidos.py`, `tests/test_fluxo_imagens.py`, `tests/test_cli.py`

**Interfaces:**
- Consome: `buscar_candidatas`, `url_final`, `tamanho` (wikimedia), `baixar_url` (rede), `gerar_cartao` (cartao), `slug` (episodio), `pasta_de_trabalho`, `IMAGENS_SUGERIDAS`.
- Produz:
  ```python
  # imagens.py
  PROPORCAO_TELA_CHEIA = 1.5
  def preparar_foto(origem: Path, saida: Path) -> Path   # 1080x1920 JPEG qualidade 90
  def prefixo_tempo(segundos: float) -> str             # 72.4 -> "0112"
  # fluxo_imagens.py
  def resumir_episodio(pasta: Path, numeros: set[int] | None, consultar=..., medir=wikimedia.tamanho) -> tuple[int, int, dict[int, str]]  # (fotos, bytes, resultados)
  def sugerir_episodio(pasta: Path, numeros: set[int] | None, pessoas: list[str], consultar=..., baixar=rede.baixar_url) -> dict[int, str]
  def escrever_guia(destino: Path, momentos: list[Momento]) -> Path
  ```
- `preparar_foto`:
  - foto vertical (altura/largura ≥ 1,5): cobre 1080x1920 com corte central;
  - foto horizontal ou quadrada: fundo com a foto cobrindo 1080x1920 e `GaussianBlur(40)`, e a foto a 1080 de largura centralizada na vertical;
  - converte para RGB.
- `resumir_episodio`: valida os pedidos (`validar_pedidos` mais as regras de `escolhas` abaixo), resolve `url_final` de cada escolha e soma os bytes. Grava `url`/`bytes` em `pedidos.json`. Não baixa nada. A CLI imprime `N fotos, X MB, origem Wikimedia Commons` e os erros por corte.
- `sugerir_episodio`:
  - só roda em corte com `url` resolvida (senão `erro: rode imagens resumo`);
  - baixa as fotos para um diretório temporário, chama `preparar_foto` e grava `imagens-sugeridas/{MMSS}-{slug(nome)}-{K}.jpg`;
  - notícia: `gerar_cartao` para `{MMSS}-{slug(nome)}.png`;
  - gera o `guia.md`;
  - limpa antes só os arquivos `*.jpg`/`*.png` que ela mesma gerou em `imagens-sugeridas/`, listados em `trabalho/sugeridas.json`;
  - foto que falha vira `Sem imagem: motivo` no guia e alerta, e os outros momentos seguem.
- Validação de `escolhas`: de 1 a 3 itens, sem repetição, cada um entre 1 e `len(candidatas)`; foto não descartada sem `escolhas` é erro. A mensagem é `momento N: escolhas inválidas`.
- `guia.md`:
  - topo fixo com os lembretes: 2 a 5 s na tela, corte seco, zoom lento de cerca de 8%, a imagem cobre a legenda, e "Se usar imagem de IA, avise na publicação";
  - depois, os blocos no formato da spec 5.4, com tempos `M:SS`.

- [ ] **Passo 1: testes que falham**
  - `test_preparar_foto_vertical`: 600x1200 dá 1080x1920.
  - `test_preparar_foto_horizontal_sem_cortar`: 1600x900 com borda vermelha. A saída é 1080x1920, e a faixa central de altura 607 (1080·900/1600) mantém a borda vermelha nas colunas 0 e 1079.
  - `test_prefixo_tempo`: `prefixo_tempo(72.4) == "0112"` e `prefixo_tempo(5) == "0005"`.
  - `test_escolhas_invalidas` (foco 4): `[0]`, `[1, 1]`, `[1, 2, 3, 4]` e `[7]` com 6 candidatas dão erro; `[2, 1]` passa.
  - `test_resumo_nao_baixa`: o `baixar` falso nunca é chamado e o total de bytes é a soma.
  - `test_sugerir_gera_arquivos_e_guia`: um momento de foto com `escolhas=[2,1]` em 12,4 s gera `0012-yas-marina-1.jpg` (a candidata 2) e `-2.jpg`; um de notícia gera `.png`; um de IA não gera arquivo e o guia tem o `Prompt`.
  - `test_sugerir_falha_isolada`: um download que dá erro gera `Sem imagem:` e os outros arquivos existem.
  - `test_sugerir_nao_apaga_arquivo_do_dono`: `imagens-sugeridas/minha.png`, que não está em `sugeridas.json`, continua.
  - Tirar os testes de `lista`/`baixar`.
- [ ] **Passo 2:** rodar os arquivos de teste acima. Esperado: FALHA nos novos.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar a suíte em segundo plano. Esperado: tudo passando.
- [ ] **Passo 5:** commit `feat: imagens sugeridas e guia para o CapCut`.

---

### Tarefa 9: Revisão nova

**Arquivos:**
- Modificar: `esteira/revisao.py`
- Teste: `tests/test_revisao.py`

**Interfaces:**
- Consome: `CORTE_MP4`, `IMAGENS_SUGERIDAS`, `VIDEO_FINAL`, `pasta_de_trabalho`.
- O bloco de cada corte passa a ter estas linhas:
  - `Vídeo: [corte.mp4](NN-x/corte.mp4)`
  - `Guia de imagens: [guia.md](NN-x/imagens-sugeridas/guia.md)` ou `Guia de imagens: não gerado`
  - Redes, Publicação sugerida, Música, Antes, Depois, como hoje
  - `Vídeo final: vazio` ou `Vídeo final: <nome do arquivo>`
  - `Alertas: ...`, com os alertas do registro, que já incluem os dos planos
- Saem os alertas de imagem.

- [ ] **Passo 1: testes que falham**
  - `test_revisao_mostra_corte_e_guia`.
  - `test_revisao_video_final_vazio_e_preenchido`.
  - `test_revisao_corte_nao_montado`: sem `corte.mp4`, dá `Erro: corte não montado`.
- [ ] **Passo 2:** rodar `pytest tests/test_revisao.py -v`. Esperado: FALHA.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar `pytest tests/test_revisao.py -v`. Esperado: PASSA.
- [ ] **Passo 5:** commit `feat: revisão com corte.mp4, guia e vídeo final`.

---

### Tarefa 10: Roteiro e regras do canal

**Arquivos:**
- Modificar: `docs/operacao.md`, `../Contexto/estilo-dos-cortes.md`, `../Contexto/estilo-de-imagens.md`

- [ ] **Passo 1:** reescrever o `operacao.md` com as etapas 1 a 10 da spec, seção 6:
  - os comandos exatos;
  - a única pausa (confirmação do download das fotos);
  - a conferência de `pessoas.jpg` e `planos.jpg`;
  - como corrigir: editar `trabalho/enquadramento.json` e rodar `montar --numero N --forcar`, perguntando antes;
  - `post.md` sem o aviso de IA e sem créditos de fotos, que ficam para a publicação;
  - nada de `aprovacao.json`.
  - Manter a seção "Biblioteca de música".
- [ ] **Passo 2:** escrever o texto proposto para os dois arquivos de `Contexto/` e mostrar ao dono do canal:
  - em `estilo-dos-cortes.md`, a regra do zoom (níveis, meta de 28%, sem "1,35 no convidado", troca seca, mínimo de 2 s), a entrega em `corte.mp4` e o vídeo final em `video-final/`;
  - em `estilo-de-imagens.md`, as imagens inseridas pelo dono do canal no CapCut a partir de `imagens-sugeridas/`, saindo as frases "A esteira insere as imagens" e "ficam em `imagens/`".
  - Salvar só com aprovação.
- [ ] **Passo 3:** commit `docs: roteiro para o fluxo com CapCut`. `Contexto/` fica fora do repositório `Automacao`: a alteração lá é só salva, sem commit.

---

### Tarefa 11: Teste real no Entre Assuntos #03

**Arquivos:**
- Criar: `docs/resultados/2026-teste-capcut-f1.md`

- [ ] **Passo 1:** criar `2 - Cortes/Entre Assuntos 03 - Arthur Cerqueira (teste capcut)/` com `episodio.json`, `transcricao/` e `aprovados.json` copiados da pasta atual. A pasta atual não é tocada.
- [ ] **Passo 2:** rodar `vozes` (`--pessoas 3`), `validar`, `planos`; conferir `pessoas.jpg`, preencher os nomes e conferir cada `planos.jpg`.
- [ ] **Passo 3:** rodar `preparar` e `montar`. Esperado: 10 `corte.mp4`, todos `ok` ou `ok com alertas`.
- [ ] **Passo 4:** reaproveitar os `pedidos.json` atuais, convertendo `escolha` em `escolhas` e acrescentando até 2 alternativas. Rodar `imagens resumo`, pedir a confirmação do download e rodar `imagens sugerir`.
- [ ] **Passo 5:** rodar `revisao`. Registrar no resultado:
  - os tempos de cada comando;
  - os alertas;
  - as correções feitas à mão no `enquadramento.json`;
  - o zoom do corte 01 comparado com o atual.
- [ ] **Passo 6:** o dono do canal compara os zooms e testa um corte no CapCut. Anotar o que ele disser. Um ajuste da meta de 28% só vira regra com aprovação.
- [ ] **Passo 7:** commit `docs: resultado do teste do fluxo com CapCut`.
