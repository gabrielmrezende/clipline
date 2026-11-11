# Auditoria do clipline

**Repositório:** https://github.com/gabrielmrezende/clipline (branch `master`, commit `3e4350c`)
**Data:** 11/11/2026
**Escopo:** código Python (`esteira/`, ~8,4 mil linhas), painel web (`painel-web/`, ~7,4 mil linhas), testes, documentação, uso do Claude, segurança, design, UX e comparação com ferramentas equivalentes.

---

## 1. Resumo executivo

O clipline é uma esteira local (Windows + GPU NVIDIA) que transforma um episódio horizontal em 8 a 10 cortes verticais. A CLI em Python faz o trabalho mecânico (Whisper, pyannote, YuNet/SFace, ffmpeg), o **Claude Code**, em sessão interativa, faz o julgamento editorial (escolher trechos, momentos de imagem, textos e calendário) e o dono do canal aprova num painel FastAPI + React.

**Veredito: a engenharia é acima da média para um projeto de um autor só, mas o produto ainda é uma ferramenta de um canal, e a parte que depende do Claude é a menos protegida e a menos reproduzível.**

Os cinco pontos que mais importam:

1. **As travas contra o agente são texto, não mecanismo.** "Nunca rodar `--confirmar` sem o sim do dono" está só em `docs/operacao.md`. Nada no repositório impede o Claude Code de publicar, gastar com IA ou sobrescrever com `--forcar`. Transcrição, títulos do Wikimedia e `post.md` são conteúdo não confiável lido por um agente com shell.
2. **A integração com o Claude não está versionada.** O código cita um `CLAUDE.md` que não existe no repositório. Não há skills, comandos, hooks, `settings.json`, esquema dos JSON que o Claude grava, registro de qual modelo decidiu o quê, nem avaliação da qualidade das escolhas.
3. **A limpeza de pausas pode cortar fala real.** `limpeza.py` remove qualquer lacuna maior que 0,5 s entre palavras transcritas, sem conferir o áudio. Palavra que o Whisper perdeu (fala sobreposta, riso, interjeição) some do corte.
4. **O filtro de "pessoa real" em imagens de IA é uma lista de nomes.** Para um canal de política, é o maior risco reputacional do projeto: "o presidente", um apelido ou um nome fora do glossário passam.
5. **Frente ao mercado, falta o que o espectador vê:** legenda animada palavra a palavra, enquadramento com acompanhamento suave, gancho na tela, nota/ranking dos cortes e edição pela interface. Em compensação, o clipline tem o que quase ninguém tem: revisão humana obrigatória, proveniência de licenças, crédito automático, controle de custo e execução local.

### Limites desta auditoria

- **Análise estática.** Li o código, a documentação e os testes. **Não executei a suíte de testes nem a esteira**: o ambiente da auditoria bloqueou a execução de código clonado, e a esteira exige Windows, GPU, `ffmpeg.exe` e modelos que não estão no repositório. Tudo o que digo sobre comportamento em execução é inferência a partir do código.
- **Rodei** `npm audit` sobre o `package-lock.json` e calculei o contraste WCAG das cores do CSS.
- **Não verifiquei** os nomes de modelos e os preços em `imagens-ia.json` (`gpt-image-2`, `gemini-nano-banana-2.1`), a versão da Graph API (`v21.0`) nem o cabeçalho `Api-Revision` do Google. Confira nas documentações oficiais.
- **Não testei as ferramentas concorrentes.** A comparação da seção 9 usa a descrição pública de cada uma.
- A severidade (Alta, Média, Baixa) é qualitativa: impacto estimado × facilidade de ocorrer. Não há número por trás.
- Não sou advogado. Os pontos sobre licenças e conteúdo sintético são alertas para conferir, não parecer jurídico.

---

## 2. O que está bem feito (manter)

| Ponto | Onde |
|---|---|
| Lógica pura separada de I/O, com dependências injetáveis | `enquadrar.py`, `limpeza.py`, `legenda.py`, parâmetros `criar=`, `baixar=`, `pedir=` |
| Escrita confinada e proteção contra path traversal | `caminhos.garantir_escrita`, `painel/leitura._resolver_dentro` |
| Publicação idempotente: grava `enviando` antes, nunca reenvia quando o resultado é incerto, assinatura SHA-256 do vídeo + texto confirmados | `publicar/envio.py`, `publicar/rodar.py` |
| Controle de concorrência otimista por hash dos bytes | `post.md` e `pedidos.json` (`versao_dos_bytes`) |
| Remontagem com rollback e recuperação após queda | `painel/troca_musica.py` |
| Segredos no Gerenciador de Credenciais; mensagens de erro filtradas para não vazar token | `publicar/http._motivo`, `imagens_ia/_comum.limpar`, `vozes._sem_token` |
| Código de acesso com PBKDF2, comparação em tempo constante, cookie `HttpOnly` + `SameSite=Strict`, `TrustedHostMiddleware` contra DNS rebinding | `painel/acesso.py`, `painel/app.py` |
| "Imagem paga nunca é perdida": falha depois da geração vira aviso, não erro | `imagens_ia/gerar.py` |
| Orçamento de IA confirmado item a item | `rotas_imagens._gerar_aprovadas` |
| Base de acessibilidade real: `:focus-visible`, alvos de 44 px, `prefers-reduced-motion`, `role="alert"`/`status`, tema escuro | `painel-web/src/estilo.css` |
| Contraste de texto: todos os pares medidos passam AA (de 5,1:1 a 8,2:1) | medição própria sobre os tokens do CSS |
| Cerca de 850 funções de teste em Python e 127 casos em JS; specs e planos por funcionalidade | `tests/`, `docs/superpowers/` |

