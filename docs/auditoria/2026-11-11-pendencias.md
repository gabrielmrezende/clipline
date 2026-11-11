# Auditoria do clipline: o que foi feito e o que falta

**Data:** 11/11/2026
**Base:** [`2026-11-11-auditoria-inicial.md`](2026-11-11-auditoria-inicial.md) (commit `3e4350c`)
**Mudanças:** branch `melhorias-auditoria` (versão 0.2.0, ver [`CHANGELOG.md`](../../CHANGELOG.md))

---

## 1. Resumo

Dos 15 achados prioritários da auditoria inicial, **12 foram resolvidos** e **3 foram resolvidos em parte**.
Também entraram itens das seções de agente, segurança, esteira, painel e repositório que não estavam entre os 15.
O que falta está na seção 4, com o motivo de cada pendência e a ordem sugerida.

O maior risco que sobra é **o código não ter rodado num episódio real no Windows depois das mudanças**. Os testes
rodaram em Linux (seção 2); o ambiente do canal (Windows, GPU, `bin/ffmpeg.exe`, credenciais, Agendador de Tarefas)
não estava disponível. Antes de usar num episódio, rode o roteiro da seção 5.

## 2. O que foi verificado e como

| Verificação | Resultado | Onde rodou |
|---|---|---|
| `pytest` da esteira e da API (suíte inteira, incluindo render real com ffmpeg) | 1.069 passaram; detalhe no fim desta seção | Linux, Python 3.13, ffmpeg 6.1 do sistema, 2 núcleos, sem GPU |
| `ruff check` (erros reais: sintaxe, nomes, argumentos mutáveis) | sem erros | Linux |
| `tsc -b` do painel | sem erros | Node 22 |
| Vitest do painel | 143 testes, todos passando | Node 22, jsdom |
| `npm run build` | ok | Node 22 |
| Playwright (6 testes, incluindo os 3 novos) | todos passando | Chromium 1243 do ambiente, painel real servido pelo uvicorn |
| `pip install -e .` e o comando `clipline doctor` | ok | venv limpo, Linux |

Não foi verificado: o hook dentro de uma sessão real do Claude Code (só a lógica e o formato de saída, por teste),
o workflow do GitHub Actions rodando no GitHub, chamadas reais às APIs do YouTube, TikTok, Instagram, OpenAI e Google,
e o comportamento no Windows.

Antes das mudanças, 59 testes falhavam fora do Windows (caminho fixo `bin/ffmpeg.exe`), 6 dependiam do `Contexto/`
real do canal e 1 teste de front já falhava no Node 22 (Blob do jsdom). Os três problemas foram corrigidos.

Resultado da suíte Python completa nesta rodada: **1.069 testes passaram, 1 falhou e 2 foram pulados** (26 min, 2
núcleos). A falha precisava do logo real do canal (`3 - Identidade/Logos/Logo sem Fundo.png`); agora o teste é pulado
fora da máquina do canal, como o de pastas. Os 5 testes de `test_agente.py`, escritos depois do início dessa rodada,
passam à parte.

## 3. O que foi feito

### 3.1 Achados prioritários

