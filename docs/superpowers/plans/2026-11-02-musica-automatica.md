# Música automática (Parte 2): plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A esteira escolhe sozinha a música de cada corte pelo clima, a partir de uma biblioteca local do Incompetech, e registra o crédito.

**Architecture:** Novo módulo `esteira/musica.py` com três responsabilidades: proposta (filtra o catálogo público), download (baixa, normaliza e cataloga) e escolha (rodízio por clima). A escolha preenche o campo `musica` do `montagem.json`; o motor da Parte 1 mixa sem mudança.

**Tech Stack:** Python 3.12, urllib (stdlib), ffmpeg/ffprobe em `Automacao/bin/`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-02-musica-automatica-design.md`

## Global Constraints

- Climas válidos, exatamente: `leve`, `tenso`, `inspirador`, `reflexivo`.
- Correspondência: leve = Bright, Bouncy, Humorous; tenso = Suspenseful, Driving, Intense; inspirador = Uplifting, Epic; reflexivo = Calming, Relaxed, Somber.
- Excluir marcações Eerie, Unnerving, Dark, Aggressive, Action; excluir instrumentos com "Voice", "Vocal" ou "Choir"; duração de 90 s a 360 s.
- Catálogo: `https://incompetech.com/music/royalty-free/pieces.json`. Download: `https://incompetech.com/music/royalty-free/mp3-royaltyfree/<arquivo>` (arquivo com percent-encoding).
- Normalização: `loudnorm` para -16 LUFS. Volume na receita continua -20 dB.
- Crédito exato: `Música: <Título> — Kevin MacLeod (incompetech.com), licença CC BY 4.0`.
- Rodízio: excluir faixas usadas nos últimos 10 cortes (outros cortes; o próprio corte não conta).
- Pasta da biblioteca: `Automacao/musicas/` (`caminhos.MUSICAS`). `*.mp3` fora do Git; `proposta.md`, `aprovadas.json`, `catalogo.json`, `uso.json` no Git.
- User-Agent das requisições: `TudoEPoliticaEsteira/1.0`, sem e-mail nem dado pessoal.
- Alterações em `Contexto/` só com o texto mostrado ao dono do canal e aprovado.

## Review Focus

1. Nome de arquivo do Incompetech com espaço ou acento ("Carefree.mp3", "Clean Soul.mp3") precisa virar URL válida. Teste na Tarefa 2.
2. Rodar `musica` de novo no mesmo corte não pode trocar a faixa só porque o próprio corte já a usou. Teste na Tarefa 3.
3. Todas as faixas do clima usadas recentemente: escolher a menos recente, nunca ficar sem música. Teste na Tarefa 3.
4. Clima escrito diferente no `aprovados.json` ("Leve", "inspiradora"): a validação acusa com mensagem clara. Teste na Tarefa 3.
5. Faixa que falha no download não entra no catálogo e não impede as outras. Teste na Tarefa 2.

---

## Estrutura de arquivos

```text
esteira/
  caminhos.py   + MUSICAS
  midia.py      + duracao_audio
  musica.py     NOVO: proposta, download, escolha
  receita.py    Musica + titulo, credito
  validar.py    + clima válido
  cortar.py     preparar preenche a música; + atualizar_musica
  revisao.py    + linha "Música: Título"
  cli.py        + musicas propor | musicas baixar, + musica <pasta>
tests/
  test_musica.py (novo), test_validar.py, test_cortar.py, test_revisao.py
.gitignore      + *.mp3
```

---

### Tarefa 1: Proposta da biblioteca

**Files:**
- Modify: `esteira/caminhos.py`, `esteira/cli.py`, `.gitignore`
- Create: `esteira/musica.py`
- Test: `tests/test_musica.py`