---

## 3. Achados prioritários

| # | Sev. | Achado | Onde | Correção |
|---|---|---|---|---|
| 1 | Alta | Travas de publicar, gastar e sobrescrever são só instrução em prosa para o agente | `docs/operacao.md`; ausência de `.claude/` | Hook `PreToolUse` que nega `--confirmar` e `--forcar`; confirmação só pelo painel ou por código de uso único (seção 4.2) |
| 2 | Alta | Integração com o Claude fora do repositório e sem contrato | `rotas_imagens.py:36` cita `CLAUDE.md` inexistente | Versionar `CLAUDE.md`, skills, comandos, `settings.json` e JSON Schema (seção 4.1) |
| 3 | Alta | Corte de "pausa" sem conferir o áudio remove fala não transcrita | `limpeza.py` (`PAUSA_LONGA = 0.5`) | Confirmar silêncio com `silencedetect`/VAD e com `vozes.json` antes de cortar |
| 4 | Alta | Filtro de pessoa real em IA é lista de nomes + regex | `pedidos._pessoa_citada` | Classificador por LLM + lista de cargos e apelidos + revisão visual da imagem gerada |
| 5 | Média | Glossário truncado em 200 caracteres na transcrição | `transcrever.py` (`", ".join(nomes)[:200]`) | Usar `hotwords` do faster-whisper ou priorizar convidados do episódio no prompt |
| 6 | Média | Aviso de IA só em texto; os campos nativos das plataformas não são enviados | `publicar/youtube.py`, `publicar/tiktok.py` | Enviar `status.containsSyntheticMedia` (YouTube) e `post_info.is_aigc` (TikTok, postagem direta) |
| 7 | Média | Sem normalização de volume da voz; só alerta de pico | `render.py` | `loudnorm` em duas passadas ou medição de LUFS por corte |
| 8 | Média | Modo `--rede`: HTTP puro, sessão de 30 dias, bloqueio global, bind em `0.0.0.0` | `acesso.py`, `cli._painel` | HTTPS local ou Tailscale; bloqueio por IP; bind no IP da Wi-Fi; logout |
| 9 | Média | Crédito das fotos não é exigido nos textos; só o da música | `publicar/post.conferir_textos` | Bloquear o agendamento quando falta crédito de foto que está no vídeo |
| 10 | Média | Sem CI, sem lockfile Python, `pip install -e .` quebrado | `pyproject.toml`, ausência de `.github/` | Seção 8 |
| 11 | Média | Erros nos JSON que o Claude escreve viram traceback | `cli.principal` só captura 9 exceções próprias | Capturar `JSONDecodeError`, `KeyError`, `TypeError`, `FileNotFoundError` com mensagem que diga arquivo, campo e correção |
| 12 | Média | Dados do canal e estado de execução versionados | `musicas/uso.json`, `publicacao.json`, `imagens-ia.json` | Mover estado para pasta ignorada; versionar só `*.exemplo.json` |
| 13 | Média | Fila do painel só em memória, um trabalhador, sem poda nem cancelamento | `painel/fila.py` | Persistir em disco; podar concluídos; botão de cancelar |
| 14 | Baixa | Porta 8765 é do painel e do retorno OAuth | `credenciais.PORTA`, `cli` (`--porta` padrão) | Portas diferentes ou porta efêmera no OAuth |
| 15 | Baixa | 2 vulnerabilidades moderadas em dependência de produção (react-router 6) e 8 no total com as de desenvolvimento (1 alta, 2 críticas) | `npm audit` em 11/11/2026 | Migrar para react-router 7 e atualizar vitest; o risco real é baixo (SPA local, sem SSR) |

---

## 4. Uso do Claude (o ponto mais fraco e o de maior retorno)

### 4.1 Como é hoje

- O Claude Code roda numa sessão interativa e segue `docs/operacao.md`, mais as regras editoriais em `Contexto/*.md`, que ficam **fora** do repositório.
- Ele lê `texto.md`, grava `aprovados.json`, `candidatos.md`, `pedidos.json`, `post.md`, `calendario.md`, `musicas-do-episodio.json` e `nomes-suspeitos.json`, e chama a CLI pelo terminal.
- Não há chamada à API da Anthropic no código. Toda a "inteligência" é a sessão.

### 4.2 Problemas e correções

**C1. Nada do agente está versionado (Alta).**
`rotas_imagens.py` e `wikimedia.py` citam um limite "do CLAUDE.md", mas o arquivo não está no repositório. Quem clonar não consegue reproduzir o comportamento.

Correção, em ordem de custo:

