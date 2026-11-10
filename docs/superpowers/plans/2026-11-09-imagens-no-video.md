# Imagens no vídeo (Fase B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `esteira montar` e o painel põem no `corte.mp4` as imagens prontas de cada momento, e o dono aprova o vídeo por um botão do painel.

**Architecture:** Um módulo novo (`imagens_no_video.py`) decide, a partir do `pedidos.json` e dos arquivos prontos, qual imagem de cada momento entra e em que tempo de tela. O `render.py` volta a sobrepor imagens (código de antes de 05/11, adaptado). O painel ganha um pedido `montar` na fila (com a proteção da troca de música) e um módulo `aprovacao.py` que copia o corte para `video-final/`. O `agendar` lê o que foi aprovado para exigir o aviso de IA.

**Tech Stack:** Python 3.12, ffmpeg (`bin/ffmpeg.exe`), Pillow, FastAPI, pytest; React 18 + TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-09-imagens-no-video-design.md`

## Global Constraints

- Rodar tudo a partir da raiz do worktree com `../Automacao/.venv/Scripts/python.exe -m pytest` e, no `painel-web/`, `npx vitest run`.
- Fins de linha: `esteira/cli.py`, `esteira/publicar/agendar.py` e `tests/test_publicar_agendar.py` são CRLF; o resto é LF. Conferir com `git ls-files --eol` antes de cada commit que toque esses arquivos.
- Mensagens e textos da tela em português do Brasil, exatamente como na spec.
- Nenhum pacote novo (Python ou npm). Nenhum download.
- Toda escrita passa por `garantir_escrita` (painel com `base_extra=app.state.cortes`).
- A esteira só grava em `video-final/` pelo `aprovacao.aprovar`, e só substitui o arquivo que o `aprovado.json` diz ser dela.
- Chave e nome de arquivo pelo tempo proposto (`chave_momento` do momento original); tempo de tela pelo `ajustar_tempos` numa cópia.
- Arquivo da aprovação: `video-final/corte-aprovado.mp4`; registro `trabalho/aprovado.json`; temporário `video-final/.corte-aprovado.tmp`.
- Aviso de IA: `Algumas imagens utilizadas neste vídeo foram geradas por Inteligência Artificial (IA).`
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Pasta do episódio com acento e espaço (`Tudo é Política`): a imagem entra pelo argv do ffmpeg e nunca dentro do `filter_complex`. Teste no Task 2.
2. Imagem que termina exatamente no fim da parte principal: a transição para o encerramento e a conferência de duração continuam certas. Teste no Task 2.
3. `no_video` com caminho (`../x.jpg`, `sub/x.jpg`) ou arquivo de outro momento num PUT: 422, nada gravado. Teste no Task 6.
4. Corte montado antes da Fase B (`registro.json` sem `imagens`): `no_corte` vazio, nada desatualizado se não há momentos prontos, e o `agendar` mantém a linha antiga. Testes nos Tasks 6 e 8.
5. Vídeo do dono com o mesmo nome `corte-aprovado.mp4` mas sem bater com o `aprovado.json`: é do dono, nunca substituído. Teste no Task 7.

---

### Task 1: Tempo único na chave e no nome dos arquivos

**Files:**
- Modify: `esteira/fluxo_imagens.py` (`_arquivos`, `_bloco_guia`, `_linha_ia`, `escrever_guia`, `_sugerir_um`, `sugerir_episodio`, `LEMBRETES`)
- Modify: `esteira/imagens_ia/gerar.py` (`_momentos_do_guia`, chamada de `escrever_guia`)
- Modify: `esteira/pedidos.py` (campo `no_video`)
- Test: `tests/test_fluxo_imagens.py`, `tests/test_imagens_ia_gerar.py`, `tests/test_pedidos.py`

**Interfaces:**
- Produces: `Momento.no_video: str = ""` (último campo do dataclass); `_arquivos(m: Momento, chave: str | None = None) -> list[str]` (sem `chave`, usa `chave_momento(m)`); `escrever_guia(destino: Path, momentos: list[Momento], ajustados: list[Momento] | None = None) -> Path` (`momentos` originais dão chave e nomes; `ajustados`, paralela, dá tempos de tela e descartes do ajuste; sem ela, os próprios `momentos`).

- [ ] **Step 1: Testes que falham**

```python
def test_sugerir_nomeia_pela_chave_proposta_quando_o_ajuste_puxa_o_inicio(tmp_path):
    # dois momentos: o 1º em 10.0-10.5, o 2º começando em 11.0 (o 1º não cabe para frente,
    # o ajuste puxa o início para 9.0); duração 60
    ...  # sugerir com baixar falso
    assert (destino / "imagens-sugeridas" / "0010-placa-1.jpg").exists()
    assert not (destino / "imagens-sugeridas" / "0009-placa-1.jpg").exists()
    assert "## 0:09 a 0:11 · Placa (foto)" in guia  # tela = ajustado