| # | Achado | Situação | O que mudou |
|---|---|---|---|
| 1 | Travas do agente só em prosa | Feito | Hook `PreToolUse` em `.claude/hooks/travas.py` (falha fechada, 31 testes) e confirmação de publicação pelo painel, com a marca do resumo exato |
| 2 | Integração com o Claude fora do repositório | Feito | `CLAUDE.md`, 3 skills, 3 comandos, `.claude/settings.json`, `Contexto.exemplo/`, JSON Schema em `docs/esquemas/` |
| 3 | Limpeza corta fala não transcrita | Feito | `silencedetect` no áudio + `vozes.json` antes de cortar; "pausa com som mantida" no `edicoes.md`; teste com áudio real |
| 4 | Filtro de pessoa real por nome | Em parte | Cargos públicos em português e inglês e seções `Apelidos` e `Cargos` no glossário. Falta o classificador por modelo (4.1) |
| 5 | Glossário truncado | Feito | Lista inteira em `hotwords`; `initial_prompt` sem cortar nome |
| 6 | Rótulo de IA só no texto | Feito | `status.containsSyntheticMedia` (YouTube) e `post_info.is_aigc` (TikTok direto); o resumo lembra de ligar no app onde não há campo |
| 7 | Voz sem normalização | Feito, opcional | `loudnorm` EBU R128 com `[voz] normalizar = true` no `clipline.toml`; desligado por padrão até ser ouvido num episódio |
| 8 | Modo `--rede` | Em parte | Trava por aparelho com tempo que dobra, sessão de 7 dias, `POST /api/sair`, CSP e defesa de origem. Falta TLS e o bind no IP (4.2) |
| 9 | Crédito de foto não exigido | Feito | O agendamento recusa sem o autor ou o link de cada foto livre em cada texto |
| 10 | Sem CI, `pip install -e .` quebrado | Em parte | CI no GitHub Actions, pacote instalável com comando `clipline`, `ruff`. Falta o lockfile (4.6) |
| 11 | Traceback em JSON do agente | Feito | Contrato dos arquivos + tratador único na CLI; `validar --json` |
| 12 | Estado do canal versionado | Não feito de propósito | Ver 4.6: um `git rm` apagaria o arquivo do dono no próximo `pull` |
| 13 | Fila do painel só em memória | Não feito | Ver 4.3 |
| 14 | Porta do OAuth igual à do painel | Feito (sem trocar a porta) | O retorno não divide mais a porta (sem `SO_REUSEADDR`) e diz para fechar o painel. A porta ficou porque o endereço de retorno está registrado no TikTok |
| 15 | Vulnerabilidades do npm | Não feito | Ver 4.5 |

### 3.2 Outros itens feitos

- **Agente:** metadados do Wikimedia saneados; campo `origem` (modelo, data, marca das regras); `esteira trecho`,
  `esteira status` e `transcricao/texto-falantes.md` para gastar menos contexto; `esteira sugerir-cortes` (Claude em
  modo não interativo, grava `aprovados.proposta.json` sem tocar no `aprovados.json`); `esteira aprendizado`
  (compara a proposta com o que o dono deixou); nota explicada e gancho por corte na skill.
- **CLI:** `doctor`; mensagens de uma linha para arquivo ausente, JSON quebrado e campo errado.
- **Esteira:** `clipline.toml` (duração, identidade, legenda, voz, categoria e limite do YouTube); legenda com a
  palavra falada acesa (opcional); repetição com vírgula preservada; gravação atômica dos arquivos de estado;
  `sugerir` devolve a foto anterior se o download falhar; ffmpeg pelo `PATH`.
- **Publicação:** PKCE no login do Google.
- **Painel:** blocos **Publicar** e **Legenda**; *error boundary*; resposta antiga não cobre a do corte novo; linha do
  corte pelo teclado; fala dos trechos para leitor de tela; abas com `aria-controls` certos; borda de campo com
  3,2:1; volta à página depois de entrar; manifesto completo.