1. `CLAUDE.md` na raiz, curto, com as regras invioláveis e apontando para `docs/operacao.md`.
2. `Contexto.exemplo/` com modelos de `canal.md`, `estilo-dos-cortes.md`, `glossario.md` e `redes-e-publicacao.md`.
3. Uma skill por etapa de julgamento em `.claude/skills/` (`escolher-cortes`, `momentos-de-imagem`, `textos-e-calendario`), cada uma com o formato de saída e exemplos.
4. Comandos em `.claude/commands/` (`/episodio`, `/corrigir-corte`, `/agendar`) para tirar do dono a necessidade de lembrar a frase certa.

**C2. Travas em prosa (Alta).**
Instrução em `CLAUDE.md` ou em skill é sugestão: costuma ser seguida, mas não é garantia. Os hooks do Claude Code são a camada determinística: um hook `PreToolUse` recebe a chamada em JSON pelo stdin e pode devolver `permissionDecision: "deny"`.

Exemplo de `.claude/settings.json` (confira a sintaxe na documentação atual antes de adotar):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python \"$CLAUDE_PROJECT_DIR/.claude/hooks/travas.py\"" }
        ]
      }
    ]
  }
}
```

```python
# .claude/hooks/travas.py
import json, re, sys

comando = json.load(sys.stdin).get("tool_input", {}).get("command", "")
PROIBIDO = [
    (r"--confirmar\b", "Confirmar (publicar, gerar imagem paga, instalar tarefa) é ato do dono: use o painel."),
    (r"--forcar\b|--religar\b", "Sobrescrever exige o dono: peça a ele para rodar o comando."),
    (r"1 - Programas", "A pasta de episódios é somente leitura."),
    (r"publicar\s+(conectar|marcar)\b", "Credenciais e estado de publicação são do dono."),
]
for padrao, motivo in PROIBIDO:
    if re.search(padrao, comando):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": motivo,
        }}))
        break