def test_guia_acha_imagem_de_ia_quando_o_ajuste_muda_o_inicio(tmp_path):
    # momento ia 20.0-20.5 seguido de outro em 21.0; ia.json com "momento": "0020-chuva"
    escrever_guia(destino, momentos, ajustados)
    assert "Imagem de IA: 0020-chuva-ia-1.jpg" in guia

def test_no_video_vazio_por_padrao_e_lido_do_arquivo(tmp_path):
    assert ler_pedidos(trabalho)[0].no_video == ""
    # com "no_video": "0012-x-2.jpg" no JSON, volta igual
```

- [ ] **Step 2: Rodar e ver falhar** — `python -m pytest tests/test_fluxo_imagens.py tests/test_imagens_ia_gerar.py tests/test_pedidos.py -q`. Esperado: os três novos falham (nome `0009-…`, linha de IA ausente, `no_video` desconhecido).

- [ ] **Step 3: Implementar.** Em `sugerir_episodio`, guardar `chaves = [chave_momento(m) for m in momentos]` antes de `_ajustados` e passar a `_sugerir_um`, que nomeia com `_arquivos(copia[i], chaves[i])` e chama `escrever_guia(destino, momentos, copia)`. `_bloco_guia(pasta, m_tela, chave, …)` usa a chave para nomes e para `_linha_ia`. `gerar_momento` chama `escrever_guia(pasta_corte, momentos, _momentos_do_guia(...))`. Primeira linha de `LEMBRETES` depois do título: `A esteira já põe no corte.mp4 a imagem marcada de cada momento. Este guia serve para quem for editar no CapCut.`

- [ ] **Step 4: Rodar** os três arquivos de teste. Esperado: tudo passa.

- [ ] **Step 5: Commit** `fix: chave e nome das imagens pelo tempo proposto; tela pelo ajustado`

### Task 2: Render com imagens e legenda escondida

**Files:**
- Modify: `esteira/receita.py` (dataclass `ImagemNoVideo`)
- Modify: `esteira/legenda.py` (`ocultar_durante`, de volta de `b901087^`)
- Modify: `esteira/render.py` (`renderizar_final`, `_filtro_imagem`)
- Test: `tests/test_render.py`, `tests/test_legenda.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class ImagemNoVideo: inicio: float; fim: float; arquivo: str; tipo: str = ""; momento: str = ""; modificado_ns: int = 0` (`arquivo` relativo à pasta do corte); `ocultar_durante(cues: list[Cue], intervalos: list[tuple[float, float]]) -> list[Cue]`; `renderizar_final(receita, video, cartao, pasta, saida, sobreposicao=None, imagens: Sequence[ImagemNoVideo] = ()) -> list[str]`; constante `ZOOM_IMAGEM = 1.08`.

- [ ] **Step 1: Testes que falham** (adaptar os de `git show b901087^:tests/test_render.py` e `tests/test_legenda.py`):

```python
def test_imagem_aparece_no_tempo(tmp_path):          # vermelha 1080x1920 de 0.5 a 2.5 num corte de 3 s
    assert _vermelho(_quadro(saida, 1.5, ...).getpixel((540, 960)))
    assert not _vermelho(_quadro(saida, 0.2, ...).getpixel((540, 960)))
    assert not _vermelho(_quadro(saida, 2.8, ...).getpixel((540, 960)))