**Interfaces:**
- Produces:
  - `MUSICAS = AUTOMACAO / "musicas"` em `caminhos.py`.
  - `CLIMAS: dict[str, set[str]]` (clima → marcações aceitas) e `CLIMAS_VALIDOS = tuple(CLIMAS)` em `musica.py`.
  - `clima_da_faixa(peca: dict) -> str | None`: primeiro clima cujas marcações casam com `peca["feel"]` (lista separada por vírgula); `None` se for excluída pelos filtros.
  - `propor(pecas: list[dict], por_clima: int = 10) -> dict[str, list[dict]]`: até `por_clima` peças por clima, cada peça em um só clima, ordenadas por preferência de instrumentação (conta de termos leves "Piano", "Strings", "Guitar", "Synth", "Pad" menos termos pesados "Drums", "Brass", "Percussion") e depois por título.
  - `escrever_proposta(selecao: dict[str, list[dict]], pasta: Path) -> None`: grava `proposta.md` (por clima: título, duração, instrumentos, link `https://incompetech.com/music/royalty-free/mp3-royaltyfree/<arquivo codificado>`, descrição) e `aprovadas.json` (`{"leve": ["Arquivo.mp3", ...], ...}`).
  - CLI `musicas propor`: baixa `pieces.json` (urllib, User-Agent da restrição global) e chama as duas funções em `MUSICAS`.

- [ ] **Step 1: Escrever os testes**

```python
PECAS = [
    {"title": "Alegre", "filename": "Alegre.mp3", "length": "00:02:30", "feel": "Bright, Bouncy", "instruments": "Piano, Guitar", "description": "x"},
    {"title": "Terror", "filename": "Terror.mp3", "length": "00:02:30", "feel": "Suspenseful, Eerie", "instruments": "Synth", "description": "x"},
    {"title": "Curta", "filename": "Curta.mp3", "length": "00:01:00", "feel": "Calming", "instruments": "Piano", "description": "x"},
    {"title": "Coro", "filename": "Coro.mp3", "length": "00:03:00", "feel": "Uplifting", "instruments": "Choir, Strings", "description": "x"},
    {"title": "Calma", "filename": "Calma.mp3", "length": "00:03:00", "feel": "Relaxed", "instruments": "Piano", "description": "x"},
]

def test_clima_da_faixa():
    assert [clima_da_faixa(p) for p in PECAS] == ["leve", None, None, None, "reflexivo"]

def test_propor_limita_e_prefere_instrumentacao_leve(): ...  # 12 peças "Bright": por_clima=10 -> 10, piano antes de "Drums, Brass"
def test_escrever_proposta_grava_md_e_aprovadas(tmp_path): ...  # aprovadas.json == {"leve": ["Alegre.mp3"], "tenso": [], "inspirador": [], "reflexivo": ["Calma.mp3"]}; link com "Clean%20Soul.mp3" para filename "Clean Soul.mp3"
```

- [ ] **Step 2: Rodar** `.venv\Scripts\python.exe -m pytest tests/test_musica.py -v`. Esperado: FAIL (módulo inexistente).
- [ ] **Step 3: Implementar** as interfaces acima e acrescentar `*.mp3` ao `.gitignore`.
- [ ] **Step 4: Rodar** de novo. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: propõe biblioteca de música por clima`.

---

### Tarefa 2: Download e catálogo

**Files:**
- Modify: `esteira/musica.py`, `esteira/midia.py`, `esteira/cli.py`
- Test: `tests/test_musica.py`

**Interfaces:**
- Consumes: `CLIMAS_VALIDOS`, `MUSICAS` (Tarefa 1).
- Produces:
  - `duracao_audio(arquivo: Path) -> float` em `midia.py` (ffprobe `format=duration`; funciona sem faixa de vídeo).
  - `@dataclass Faixa(titulo: str, clima: str, duracao: float, arquivo: str, credito: str)`; `arquivo` relativo a `MUSICAS` (`"leve/Alegre.mp3"`).
  - `credito(titulo: str) -> str`: texto exato da restrição global.
  - `ler_catalogo(pasta: Path) -> list[Faixa]` e `gravar_catalogo(pasta: Path, faixas: list[Faixa]) -> None` (`catalogo.json`; ausente → `[]`).
  - `baixar_musicas(pasta: Path, pecas: list[dict], baixar: Callable[[str, Path], None] = baixar_url) -> list[str]`: lê `aprovadas.json`; para cada arquivo ainda fora do catálogo, baixa para um temporário, normaliza com `loudnorm=I=-16:TP=-1.5:LRA=11` para `pasta/<clima>/<arquivo>`, mede a duração e acrescenta ao catálogo. Retorna mensagens de erro (`"falha em X.mp3: ..."`); uma falha não interrompe as outras. Faixa já no catálogo é pulada.
  - `baixar_url(url: str, destino: Path) -> None`: urllib com o User-Agent da restrição global.
  - CLI `musicas baixar`: baixa `pieces.json`, chama `baixar_musicas` e imprime "K faixas no catálogo" e os erros.

- [ ] **Step 1: Escrever os testes** (com `baixar` falso que gera um tom com ffmpeg, sem rede)

```python
def test_baixar_normaliza_e_cataloga(tmp_path): ...       # catálogo com Faixa("Alegre", "leve", ~5.0, "leve/Alegre.mp3", credito("Alegre"))
def test_credito_exato():
    assert credito("Carefree") == "Música: Carefree — Kevin MacLeod (incompetech.com), licença CC BY 4.0"