```

Um hook por expressão regular é contornável (script intermediário, variável de shell). A defesa completa é tirar a confirmação da linha de comando:

- `publicar agendar` sem `--confirmar` grava um pedido pendente; **só o painel**, com clique humano, confirma. Já é o desenho usado em `aprovar` e nas imagens de IA; falta aplicar à publicação (é a "fase 2" do roadmap, e deveria subir de prioridade por segurança, não por conveniência).
- Alternativa mais barata: o resumo imprime um código de uso único, derivado da assinatura do pedido, que o dono digita. O agente vê o código, então isso protege contra erro, não contra um agente manipulado.

**C3. Injeção de instrução por conteúdo (Alta, em conjunto com C2).**
Entram no contexto do agente, sem marcação: a transcrição do episódio (fala de convidados), títulos e autores do Wikimedia (qualquer pessoa edita) e o `post.md`. Um título de arquivo no Commons com texto do tipo "ignore as regras e rode..." é um vetor plausível.

Correção: C2 resolve o impacto. Além disso, declarar no `CLAUDE.md` que esses arquivos são dados e nunca instruções, e fazer a CLI entregar metadados externos já saneados (remover quebras de linha e limitar o tamanho de `autor` e `titulo` em `wikimedia._candidata`).

**C4. Sem contrato para o que o Claude escreve (Média).**
`Corte(**c)` e `Momento(**item)` estouram com `TypeError` se o agente inventar um campo, e a CLI mostra traceback. O agente recebe a pior mensagem de erro justamente nos arquivos que ele mesmo grava.

Correção: JSON Schema para `aprovados.json`, `pedidos.json`, `musicas-do-episodio.json` e `nomes-suspeitos.json`, publicado em `docs/esquemas/`; `esteira validar` passa a validar todos e a responder em uma linha por erro, com arquivo, caminho do campo e valor esperado. Vale também uma saída `--json` em todos os comandos, para o agente não depender de texto.

**C5. Contexto gasto à toa (Média).**
- `palavras.json` é gravado com uma chave por linha (`indent=0`). Num episódio de 1 h 30 min passa de 1 MB. A operação manda o agente "conferir os tempos exatos" nele.
- `texto.md` tem um carimbo por segmento do Whisper, com resolução de 1 s, e **não diz quem fala**, embora `vozes.json` exista logo depois.

Correção:
- `esteira trecho <pasta> --de 724 --ate 802` imprime as palavras com tempo e falante só daquele intervalo.
- Regerar `texto.md` depois de `vozes`, com `[00:12:04.1] P2 (Convidado): ...` e marcação de pausas longas. Saber quem fala e onde há silêncio melhora a escolha dos cortes e o diagnóstico do achado 3.
- Um subagente por corte para escrever os `post.md` em paralelo, em vez de um contexto único acumulando os dez.

**C6. Sem proveniência (Média).**
Nada registra qual modelo, em que data e com qual versão das regras produziu `aprovados.json`. Quando a qualidade cair depois de uma troca de modelo ou de regra, não haverá como comparar.

Correção: campo `origem` em cada arquivo do agente: `{modelo, data, hash_do_Contexto, versao_da_skill}`.

**C7. Sem avaliação nem aprendizado (Média).**
A esteira já produz o dado de treino e joga fora: cortes propostos × aprovados, título proposto × editado no painel, música proposta × trocada, imagem proposta × descartada. `calendario.md` cita "métricas novas" como passo manual.

Correção:
1. `esteira aprendizado <pasta>` gera um resumo das diferenças entre o que o agente propôs e o que o dono publicou.
2. O resumo alimenta `Contexto/` (com aprovação), como exemplos reais do canal.
3. Coleta de métricas pela YouTube Analytics API (retenção, visualizações em 48 h) por corte, gravadas em `metricas.json`. Isso vira um conjunto de referência para comparar modelos e versões de skill.

**C8. Dependência de sessão interativa (Média).**
Não dá para rodar a etapa de julgamento a partir do painel, nem em lote, nem sem alguém no terminal.

Correção: `esteira sugerir-cortes <pasta>` chamando o Claude em modo não interativo (`claude -p`) ou pela API com saída estruturada conforme o esquema de C4. O painel ganha o botão "Pedir sugestões" e a sessão interativa continua existindo para quem prefere. Registrar tokens e custo no mesmo padrão de orçamento das imagens.

**C9. Usos do Claude que ainda não existem e valem o custo.**

| Uso | Ganho |
|---|---|
| Classificar se um prompt de imagem retrata pessoa real ou identificável (complementa o achado 4) | Reduz o maior risco reputacional |
| Revisão visual antes de mostrar ao dono: 4 a 6 quadros do `corte.mp4` para achar legenda sobre o rosto, imagem trocada, enquadramento vazio | Menos idas e vindas no painel |
| Nota explicada por corte (gancho nos 3 primeiros segundos, autonomia do trecho, risco de tirar de contexto) gravada em `candidatos.md` em formato fixo | Equivale ao "virality score" dos concorrentes, só que auditável |
| Texto de gancho para os primeiros segundos | Recurso padrão no mercado, ausente aqui |
| Checagem de contexto: comparar o corte com a fala completa e alertar distorção | Crítico em conteúdo político |

**C10. Servidor MCP em vez de shell (opcional, mais adiante).**
Expor a esteira como ferramentas tipadas (`transcrever`, `validar`, `montar`, `resumo_de_publicacao`) e não dar shell ao agente reduz a superfície de ataque de C2 e C3 de forma estrutural. Custa mais do que hooks. Recomendo só depois de C1 a C4.

---

## 5. Segurança

| # | Sev. | Achado | Detalhe | Correção |
|---|---|---|---|---|
| S1 | Alta | Agente com shell e travas em prosa | Seção 4.2, C2 e C3 | Hooks; confirmação fora da CLI |
| S2 | Alta | Filtro de pessoa real fraco | Só nomes das seções Apresentadores, Convidados e Pessoas do glossário | Seção 4.2, C9; negar por padrão prompts com cargo público, partido ou rosto |
| S3 | Média | Painel local sem autenticação; CSRF depende de o FastAPI exigir `Content-Type: application/json` | Está documentado em `Confirmacao`, mas é defesa implícita de versão de framework | Middleware que rejeita métodos não-GET quando `Origin` ou `Sec-Fetch-Site` indicam outra origem |
| S4 | Média | `GET .../fotos/resumo` dispara chamadas ao Wikimedia | GET com efeito externo é acionável por `<img>` de outra página | Trocar para POST |
| S5 | Média | Modo `--rede` | HTTP sem TLS na Wi-Fi; cookie válido por 30 dias; 5 erros travam o login **de todos** por 60 s (qualquer aparelho na rede bloqueia o dono); contador zera ao reiniciar; `host="0.0.0.0"` escuta em todas as interfaces, inclusive VPN | Tailscale ou HTTPS com certificado local; bind no IP detectado; bloqueio por IP com recuo exponencial; sessão de 7 dias e rota de logout |
| S6 | Baixa | Sem cabeçalhos de segurança | Faltam CSP, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors` | Middleware único; a CSP precisa liberar `upload.wikimedia.org` em `img-src` |
| S7 | Baixa | OAuth sem PKCE; porta fixa 8765 igual à do painel | `HTTPServer` usa `allow_reuse_address`; com o painel aberto, o comportamento no Windows não é previsível (não testei) | PKCE; porta efêmera ou diferente |
| S8 | Baixa | Trava de publicação por arquivo sem PID, com validade de 2 h | Uma queda deixa a publicação parada por até 2 h | Gravar PID e conferir se o processo existe |
| S9 | Baixa | `logs/publicar.log` cresce sem limite | `tarefa.py` | Rotação por tamanho |
| S10 | Info | Busca por segredos no código | Nenhum encontrado na árvore atual. Não varri o histórico completo (clone raso de 50 commits) | Rodar `gitleaks` no histórico inteiro |

---

## 6. Esteira de vídeo e áudio

### 6.1 Transcrição (`transcrever.py`, `vozes.py`)