def test_legenda_some_durante_imagem(tmp_path):      # Cue(0, 3, ["LEGENDA BEM LONGA"]) e imagem de 0.5 a 2.5
    assert _brancos_na_legenda(_quadro(saida, 1.5, ...)) == 0
    assert _brancos_na_legenda(_quadro(saida, 0.2, ...)) > 0

def test_imagem_de_outro_tamanho_cobre_a_tela_sem_distorcer(tmp_path):  # 800x600 vermelha: quadro inteiro vermelho

def test_zoom_alterna_entre_imagens():               # _filtro_imagem(…, ordem=0) contém "(1+" ; ordem=1 contém "(1.08-"

def test_imagem_ate_o_fim_da_parte_principal(tmp_path):  # imagem 1.0-3.0 num corte de 3 s com encerramento: duração 3 + fim

def test_caminhos_com_acento_em_imagem_e_musica(tmp_path):  # imagem "imagens-sugeridas/0001-ação-1.jpg" na pasta "Tudo é Política (teste)"

def test_ocultar_durante_corta_e_mantem_o_lado_maior():   # os casos do teste antigo
```

- [ ] **Step 2: Rodar e ver falhar** — `python -m pytest tests/test_render.py tests/test_legenda.py -q`. Esperado: `ImportError`/`TypeError` nos novos.

- [ ] **Step 3: Implementar.** `_filtro_imagem(entrada: int, saida: str, ordem: int, imagem: ImagemNoVideo) -> str`: `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920`, o `perspective` do código antigo (par aproxima de 1 a 1.08, ímpar afasta), `setsar=1,format=yuv420p,setpts=PTS-STARTPTS+<inicio>/TB`. Em `renderizar_final`: a legenda (`ass`) é aplicada primeiro em `[vprin]`; depois, um `overlay=enable='between(t,a,b)':eof_action=pass` por imagem, em ordem de `inicio`; o `.ass` é escrito com `ocultar_durante(receita.legenda, [(i.inicio, i.fim) for i in imagens])`. Entrada de cada imagem: `-loop 1 -framerate 30 -t <dur> -i <pasta/arquivo resolvido>`.

- [ ] **Step 4: Rodar** os dois arquivos. Esperado: tudo passa.

- [ ] **Step 5: Commit** `feat: render sobrepõe imagens com zoom alternado e esconde a legenda`

### Task 3: Escolha da imagem de cada momento

**Files:**
- Create: `esteira/imagens_no_video.py`
- Modify: `esteira/painel/rotas_imagens.py` (passa a usar o módulo novo em `_fotos_prontas` e `_ia_do_momento`)
- Test: `tests/test_imagens_no_video.py`

**Interfaces:**
- Consumes: `ImagemNoVideo` (Task 2); `_arquivos`, `chave_momento`, `ler_ia`, `ler_creditos`, `_ler_sugeridas` (`fluxo_imagens`); `arquivo_de_versao`, `MAXIMO_VERSOES` (`imagens_ia.gerar`); `ajustar_tempos`, `rotulo_momento` (`pedidos`).
- Produces:
  - `fotos_prontas(m: Momento, chave: str, imagens: Path, sugeridas: set[str], creditos: dict[str, dict]) -> list[str]` (a lógica atual de `_fotos_prontas`/`_mesma_foto`, movida);
  - `versoes_ia(chave: str, imagens: Path, ia: list[dict]) -> list[dict]` (`{"arquivo", "versao", "provedor", "data"}`, em ordem de versão; a lógica atual de `_ia_do_momento`, movida);
  - `@dataclass class Escolha: chave: str; momento: Momento; inicio_tela: float | None; fim_tela: float | None; prontas: list[str]; arquivo: str | None; alerta: str | None`;
  - `escolhas_do_corte(destino: Path, momentos: list[Momento], duracao: float | None) -> list[Escolha]` (uma por momento, na ordem do arquivo; `duracao` None: sem ajuste);
  - `imagens_do_corte(destino: Path) -> tuple[list[ImagemNoVideo], list[str]]` (lê `pedidos.json` e `montagem.json`; lista em ordem de tempo; `modificado_ns` do arquivo).

- [ ] **Step 1: Testes que falham**

```python
def test_foto_entra_a_primeira_opcao_pronta(...)        # opção 1 falhou, 2 pronta: arquivo "<chave>-2.jpg"
def test_ia_entra_a_versao_mais_nova(...)               # versões 1 e 2: "<chave>-ia-2.jpg"
def test_noticia_entra_o_cartao(...)
def test_no_video_valido_manda(...)                     # no_video = "<chave>-ia-1.jpg"
def test_no_video_vencido_entra_o_padrao_com_alerta(...)
    assert alerta == "imagem 0:12 Placa: 0012-placa-3.jpg não está pronta, entrou 0012-placa-1.jpg"