def test_url_com_espaco(tmp_path): ...                    # baixar recebe ".../mp3-royaltyfree/Clean%20Soul.mp3"
def test_falha_em_uma_faixa_nao_para_as_outras(tmp_path): ...  # erro listado, a outra entra no catálogo
def test_faixa_ja_catalogada_nao_baixa_de_novo(tmp_path): ...
def test_volume_normalizado(tmp_path): ...                # tom a -30 dBFS e a -6 dBFS saem com pico a menos de 3 dB um do outro
```

- [ ] **Step 2: Rodar** `.venv\Scripts\python.exe -m pytest tests/test_musica.py -v`. Esperado: FAIL nos novos.
- [ ] **Step 3: Implementar** as interfaces.
- [ ] **Step 4: Rodar** de novo. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: baixa, normaliza e cataloga músicas`.

---

### Tarefa 3: Escolha por corte

**Files:**
- Modify: `esteira/musica.py`, `esteira/receita.py`, `esteira/validar.py`, `esteira/cortar.py`, `esteira/cli.py`
- Test: `tests/test_musica.py`, `tests/test_validar.py`, `tests/test_cortar.py`

**Interfaces:**
- Consumes: `Faixa`, `ler_catalogo`, `CLIMAS_VALIDOS`, `MUSICAS`.
- Produces:
  - `Musica` ganha `titulo: str = ""` e `credito: str = ""` (ler/gravar receita antigas continuam funcionando).
  - `ler_uso(pasta: Path) -> dict[str, dict]` e `gravar_uso(pasta: Path, uso: dict[str, dict]) -> None` (`uso.json`: chave → `{"arquivo": str, "data": str ISO}`).
  - `escolher_musica(clima: str, catalogo: list[Faixa], uso: dict[str, dict], duracao: float, chave: str) -> Faixa | None`, conforme a spec seção 5: candidatas do clima; recentes = arquivos das 10 entradas mais novas de `uso` excluindo `chave`; fora as recentes (se sobrar nenhuma, todas); ordena por (duração < `duracao`, data do último uso ou "" se nunca, posição no catálogo).
  - `atualizar_musica(pasta_corte: Path, corte: Corte, chave: str, pasta_musicas: Path = MUSICAS) -> str | None`: escolhe, grava no `montagem.json` `Musica(str(pasta_musicas / faixa.arquivo), -20.0, faixa.titulo, faixa.credito)` (ou `None`), registra o uso com a data atual e retorna o título ou `None`.
  - `validar_trecho` acrescenta `"clima fora de leve, tenso, inspirador, reflexivo"` quando `corte.clima` não está em `CLIMAS_VALIDOS`.
  - `preparar_episodio` chama `atualizar_musica` depois de gravar a receita; sem faixa, o resultado vira `"ok com alertas: sem música para o clima <clima>"`. Chave = `"<nome da pasta do episódio>/<nome da pasta do corte>"`.
  - CLI `musica <pasta> [--numero N]`: chama `atualizar_musica` em cortes que já têm `montagem.json` (preserva legenda e imagens) e imprime "NN: <título>" ou "NN: sem música para o clima X".