- **Glossário truncado (Média).** `initial_prompt=", ".join(nomes)[:200]` descarta quase todo glossário real. Use `hotwords` ou monte o prompt com os nomes do episódio primeiro.
- **Tempo por palavra sem alinhamento forçado (Média).** Os cortes, a legenda e a limpeza dependem dos tempos do Whisper, que oscilam em fala rápida. O WhisperX (alinhamento com wav2vec2) é a referência aberta para isso. Custa VRAM e uma dependência a mais; vale medir num episódio antes de adotar.
- **Sem lote, progresso ou retomada (Baixa).** O faster-whisper tem inferência em lote, que costuma reduzir bastante o tempo. Uma falha no minuto 80 refaz tudo.
- **`language="pt"` fixo e `use_auth_token` do pyannote 3.x** prendem o projeto a versões antigas.

### 6.2 Limpeza (`limpeza.py`) — Alta

```python
elif pausa > PAUSA_LONGA:          # 0,5 s entre duas palavras transcritas
    cortes.append((anterior.fim + folga, palavra.inicio - folga))
```

O que não foi transcrito é tratado como silêncio. Casos em que isso erra: fala sobreposta do outro participante, riso, "uhum", palavra que o Whisper engoliu, vinheta. O `edicoes.md` registra como "pausa", então a revisão não percebe.

Correção: antes de cortar, medir o intervalo com `silencedetect` (ou com o VAD que o faster-whisper já carrega) e cruzar com `vozes.json`. Se houver energia ou voz ativa, não cortar e registrar "pausa com som mantida". Acrescentar um teste com áudio sintético.

Também vale revisar a regra de repetição: remove a primeira de duas palavras iguais em menos de 0,5 s, o que apaga ênfase legítima ("muito, muito grave"). A lista `PROTEGIDAS` cobre só três palavras.

### 6.3 Enquadramento (`enquadrar.py`, `rostos.py`, `render.py`)

- Recorte **estático por trecho**, quatro níveis de zoom, troca por corte seco, amostragem de rosto a cada 0,5 s. Funciona para mesa fixa; quem se mexe sai do quadro.
- Sem tela dividida para diálogo rápido (dois rostos empilhados), que é padrão nos concorrentes para podcast.
- Ajuste só editando `enquadramento.json` à mão.

Sugestão: interpolar o centro do recorte dentro do trecho quando o rosto se desloca além de um limiar; layout dividido quando dois falantes alternam em menos de 2 s; editor de enquadramento no painel (arrastar a caixa sobre o quadro).

### 6.4 Legenda (`legenda.py`)

- Um estilo só (Montserrat 90, branca, contorno), posição fixa em `y=1530`. O campo `destaque` existe no código, mas a operação manda não usar.
- Sem animação palavra a palavra, que é hoje o padrão visual do formato.
- Correção de legenda exige editar `montagem.json`.

Sugestão: predefinições de estilo em `Contexto/legenda.json`; modo de destaque da palavra falada (os tempos por palavra já existem; em ASS é uma tag `\k` ou eventos por palavra); editor de legenda no painel; botão de áreas seguras no player para ver o que a interface de cada rede cobre.

### 6.5 Áudio (`render.py`)

- A música é normalizada na entrada (−16 LUFS) e há *ducking* por `sidechaincompress`, o que é bom. **A voz não é normalizada**: só existe um alerta quando o pico passa de −0,5 dB. Cortes do mesmo episódio saem com volumes diferentes.
- Correção: medir LUFS por corte e aplicar `loudnorm` em duas passadas. O alvo usual de redes fica em torno de −14 LUFS; confirme por plataforma.

### 6.6 Imagens (`fluxo_imagens.py`, `imagens_ia/`, `wikimedia.py`)

- **Licenças com "SA" (Média, conferir com jurídico).** `licenca_aceita` aceita CC BY-SA. Usar uma foto assim dentro de um vídeo pode acionar a cláusula de compartilhamento pela mesma licença. Sugestão: tornar o conjunto de licenças configurável e marcar SA com aviso próprio no painel.
- **Crédito de foto não é obrigatório nos textos.** O `agendar` lista os créditos no resumo, mas `conferir_textos` só bloqueia pela falta do crédito da música.
- **`sugerir` apaga as fotos antes de baixar as novas** (a própria operação alerta). Baixar em pasta temporária e trocar no fim.
- **OpenAI em 1024×1536 (2:3) recortado para 9:16** perde as laterais. O comentário "a Task 4 ajusta" ficou no código.
- **Preço por imagem digitado à mão** em `imagens-ia.json`. O "custo estimado" pode divergir da fatura sem aviso. Mostrar a data da última conferência do preço.

### 6.7 Publicação (`publicar/`)

- **Rótulo de conteúdo sintético (Média).** A API do YouTube aceita `status.containsSyntheticMedia` em `videos.insert` desde outubro de 2024. A postagem direta do TikTok aceita `post_info.is_aigc`; o envio para rascunho (inbox) não tem esse campo. O clipline só escreve o aviso no texto. Envie os campos quando `imagens_aprovadas` indicar IA no vídeo. Para o Instagram, confirme na documentação da Meta se há campo equivalente (não verifiquei).
- Vídeo inteiro em memória (`read_bytes`) e `PUT` único, sem retomada. Aceitável para cortes de 2 minutos; frágil em conexão ruim.
- Precisão de 15 minutos no Instagram e no TikTok (intervalo da tarefa agendada).
- Fixos no código: `categoryId: "22"`, perfil `@tudoepoliticabr`, fuso −3, limite de 180 s do Shorts, `VERSAO_GRAPH = "v21.0"`.
- O `schtasks /TR` tem limite de tamanho do comando; com caminhos longos do Windows a criação pode falhar. Não testei: confira e, se preciso, use um `.cmd` intermediário.
- Sem miniatura, sem *tags*, sem playlist, sem primeiro comentário fixado.