def test_momento_sem_imagem_fica_de_fora_com_motivo(...)  # foto: "imagem 0:12 Placa fora do vídeo: foto não baixada"
                                                          # notícia: "...: cartão não gerado"; IA: "...: IA ainda não gerada"
def test_descartado_pelo_dono_nao_entra_nem_alerta(...)
def test_descartado_pelo_ajuste_alerta(...)             # "imagem 0:12 Placa fora do vídeo: não cabe em 2 s"
def test_tempo_de_tela_e_o_ajustado(...)                # momento 12.0-12.5 → tela 12.0-14.0
def test_sem_pedidos_lista_vazia_sem_alerta(...)
def test_pedidos_ilegivel_lista_vazia_com_alerta(...)   # alerta começa com "imagens: pedidos.json ilegível:"
```

- [ ] **Step 2: Rodar e ver falhar** — `python -m pytest tests/test_imagens_no_video.py -q`. Esperado: `ModuleNotFoundError`.

- [ ] **Step 3: Implementar** o módulo. Rótulo dos alertas: `rotulo_momento(i, m, painel=True)` do momento original. Ordem de preferência das prontas: foto por K crescente; IA por versão decrescente; notícia o cartão. `rotas_imagens` passa a importar `fotos_prontas` e `versoes_ia` (sem mudar a resposta de hoje).

- [ ] **Step 4: Rodar** `python -m pytest tests/test_imagens_no_video.py tests/test_painel_imagens_api.py -q`. Esperado: tudo passa.

- [ ] **Step 5: Commit** `feat: escolha da imagem de cada momento para o vídeo`

### Task 4: `montar` com as imagens

**Files:**
- Modify: `esteira/montar.py`, `esteira/cortar.py` (`registrar` ganha `imagens`), `esteira/cli.py` (CRLF: `--sem-imagens`)
- Test: `tests/test_montar.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `imagens_do_corte` (Task 3); `renderizar_final(..., imagens=)` (Task 2).
- Produces: `montar_episodio(pasta, numeros=None, forcar=False, cartao=None, sem_imagens: bool = False) -> dict[int, str]`; `registrar(..., imagens: list[dict] | None = None)` grava `"imagens"` quando não é None; `registro.json["imagens"]` = `[asdict(ImagemNoVideo)]` no corte montado com sucesso (lista vazia com `--sem-imagens`).

- [ ] **Step 1: Testes que falham**

```python
def test_montar_poe_as_imagens_prontas_e_registra(tmp_path):   # 1 foto pronta (sugeridas.json + creditos.json)
    assert registro["imagens"][0]["arquivo"] == "imagens-sugeridas/0001-placa-1.jpg"
    assert _vermelho(quadro no meio da imagem)
def test_montar_alerta_momento_sem_imagem(tmp_path):           # resultado "ok com alertas: ... IA ainda não gerada"
def test_montar_sem_imagens(tmp_path):                         # registro["imagens"] == [] e nenhum quadro vermelho
def test_cli_montar_sem_imagens_repassa(monkeypatch)           # args → montar_episodio(..., sem_imagens=True)
```

- [ ] **Step 2: Rodar e ver falhar** — `python -m pytest tests/test_montar.py tests/test_cli.py -q`.

- [ ] **Step 3: Implementar.** Em `montar_episodio`, depois de `ler_receita`: `imagens, alertas_img = ([], []) if sem_imagens else imagens_do_corte(destino)`; os alertas das imagens entram depois dos do render, sem repetir. `registrar(..., imagens=[asdict(i) for i in imagens])` só no sucesso. CLI: `c.add_argument("--sem-imagens", action="store_true")`.