- **Repositório:** `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, modelos de issue e de pull request,
  `docs/seguranca-do-agente.md`, `docs/arquitetura.md` marcado como histórico, e2e fora do Windows.

## 4. O que falta

Ordem sugerida: 4.6 (risco de dado), depois 4.1, 4.3, 4.4, 4.2, 4.5 e o resto.

### 4.1 Agente

| Item | Por que não foi feito | Como fazer |
|---|---|---|
| Classificador de pessoa real por modelo | Exige chave de API e decisão de custo do dono | `esteira/agente.py`: chamada curta ao Claude com o prompt e o glossário, resposta sim/não com motivo, antes de aprovar no painel. Cachear por hash do prompt |
| Revisão visual pelo Claude antes do dono | Mesma dependência; precisa decidir quantos quadros e o custo | Extrair 4 a 6 quadros do `corte.mp4` e pedir uma lista de problemas (legenda sobre rosto, imagem errada, quadro vazio) em `revisao-visual.md` |
| Botão "Pedir sugestões" no painel | A rota precisaria rodar `claude -p` pela fila; falta decidir o comportamento quando o Claude Code não está instalado | Rota `POST /api/episodios/{ep}/sugerir-cortes` que chama `agente.sugerir_cortes` na fila |
| Servidor MCP no lugar do shell | Maior; só vale depois de as travas e o contrato estarem em uso | Expor `status`, `trecho`, `validar`, `montar` (sem `--forcar`) e o resumo de publicação como ferramentas tipadas, e tirar o Bash do agente |
| Métricas (YouTube Analytics) e conjunto de referência | Precisa de outro escopo OAuth e de decisão do dono | `metricas.json` por corte; o `aprendizado` cruza nota da skill × retenção |
| Hook testado numa sessão real | O ambiente desta rodada não roda o Claude Code do canal | Abrir o Claude Code em `Automacao/`, pedir `esteira montar ... --forcar` e conferir a recusa. No Windows, se `python` não estiver no PATH, troque o comando do hook para `.venv\\Scripts\\python.exe` |

Limite que fica mesmo com tudo acima: o hook lê o texto do comando, e um script montado em partes passa. A defesa
estrutural é o MCP (tirar o shell) ou a confirmação só pelo painel, que já existe.

### 4.2 Segurança do painel

| Item | Por que não foi feito | Como fazer |
|---|---|---|
| HTTPS na rede local | Exige certificado instalado no celular | Recomendar Tailscale (HTTPS e acesso só aos aparelhos do dono) ou `mkcert` |
| Bind no IP da Wi-Fi em vez de `0.0.0.0` | O uvicorn escuta um endereço só; trocar quebraria o acesso por `127.0.0.1` no próprio notebook | Dois servidores, ou bind no IP e acesso local por ele |
| Trava de publicação com PID | No Windows, `os.kill(pid, 0)` encerra o processo; precisa de `OpenProcess` via `ctypes` | Gravar o PID e conferir com a API do Windows; manter o limite de 2 h como reserva |
| Rotação do `logs/publicar.log` | O arquivo fica aberto pelo redirecionamento do `cmd` enquanto roda | Trocar o `>>` por `logging` com `RotatingFileHandler` dentro de `publicar rodar` |
| Varredura de segredos no histórico | O clone desta rodada é raso | `gitleaks detect` no histórico completo |
| PKCE no TikTok | O formato do desafio do TikTok para desktop não foi confirmado na documentação | Conferir e aplicar como no Google |

### 4.3 Painel e UX

| Item | Por que não foi feito | Como fazer |
|---|---|---|
| Fila persistente e com cancelamento | Mexe no trabalhador e na recuperação após queda; merece spec própria | Gravar os pedidos em `painel-fila.json`; ao abrir, marcar os que estavam "montando" como interrompidos; botão de cancelar os "na fila" |
| Diálogo próprio no lugar de `window.confirm` | Cerca de 20 testes simulam `confirm`; a troca é grande e precisa de revisão visual | Componente `<dialog>` com resumo, itens e custo, e um `confirmar()` que devolve Promise |
| Editor de início e fim com a transcrição clicável | Fase 3 do roadmap; precisa refazer `preparar` do corte pelo painel | Rota que muda `aprovados.json` e roda `preparar --numero N` na fila |
| Ajustar o enquadramento arrastando a caixa | Precisa de um quadro do episódio por plano e de um editor | Reaproveitar `planos.jpg`; gravar `enquadramento.json` |
| Ver as remoções do `edicoes.md` na linha do corte | Os tempos estão na linha do episódio; precisa remapear | Usar `limpeza.remapear` e mostrar como marcas na régua |
| Player de revisão (J/K/L, velocidade, áreas seguras) | Não priorizado nesta rodada | Atalhos no `Players` e uma sobreposição com as áreas de cada rede |
| SSE no lugar de consultas a cada 2 s | Troca o modelo de acompanhamento em todos os blocos | `GET /api/tarefas/eventos` com `text/event-stream` |
| Divisão de código, tipos gerados do OpenAPI | Não priorizado | `React.lazy` nas telas; OpenAPI só em desenvolvimento |
| Tema claro/escuro manual, esqueletos, CSS por componente | Não priorizado | — |
| Ações em lote, filtro por selo, histórico de aprovação | Não priorizado | — |

### 4.4 Esteira

| Item | Por que não foi feito | Como fazer |
|---|---|---|
| Ligar a voz normalizada e a legenda por palavra por padrão | Mudam o som e o visual de todo corte; precisam ser vistos e ouvidos num episódio | Testar num episódio com `clipline.toml` e decidir |
| Acompanhamento suave do rosto e tela dividida | Mudança grande no `enquadrar.py` e no filtro do render | Interpolar o centro dentro do plano; layout empilhado quando dois falantes alternam rápido |
| Alinhamento forçado (WhisperX) e transcrição em lote | Dependência pesada; precisa medir VRAM na RTX 4060 | Comparar num episódio antes de adotar |
| Entrada por link (`yt-dlp`) | `1 - Programas/` é só leitura para a esteira | Baixar para uma pasta de entrada própria e registrar a origem |
| Licenças CC BY-SA configuráveis | Decisão jurídica do canal | Lista de licenças aceitas no `clipline.toml` e aviso próprio para SA no painel |
| OpenAI em 9:16 | Os tamanhos aceitos pelo modelo não foram conferidos | Conferir na documentação e trocar o `TAMANHO` |
| Envio retomável e sem carregar o vídeo na memória | Não priorizado; cortes de 2 min cabem | Ler em partes e retomar do último byte confirmado |
| Pastas e encerramentos no `clipline.toml` | Mexe em `caminhos.py`, que é importado por todo o projeto; precisa de cuidado com `garantir_escrita` | Ler as pastas da configuração antes de calcular `CORTES` e `PROGRAMAS` |
| Miniatura, tags e playlist no YouTube | Não priorizado | Campos no `post.md` e na chamada da API |

### 4.5 Dependências

| Item | Por que não foi feito | Como fazer |
|---|---|---|
| react-router 6 → 7 (2 avisos moderados) | Mudança de versão maior; o risco real é baixo (SPA local, sem SSR) | Atualizar e rodar Vitest e Playwright |
| Vitest 2 → atual (avisos só em desenvolvimento) | Idem | Idem |

### 4.6 Repositório e dados

| Item | Por que não foi feito | Como fazer |
|---|---|---|
| Tirar `musicas/uso.json`, `publicacao.json` e `imagens-ia.json` do git | Um `git rm --cached` publicado apaga o arquivo da máquina do dono no próximo `pull`, e o `uso.json` guarda o histórico de músicas usadas | Na máquina do dono: copiar os três para fora, `git rm --cached`, acrescentar ao `.gitignore`, commitar, `pull` e devolver as cópias. Versionar `*.exemplo.json` |
| Lockfile do Python | Resolver as dependências com CUDA no Windows pede o ambiente do canal | `uv pip compile pyproject.toml -o requirements.lock` no Windows |
| Publicação agendada fora do Windows | `schtasks` e Gerenciador de Credenciais | cron/systemd/launchd e o backend padrão do `keyring` |
| CI no Windows | Custo e tempo de CI maiores | Um job `windows-latest` só com `pytest` |
| Linter de estilo completo | Reescreveria o projeto inteiro de uma vez | Acrescentar regras do `ruff` aos poucos |

## 5. Antes de usar num episódio real

1. `git pull` e `.venv\Scripts\python.exe -m pip install -e ".[painel,dev]"`.
2. `.venv\Scripts\clipline.exe doctor`: nada em FALTA.
3. `.venv\Scripts\python.exe -m pytest -n auto` no Windows.
4. `cd painel-web && npm ci && npm run build && npm run e2e`.
5. Abrir o Claude Code em `Automacao/` e pedir algo que o hook deve recusar (`montar ... --forcar`).
6. Num episódio já feito, em cópia: `preparar --numero 1 --forcar` (pelo dono) e conferir o `edicoes.md`
   ("pausa com som mantida") e o corte.
7. Testar `clipline.toml` com `[legenda] estilo = "palavra"` e `[voz] normalizar = true` num corte e decidir.
8. Agendar um corte pelo bloco **Publicar** do painel, com o YouTube em modo privado.

## 6. Comparação com o mercado, depois desta rodada

| Recurso | Antes | Agora | Referência de mercado |
|---|---|---|---|
| Legenda animada | Não | Sim, opcional (palavra acesa) | Padrão em OpusClip, Submagic, Klap |
| Nota e gancho por corte | Não | Sim, explicados, na skill | OpusClip e Vizard (nota opaca) |
| Edição pela interface | Post, música, imagens | + legenda e publicação | Descript (edição pelo texto) |
| Rótulo de IA nativo | Não | YouTube e TikTok | Ferramentas de agendamento oferecem |
| Revisão humana obrigatória | Sim | Sim, com travas também para o agente | Raro no mercado |
| Execução local | Sim | Sim, agora também em Linux | Os comerciais são SaaS |
| Edição pela transcrição, enquadramento suave, tela dividida | Não | Não (seção 4) | Comum nos comerciais |

A comparação usa a descrição pública das ferramentas citadas na auditoria inicial; nenhuma foi testada.