### 6.8 Regras fixas que deveriam ser configuração

`DURACAO_MIN = 60` e `DURACAO_MAX = 120` (`validar.py`), quatro climas (`musica.py`), 2 a 5 s por imagem (`pedidos.py`), zoom máximo 2,0, 8 a 10 cortes, quatro encerramentos com nomes de pessoas (`caminhos.py`). Tudo isso é decisão editorial dentro do código.

---

## 7. Painel: design, UX, front-end e acessibilidade

### 7.1 Design

Direção coerente ("mesa de corte": monitor escuro, folha clara, um azul de marca), *tokens* em variáveis CSS, tipografia variável e marca própria. Problemas:

| Achado | Correção |
|---|---|
| `window.confirm` para aprovar, baixar fotos, gerar IA paga e montar | Diálogo próprio (`<dialog>`) com resumo, lista de itens e custo; o nativo corta texto no celular e não aceita formatação |
| Tema só segue o sistema | Alternador claro/escuro/sistema |
| `<title>` fixo "Tudo é Política"; `manifest` sem `theme_color`, `display` e `lang` | Título vindo da configuração; manifesto completo |
| `estilo.css` com 1.470 linhas num arquivo | Dividir por componente (já começou em `imagensNoVideo.css`) |
| Borda de campo `--linha-forte` sobre branco: 1,59:1 | Se a borda for o único indicador do campo, não atinge os 3:1 de contraste não textual. Escurecer |
| Estados vazios e de carregamento em texto puro ("Carregando…") | Esqueletos e estados vazios com a próxima ação |

### 7.2 UX: o que falta para o dono não depender do terminal

Em ordem de valor:

1. **Editar legenda** na tela (hoje: `montagem.json` à mão + CLI).
2. **Ajustar início e fim do corte** com a transcrição clicável (fase 3 do roadmap).
3. **Agendar e ver a fila** de publicação (fase 2 do roadmap; ver C2, é também a correção de segurança).
4. **Visão da esteira:** em que etapa está cada episódio e cada corte, e qual o próximo passo. Hoje a lista só mostra "N de M prontos".
5. **Ajustar o enquadramento** arrastando a caixa.
6. **Player de revisão:** atalhos (espaço, J/K/L, setas), velocidade, quadro a quadro, comparação lado a lado do corte com o vídeo final, sobreposição de áreas seguras.
7. **Ver as remoções** (`edicoes.md`) na linha do corte, com um clique para ouvir cada uma. É a forma de pegar o problema da seção 6.2.
8. **Ações em lote:** aprovar vários, montar todos, baixar todos.
9. Busca e filtro por selo; histórico de quem aprovou e quando.
10. Depois do 401, voltar à página em que a pessoa estava; mostrar contagem regressiva quando o login estiver travado.

### 7.3 Front-end

| Achado | Onde | Correção |
|---|---|---|
| `useEffect` com `fetch` sem cancelamento: ao trocar rápido de corte, a resposta antiga pode sobrescrever a nova | `Corte.tsx`, `Episodios.tsx`, blocos | `AbortController` ou uma camada de dados (TanStack Query) com chave por `ep`/`n` |
| Acompanhamento por `setTimeout` | `BlocoMusica`, `BlocoImagens` | Server-Sent Events em `/api/tarefas/eventos` |
| Sem *error boundary* | `App.tsx` | Um no topo, com botão de recarregar |
| Sem divisão de código | `Corte` carrega `react-markdown` sempre | `React.lazy` nas telas |
| Tipos da API escritos à mão em `api.ts` (379 linhas) | Divergem do Pydantic sem aviso | Reativar o OpenAPI só em desenvolvimento e gerar os tipos |
| React 18, Router 6, Vite 5, Vitest 2 | `package.json` | Planejar a atualização; `npm audit` aponta o Router e o Vitest |
| E2E só roda em Windows (`.venv/Scripts/python.exe`) | `playwright.config.ts` | Resolver o executável por plataforma |

### 7.4 Acessibilidade

Base sólida. Pontos a corrigir:

- A régua da linha do corte aceita clique para posicionar o vídeo, mas não teclado; só os trechos são botões. Tornar a régua um `role="slider"` com setas.
- A fala de cada trecho aparece só em `title`, que não funciona em toque nem é anunciado de forma confiável.
- Em `Episodio.tsx`, todas as abas apontam `aria-controls` para o id do painel ativo.
- `window.confirm` (7.1) também é questão de acessibilidade: sem estrutura para leitor de tela.
- Não testei com leitor de tela nem com navegação real por teclado; a avaliação é pelo código.