- [ ] **Step 4: Rodar** os dois arquivos. Esperado: tudo passa. Conferir `git ls-files --eol esteira/cli.py` (`w/crlf`).

- [ ] **Step 5: Commit** `feat: montar põe as imagens prontas; --sem-imagens monta sem elas`

### Task 5: Remontagem protegida e fila

**Files:**
- Modify: `esteira/painel/troca_musica.py` (extrai a parte protegida; `remontar`)
- Modify: `esteira/painel/fila.py` (música e montagem se bloqueiam; `montando_corte`)
- Modify: `esteira/painel/rotas.py` (o selo "montando" da lista usa `montando_corte`)
- Test: `tests/test_painel_troca_musica.py`, `tests/test_painel_fila.py`

**Interfaces:**
- Produces: `remontar(pasta_episodio: Path, numero: int, montar: Callable[[Path, int], str], base: Path | None = None, substituir=os.replace, dormir=time.sleep) -> Resultado` (`"pronto"` com `mensagem` = resultado do montar e `avisos` = alertas; `"erro"` com `resumir_erro`, e `corte.mp4`/`registro.json` de antes de volta); `Fila.montando_corte(episodio: str, numero: int) -> bool`; constante `MONTAGEM = ("musica", "montar")` em `fila.py`.

- [ ] **Step 1: Testes que falham**

```python
def test_remontar_ok_devolve_alertas(tmp_path)          # montar falso "ok com alertas: a; b" → avisos ["a", "b"]
def test_remontar_falha_devolve_corte_e_registro(tmp_path)  # bytes de antes de volta
def test_remontar_com_video_aberto(tmp_path)            # substituir levanta PermissionError → mensagem VIDEO_ABERTO
def test_musica_e_montagem_se_bloqueiam(...)            # pedir_tarefa("montar") com "musica" ativa → PedidoAtivo, e o contrário
def test_montando_corte_ve_os_dois_tipos(...)
```

- [ ] **Step 2: Rodar e ver falhar** — `python -m pytest tests/test_painel_troca_musica.py tests/test_painel_fila.py -q`.

- [ ] **Step 3: Implementar.** `trocar_musica` e `remontar` usam a mesma função interna (desfaz troca interrompida, marcador, guarda o vídeo, monta, restaura na falha); só `trocar_musica` muda a receita, troca o crédito e registra o uso. Na fila, `pedir` e `pedir_tarefa` recusam quando o tipo pedido está em `MONTAGEM` e há qualquer pedido ativo de `MONTAGEM` no corte (`o corte N já está sendo montado`).

- [ ] **Step 4: Rodar** os dois arquivos e `tests/test_painel_musica_api.py`. Esperado: tudo passa.

- [ ] **Step 5: Commit** `feat: remontagem protegida e música e montagem exclusivas na fila`

### Task 6: API do painel — momentos e montar

**Files:**
- Modify: `esteira/painel/rotas_imagens.py`, `esteira/painel/app.py` (`app.state.montar`)
- Test: `tests/test_painel_imagens_api.py`

**Interfaces:**
- Consumes: `escolhas_do_corte`, `imagens_do_corte` (Task 3); `remontar`, `montando_corte` (Task 5).
- Produces: `montagem_desatualizada(destino: Path) -> bool` em `imagens_no_video.py` (compara `(arquivo, inicio, fim, modificado_ns)` previstos com `registro.json["imagens"]`; sem `corte.mp4`, False; registro sem `imagens` vale `[]`); `AlteracaoMomento.no_video: str | None`; resposta de `GET momentos` com `no_video`, `prontas`, `inicio_tela`, `fim_tela` por momento e `no_corte`, `montagem_desatualizada`; `POST /api/episodios/{ep}/cortes/{n}/montar` (corpo `Confirmacao`) → 202 pedido `tipo: "montar"`.

- [ ] **Step 1: Testes que falham**

```python
def test_momentos_traz_no_video_prontas_e_tempo_de_tela(...)
def test_put_no_video_valido_grava(...)                 # no_video volta na resposta e no pedidos.json
def test_put_no_video_vazio_volta_ao_padrao(...)
def test_put_no_video_invalido_422(...)                 # "../x.jpg", "sub/x.jpg", arquivo de outro momento; arquivo intacto
def test_montar_202_e_executa_remontar(...)             # fila falsa: pedido "montar" com cortes [n]
def test_montar_409_com_musica_ativa(...)               # detail "Este corte já está sendo montado."
def test_montar_sem_confirmacao_422(...)
def test_montagem_desatualizada(...)                    # registro com outra lista → True; mesma lista → False; registro antigo sem "imagens" e nada pronto → False
```