- [ ] **Step 1: Escrever os testes**

```python
def test_escolhe_do_clima_e_prefere_mais_longa(): ...       # faixa de 60 s e de 200 s, corte de 90 s -> a de 200 s
def test_evita_as_ultimas_dez(): ...
def test_todas_recentes_volta_a_menos_recente(): ...
def test_mesmo_corte_de_novo_mantem_a_faixa(): ...          # uso com a chave do próprio corte não a exclui
def test_clima_sem_faixas_retorna_none(): ...
def test_clima_invalido_na_validacao(): ...                 # Corte(..., clima="Leve") -> problema "clima fora de leve, tenso, inspirador, reflexivo"
def test_preparar_preenche_musica_e_credito(tmp_path): ...  # catálogo de teste via pasta_musicas; montagem.json tem titulo e credito
def test_atualizar_musica_preserva_legenda(tmp_path): ...
```

Os testes de `preparar` usam o auxiliar `preparar_episodio_teste` e um catálogo de teste em `tmp_path` (monkeypatch de `cortar.MUSICAS` ou parâmetro).

- [ ] **Step 2: Rodar** `.venv\Scripts\python.exe -m pytest tests/test_musica.py tests/test_validar.py tests/test_cortar.py -v`. Esperado: FAIL nos novos.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar** a suíte inteira. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: escolhe música por clima com rodízio`.

---

### Tarefa 4: Revisão e roteiro

**Files:**
- Modify: `esteira/revisao.py`, `docs/operacao.md`
- Modify, com aprovação: `../Contexto/redes-e-publicacao.md`
- Test: `tests/test_revisao.py`

**Interfaces:**
- Consumes: `Musica.titulo` (Tarefa 3).
- Produces: bloco da revisão com a linha `Música: <título>` logo após `Publicação sugerida`, ou `Música: nenhuma`.

- [ ] **Step 1: Teste** `test_revisao_mostra_musica(tmp_path)`: receita com `Musica(..., titulo="Carefree")` → linha `Música: Carefree`; sem música → `Música: nenhuma`.
- [ ] **Step 2: Rodar**, ver falhar; **Step 3: implementar**; **Step 4: rodar**, ver passar.
- [ ] **Step 5: `docs/operacao.md`**: clima com os 4 valores (etapa 2); etapa nova "Música" após "Preparar" (`musica` só se a receita já existir; `preparar` já escolhe); seção "Música" do `post.md` passa a ser: faixa usada e o crédito exato da receita, na descrição do YouTube e nos textos de Instagram e TikTok; fora a busca no CapCut. Seção "Biblioteca de música": `musicas propor`, aprovação do dono do canal, `musicas baixar`.
- [ ] **Step 6: Mostrar ao dono do canal** o texto para `Contexto/redes-e-publicacao.md` ("Toda descrição e texto de post traz o crédito da música: Música: <Título> — Kevin MacLeod (incompetech.com), licença CC BY 4.0.") e salvar só depois da aprovação.
- [ ] **Step 7: Commit** `feat: mostra música na revisão e atualiza roteiro`.

---

### Tarefa 5: Biblioteca real e teste no F1

Feita com o dono do canal.

- [ ] **Step 1:** `esteira musicas propor`; mostrar `musicas/proposta.md` ao dono do canal; ajustar `aprovadas.json` conforme a resposta. Commit `docs: proposta da biblioteca de música`.
- [ ] **Step 2:** pedir confirmação do download (quantidade de faixas, origem incompetech.com, tamanho total estimado pela duração a ~160 kbps). Rodar `esteira musicas baixar`. Commit de `catalogo.json`.
- [ ] **Step 3:** `esteira musica "<F1>"` e `esteira montar "<F1>" --forcar` (pedir confirmação antes do `--forcar`); `esteira revisao`; acrescentar o crédito aos 10 `post.md`.
- [ ] **Step 4:** o dono do canal ouve; ajustar `volume_db` padrão se ele pedir (um número para todos).
- [ ] **Step 5:** registrar em `docs/resultados/` e commitar `uso.json` e o resultado.