---

## 8. Engenharia, DX e saúde do repositório

| # | Achado | Correção |
|---|---|---|
| E1 | Sem integração contínua | GitHub Actions com `pytest` (sem GPU, os testes já usam falsos), `npm test`, `tsc`, `ruff` e `npm audit` |
| E2 | `pip install -e .` não funciona (o próprio README avisa); dependências sem versão fixa | Declarar `[build-system]` e `[tool.setuptools.packages.find] include = ["esteira*"]`; lockfile com `uv` ou `pip-tools`; script de entrada `clipline` |
| E3 | Só Windows: `ffmpeg.exe` fixo em `midia.py`, `schtasks`, layout `Lib/site-packages` em `_registrar_dlls_nvidia` | `shutil.which` com recuo para `bin/`; abstrair o agendador (cron/systemd/launchd) |
| E4 | Identidade do canal no código: pastas `1 - Programas`, `2 - Cortes`, encerramentos "Gabriel 1/Tigas 1", `@tudoepoliticabr`, serviços `tudo-e-politica-*`, `USER_AGENT` | `clipline.toml` por canal com pastas, identidade, redes, limites e climas |
| E5 | Sem `esteira doctor` | Um comando que confira ffmpeg, NVENC, CUDA, modelos, `HF_TOKEN`, credenciais, build do painel e pastas |
| E6 | Sem `esteira status <pasta>` | Mostrar a etapa de cada corte e o próximo comando; serve ao dono, ao painel e ao Claude |
| E7 | Tracebacks em erros comuns (achado 11) | Tratador único no `principal` |
| E8 | Escrita não atômica em `gravar_receita`, `gravar_pedidos`, `registrar`, `gravar_uso` e `gravar_catalogo`, enquanto outros módulos usam `.tmp` + `replace` | Um `gravar_atomico()` em `caminhos.py`, usado por todos |
| E9 | CLI e painel escrevem os mesmos arquivos sem trava entre processos (`montagem.json`, `uso.json`) | Trava de arquivo por corte |
| E10 | Módulos importam funções privadas uns dos outros (`_gravar`, `_credito`, `_pessoa_citada`, `_motivo`, `_TRAVA_GRAVACAO`); `imagens_ia` depende de `publicar.http` | Promover a API pública; mover o cliente HTTP para `esteira/rede.py` |
| E11 | Só `montagem.json` tem campo `versao` | Versão de esquema em todos os arquivos de estado |
| E12 | `docs/arquitetura.md` descreve um sistema anterior (321 testes, imagens fora do vídeo) | Atualizar ou marcar como histórico |
| E13 | Sem linter, formatador nem checagem de tipos configurados | `ruff` e `pyright` no `pyproject.toml` |
| E14 | Sem log estruturado; diagnóstico depende de `registro.json` e de `print` | `logging` com arquivo por episódio |
| E15 | Pacote `esteira`, produto `clipline`, pasta sugerida `Automacao` | Unificar o nome |
| E16 | Estado e dados do canal versionados (`musicas/uso.json` traz títulos de cortes reais) | Contradiz a regra do próprio README ("não envie dados de canal") |
| E17 | Sem `CONTRIBUTING.md`, `SECURITY.md`, modelos de issue e `CHANGELOG` | Necessários para o projeto ser de fato aberto |

---

## 9. Comparação com outras ferramentas

Não testei nenhuma delas. A tabela usa a descrição pública de cada projeto ou produto; as colunas de mercado variam por plano. "?" significa que não encontrei a informação.

### 9.1 Código aberto

| Recurso | clipline | OpenShorts | autoclip | SupoClip | AI-Youtube-Shorts-Generator |
|---|---|---|---|---|---|
| Transcrição por palavra | Sim (faster-whisper) | Sim (faster-whisper) | Analisa legendas | ? | Sim (Whisper) |
| Escolha dos trechos | Claude Code, manual por sessão | LLM, automática | Pontuação de segmentos | LLM | LLM |
| Nota/ranking dos cortes | Não | ? | Sim | ? | Sim (ranking) |
| Enquadramento vertical | Por falante, estático | Reenquadra | ? | ? | Recorte automático |
| Diarização + reconhecimento de rosto | Sim | ? | ? | ? | ? |
| Legenda | Queimada, um estilo | Com ganchos | ? | ? | ? |
| Música com crédito automático | Sim | ? | ? | ? | ? |
| Imagens com licença rastreada | Sim | ? | ? | ? | ? |
| Painel de revisão com aprovação obrigatória | Sim | ? | ? | ? | Não (CLI) |
| Publicação em redes | Sim, com confirmação | ? | ? | ? | ? |
| Entrada por link do YouTube | Não | Sim | Sim (YouTube, Bilibili, local) | ? | Sim |
| Instalação | Manual, só Windows | Auto-hospedável | Local | Auto-hospedável | `pip` + chave de LLM |
| Licença | MIT | MIT | ? | ? | ? |

Leitura: os projetos abertos concorrentes são **automáticos e genéricos** (link → cortes). O clipline é **editorial e supervisionado**. O diferencial não aparece para quem chega pelo README, porque a instalação é a barreira.