- [ ] **Step 2: Rodar e ver falhar** — `python -m pytest tests/test_painel_imagens_api.py -q`.

- [ ] **Step 3: Implementar.** `PUT` valida `no_video` contra `prontas` do momento (vazio é sempre válido) e grava como os outros campos. A rota `montar` monta o executar com `remontar(pasta, n, estado.montar, base=estado.cortes)`, chamando `progresso("Montando o corte…")` antes.

- [ ] **Step 4: Rodar** `python -m pytest tests/test_painel_imagens_api.py tests/test_painel_api.py -q`. Esperado: tudo passa.

- [ ] **Step 5: Commit** `feat: painel escolhe a imagem do vídeo e monta o corte com as imagens`

### Task 7: Aprovação pelo painel

**Files:**
- Create: `esteira/aprovacao.py`
- Modify: `esteira/painel/rotas.py` (`GET corte` com `aprovacao` e `montagem_desatualizada`; `POST aprovar`)
- Test: `tests/test_aprovacao.py`, `tests/test_painel_api.py`

**Interfaces:**
- Produces: `ARQUIVO_APROVADO = "corte-aprovado.mp4"`; `REGISTRO_APROVADO = "aprovado.json"`; `@dataclass class Aprovacao: estado: str; motivo: str | None = None` (`"aprovar" | "aprovar de novo" | "aprovado" | "bloqueado"`); `class ErroAprovacao(Exception)` com `status: int`; `da_esteira(destino: Path) -> dict | None`; `estado_aprovacao(destino: Path, montando: bool = False) -> Aprovacao`; `aprovar(destino: Path, montando: bool = False, base: Path | None = None, agora=datetime.now) -> Aprovacao`; `imagens_aprovadas(destino: Path, video: Path) -> list[dict] | None`.

- [ ] **Step 1: Testes que falham**

```python
def test_aprovar_copia_e_registra(tmp_path)           # video-final/corte-aprovado.mp4 com os mesmos bytes; aprovado.json com tamanho, modificado_ns, imagens do registro
def test_estado_aprovado_depois_de_aprovar(tmp_path)
def test_corte_remontado_pede_aprovar_de_novo_e_substitui_so_a_copia(tmp_path)
def test_video_do_dono_bloqueia(tmp_path)             # motivo "video-final/ já tem um vídeo seu (Corte 1.mp4). Para aprovar o corte da esteira, tire esse vídeo de lá."; aprovar → ErroAprovacao 409, nada muda
def test_dono_trocou_o_corte_aprovado_e_dele(tmp_path) # mesmo nome, outro tamanho → bloqueado, arquivo intacto
def test_sem_corte_422(tmp_path)                      # motivo "corte não montado"
def test_montando_bloqueia_409(tmp_path)              # motivo "o corte está sendo montado"
def test_aprovado_json_ilegivel_trata_como_do_dono(tmp_path)
def test_imagens_aprovadas_so_da_copia_da_esteira(tmp_path)  # outro vídeo → None; registro antigo sem imagens → None
def test_api_aprovar_e_detalhe_do_corte(...)          # POST 200 {"estado": "aprovado"}; GET corte traz aprovacao e montagem_desatualizada; sem confirmação 422
```

- [ ] **Step 2: Rodar e ver falhar** — `python -m pytest tests/test_aprovacao.py tests/test_painel_api.py -q`.

- [ ] **Step 3: Implementar.** Cópia: `shutil.copyfile` para `.corte-aprovado.tmp` na própria `video-final/`, `os.replace`, temporário apagado em qualquer falha. `aprovado.json` gravado depois da troca, com `stat()` do arquivo final. "Em dia" = `st_mtime` da cópia ≥ `st_mtime` do `corte.mp4`. Rota: `POST /api/episodios/{ep}/cortes/{n}/aprovar` (corpo `Confirmacao`), `montando=fila.montando_corte(...)`, `ErroAprovacao` vira `{"detail": motivo}` com o `status`.

- [ ] **Step 4: Rodar** os dois arquivos e `tests/test_revisao.py`. Esperado: tudo passa.

- [ ] **Step 5: Commit** `feat: aprovar o corte pelo painel copia para video-final`

### Task 8: `agendar` com as imagens aprovadas

**Files:**
- Modify: `esteira/publicar/post.py` (`AVISO_IA`, `faltando_aviso_ia`), `esteira/publicar/agendar.py` (CRLF)
- Test: `tests/test_publicar_post.py`, `tests/test_publicar_agendar.py` (CRLF)

**Interfaces:**
- Consumes: `imagens_aprovadas` (Task 7); `ler_creditos` (`fluxo_imagens`).
- Produces: `faltando_aviso_ia(textos: Textos, redes: set[str]) -> list[str]` (`"<rede>: falta o aviso de IA"`; YouTube olha a descrição; comparação sem diferença de maiúsculas e espaços); `Pedido.imagens_no_video: list[dict] | None = None`; `Pedido.creditos: list[str]`.

- [ ] **Step 1: Testes que falham**

```python
def test_ia_no_video_aprovado_sem_aviso_recusa(...)    # "youtube: falta o aviso de IA" etc. só nas redes pedidas
def test_ia_no_video_aprovado_com_aviso_passa_e_resume(...)  # "Imagens de IA no vídeo: 1 (o aviso está nos textos)."
def test_sem_ia_no_video_aprovado_nao_mostra_linha_de_ia(...)  # ia.json com imagens geradas, nenhuma no vídeo
def test_resumo_lista_creditos_das_fotos(...)          # "Créditos das fotos no vídeo:" e "- Autor, CC BY-SA 4.0, https://…"
def test_video_do_capcut_mantem_a_linha_antiga(...)    # "Este corte tem 2 imagens de IA geradas: confira se o vídeo final usa alguma e inclua o aviso."
def test_mensagem_de_video_final_desatualizado(...)    # "vídeo final mais antigo que o corte.mp4: aprove de novo no painel ou refaça no CapCut"
```

- [ ] **Step 2: Rodar e ver falhar** — `python -m pytest tests/test_publicar_post.py tests/test_publicar_agendar.py -q`.

- [ ] **Step 3: Implementar.** Crédito sem registro no `creditos.json`: `- <nome do arquivo>: crédito não encontrado (confira o guia.md)`.

- [ ] **Step 4: Rodar** os arquivos de `tests/test_publicar_*.py`. Esperado: tudo passa. `git ls-files --eol` mostra `w/crlf` nos dois arquivos CRLF.

- [ ] **Step 5: Commit** `feat: agendar exige o aviso de IA quando o vídeo aprovado tem IA`

### Task 9: Telas do painel

**Files:**
- Modify: `painel-web/src/api.ts`, `painel-web/src/componentes/CartaoMomento.tsx`, `painel-web/src/componentes/BlocoImagens.tsx`, `painel-web/src/componentes/imagensComum.tsx` (`montar` no andamento), `painel-web/src/telas/Corte.tsx`
- Create: `painel-web/src/componentes/Aprovacao.tsx`
- Test: `CartaoMomento.test.tsx`, `BlocoImagens.test.tsx`, `Aprovacao.test.tsx`, `telas/Corte.test.tsx`

**Interfaces:**
- Consumes: as rotas dos Tasks 6 e 7.
- Produces (`api.ts`): `Momento` += `no_video: string | null; prontas: string[]; inicio_tela: number | null; fim_tela: number | null`; `RespostaMomentos` += `no_corte: unknown[]; montagem_desatualizada: boolean`; `AlteracaoMomento` += `no_video?: string`; `interface Aprovacao { estado: "aprovar" | "aprovar de novo" | "aprovado" | "bloqueado"; motivo: string | null }`; `CorteDetalhe` += `aprovacao: Aprovacao; montagem_desatualizada: boolean`; `montarCorte(ep, n): Promise<Pedido>`; `aprovarCorte(ep, n): Promise<Aprovacao>`.

- [ ] **Step 1: Testes que falham**