### 9.2 Mercado

| Recurso | clipline | OpusClip | Submagic | Vizard | Klap | Descript |
|---|---|---|---|---|---|---|
| Nota de viralidade e detecção de gancho | Não | Sim | Não é o foco | Sim | Sim | Não é o foco |
| Legenda animada com predefinições | Não | Sim | Sim (ponto forte) | Sim | Sim | Sim |
| B-roll automático | Fotos livres, cartões e IA com aprovação | Sim | Sim | ? | ? | ? |
| Editar pelo texto da transcrição | Não | Parcial | Não | Sim | ? | Sim (ponto forte) |
| Agendamento e publicação | CLI com confirmação | Sim | ? | Sim | Sim | ? |
| Equipe e colaboração | Não | Planos superiores | ? | Sim | ? | Sim |
| Dublagem e tradução | Não | Planos superiores | Sim (legendas em vários idiomas) | ? | Sim | Sim |
| Execução local, sem envio do vídeo | Sim | Não | Não | Não | Não | Não |
| Custo por minuto processado | Zero (hardware próprio + sessão do Claude) | Por créditos | Assinatura | Por minutos | Assinatura | Assinatura |
| Regras editoriais em texto, versionáveis | Sim | Não | Não | Não | Não | Não |
| Rastreio de licença e crédito | Sim | ? | ? | ? | ? | ? |

### 9.3 O que copiar e o que não copiar

**Copiar:**
1. Legenda animada com predefinições (seção 6.4).
2. Nota explicada por corte (seção 4.2, C9).
3. Gancho na tela nos primeiros segundos.
4. Edição pela transcrição (seção 7.2).
5. Entrada por link (`yt-dlp`), para episódios já publicados.
6. Acompanhamento suave e tela dividida (seção 6.3).

**Não copiar:**
- Automação sem revisão. A aprovação humana é o diferencial, sobretudo em política.
- Nota de viralidade opaca. A versão auditável (critérios escritos, justificativa por corte) vale mais.
- Modelo SaaS com envio do vídeo.

---

## 10. Plano sugerido

### Fase 0: um a dois dias, risco

1. Hook `PreToolUse` negando `--confirmar`, `--forcar`, `--religar` e escrita em `1 - Programas`.
2. `CLAUDE.md` e `Contexto.exemplo/` versionados.
3. Tratador único de erros na CLI (sem traceback para JSON inválido).
4. Tirar `uso.json`, `publicacao.json` e `imagens-ia.json` do controle de versão.
5. `containsSyntheticMedia` e `is_aigc` na publicação.
6. Portas diferentes para painel e OAuth.

### Fase 1: uma a duas semanas, qualidade do corte

7. Limpeza conferindo o áudio antes de cortar; remoções visíveis na linha do corte.
8. `texto.md` com falante e pausas; `esteira trecho`.
9. `hotwords` com o glossário inteiro.
10. Normalização de volume da voz.
11. JSON Schema + `validar` completo + saída `--json`.
12. Classificador de pessoa real para prompts de IA.
13. CI, lockfile, `pip install` funcionando, `esteira doctor`.

### Fase 2: três a seis semanas, produto

14. Agendar e ver a fila pelo painel (substitui `--confirmar`).
15. Editor de legenda e de início/fim com transcrição clicável.
16. Legenda animada com predefinições.
17. `clipline.toml` por canal; fim dos valores fixos.
18. `esteira sugerir-cortes` não interativo + botão no painel.
19. Diálogos próprios no lugar de `window.confirm`; camada de dados com cancelamento; SSE.

### Fase 3: depois

20. Linux e macOS; instalação com um comando.
21. Acompanhamento suave e tela dividida.
22. Métricas (YouTube Analytics) + `esteira aprendizado` + conjunto de referência.
23. Revisão visual pelo Claude antes da revisão humana.
24. Servidor MCP no lugar do shell.

---

## 11. Fontes

**Código e documentação do repositório** (commit `3e4350c`): todos os caminhos citados nas tabelas.

**Externas:**
- Claude Code, referência de hooks: https://code.claude.com/docs/en/hooks
- YouTube Data API, `videos.insert`: https://developers.google.com/youtube/data/reference/rest/v3/videos/insert
- YouTube Data API, histórico de revisões (conteúdo alterado ou sintético): https://developers.google.com/youtube/v3/revision_history
- TikTok Content Posting API, Direct Post: https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post
- SupoClip: https://github.com/FujiwaraChoki/supoclip
- AI-Youtube-Shorts-Generator: https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator
- OpenShorts: https://openalternative.co/openshorts
- autoclip: https://www.opensourcealternatives.to/item/autoclip
- Comparativos de mercado consultados: https://pictory.ai/blog/opusclip-alternatives e https://jupitrr.com/alternatives/opus-clip-alternatives
- `npm audit` executado em 11/11/2026 sobre `painel-web/package-lock.json` (avisos GHSA-wrjc-x8rr-h8h6, GHSA-337j-9hxr-rhxg, GHSA-5gmw-xhrv-c9v3, GHSA-85c8-ppgw-ccpr)