```tsx
it("marca No vídeo na imagem que entra e oferece Usar no vídeo nas outras prontas")  // clique → alterar({no_video: "0012-x-2.jpg"}, {no_video: "0012-x-2.jpg"})
it("mostra o tempo de tela e o proposto quando o ajuste mudou o início")             // "0:09 (proposto 0:10)"; ▶ chama irPara(9)
it("Montar com as imagens confirma com a contagem e manda o pedido")               // confirm com "Montar o corte de novo com 2 imagens? O corte.mp4 atual será substituído (leva cerca de 1 minuto)."
it("avisa quando as imagens mudaram desde a última montagem")                     // "As imagens mudaram desde a última montagem."
it("Aprovar este vídeo confirma e mostra Aprovado")
it("Aprovar de novo e bloqueado mostram o texto certo")                            // bloqueado mostra o motivo, sem botão
it("a confirmação de aprovar começa pelo aviso quando a montagem está desatualizada")
```

- [ ] **Step 2: Rodar e ver falhar** — `cd painel-web; npx vitest run`.

- [ ] **Step 3: Implementar.** `BlocoImagens` recebe `soltarVideo`, `aoMudarAndamento` e `aoTerminarMontagem` (como o `BlocoMusica`); o pedido `montar` é acompanhado pelo mesmo `useAcompanhamento`, e a contagem da confirmação é o número de momentos com `no_video`. `Aprovacao` fica junto do `Selo` na tela do corte; ao aprovar, a tela recarrega o detalhe do corte (selo e lista de `video_final`). Texto da confirmação de aprovar: `Aprovar este corte? O corte.mp4 vai para video-final/ como corte-aprovado.mp4 e passa a ser o vídeo que o agendar publica.`

- [ ] **Step 4: Rodar** `npx vitest run` e `npx tsc -b`. Esperado: tudo passa, sem erro de tipo.

- [ ] **Step 5: Commit** `feat: telas para escolher a imagem do vídeo, montar e aprovar`

### Task 10: Regras e documentos

**Files:**
- Modify: `C:\Tudo é Política\Contexto\estilo-de-imagens.md`, `C:\Tudo é Política\Contexto\estilo-dos-cortes.md` (fora do repositório: editar no lugar, sem commit)
- Modify: `docs/operacao.md`, `docs/painel.md`

- [ ] **Step 1:** Aplicar o texto da seção "Regras do canal que mudam" da spec; no `operacao.md`, trocar as etapas 7 e 8 (a pausa do download passa a ser a etapa 7), a regra de `video-final/`, `--sem-imagens`, a mensagem nova do `agendar` e "Corrigir um corte" (remontar pelo painel).
- [ ] **Step 2:** `grep -rn "CapCut\|etapa 8\|nunca grava" docs/operacao.md docs/painel.md ../Contexto` e conferir que nenhuma frase velha contradiz a nova.
- [ ] **Step 3: Commit** (só `docs/`) `docs: operação e painel com as imagens no vídeo`

### Task 11: Conferência real e revisão final

- [ ] **Step 1:** Suítes completas: `python -m pytest -q` e `npx vitest run`. Esperado: tudo passa.
- [ ] **Step 2:** Cópia de teste em `Automacao/.superpowers/teste-fase-b/` do corte 01 do episódio `(teste capcut)` (sem `corte.mp4` e sem `video-final/`), com uma imagem de IA de teste registrada no `ia.json` da cópia. Rodar `montar`, extrair quadros (até 640 px, apagados no fim) no meio de cada imagem e fora delas, e conferir: tela cheia, faixa central com fundo desfocado, sem legenda, zoom diferente entre o primeiro e o último quadro, duração certa.
- [ ] **Step 3:** Painel na cópia (`painel --cortes`): marcar outra opção `No vídeo`, `Montar com as imagens`, `Aprovar este vídeo`; conferir `video-final/corte-aprovado.mp4` e o selo.
- [ ] **Step 4:** Revisão do branch inteiro por um revisor novo; corrigir o que for confirmado.
- [ ] **Step 5:** Merge `--ff-only` no `master`, `npm run build` no `Automacao/painel-web`, resultado em `docs/resultados/2026-teste-imagens-no-video.md`.
