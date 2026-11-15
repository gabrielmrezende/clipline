<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/marca/clipline/clipline-logo.svg">
    <img src="docs/marca/clipline/clipline-logo-claro.svg" alt="clipline" width="360">
  </picture>
</p>

<p align="center">
  De um episódio gravado a cortes verticais prontos para publicar: legenda, zoom em quem fala,
  música e imagens, revisados num painel web antes de qualquer envio.
</p>

<p align="center">
  <img alt="Python 3.12 e 3.13" src="https://img.shields.io/badge/python-3.12_%7C_3.13-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-painel-009688?logo=fastapi&logoColor=white">
  <img alt="React 18 + TypeScript" src="https://img.shields.io/badge/React_18-TypeScript-3178C6?logo=react&logoColor=white">
  <img alt="ffmpeg" src="https://img.shields.io/badge/ffmpeg-NVENC_ou_libx264-007808?logo=ffmpeg&logoColor=white">
  <img alt="Windows, Linux e macOS" src="https://img.shields.io/badge/plataforma-Windows_%7C_Linux_%7C_macOS-0078D4">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-CPU-2496ED?logo=docker&logoColor=white">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-servidor-6B4FBB">
  <img alt="Em uso" src="https://img.shields.io/badge/status-em_uso_no_canal-0750D8">
  <a href="https://github.com/gabrielmrezende/clipline/actions/workflows/testes.yml"><img alt="Testes" src="https://github.com/gabrielmrezende/clipline/actions/workflows/testes.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="Licença MIT" src="https://img.shields.io/badge/licen%C3%A7a-MIT-green"></a>
</p>

---

O **clipline** é a esteira de cortes do canal **Tudo é Política**. Ela recebe um episódio
horizontal (entrevista ou bate-papo) e entrega de 8 a 10 cortes verticais em 1080x1920 e 30 fps,
prontos para TikTok, YouTube Shorts e Instagram Reels.

O trabalho é dividido em três partes:

- **A CLI em Python** faz o trabalho mecânico e repetível: transcrever, achar quem fala, enquadrar,
  limpar pausas, legendar, pôr música e imagens e renderizar.
- **O [Claude Code](https://claude.com/claude-code)** faz o trabalho de julgamento numa sessão
  interativa, seguindo regras escritas: quais trechos viram corte, onde entra cada imagem, os textos
  dos posts e o calendário.
- **O dono do canal** revisa e aprova no painel. Nada é publicado sem um sim dele ao resumo da
  publicação.

> [!NOTE]
> O projeto nasceu para um canal só. Sem `clipline.toml`, os padrões continuam os do Tudo é Política: as pastas
> irmãs do repositório, os encerramentos, a logo e a arroba. Um canal novo roda `clipline init` e ganha as próprias
> pastas, identidade, idioma e prefixo de credenciais ([`docs/configuracao.md`](docs/configuracao.md)). As regras
> editoriais ficam fora do repositório, em `Contexto/`.

## Sumário

- [Destaques](#destaques)
- [Como funciona](#como-funciona)
- [Tecnologias](#tecnologias)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Uso](#uso)
- [Claude Code](#claude-code)
- [Painel de revisão](#painel-de-revisão)
- [Testes](#testes)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Princípios de projeto](#princípios-de-projeto)
- [Documentação](#documentação)
- [Roadmap](#roadmap)
- [Contribuindo](#contribuindo)
- [Segurança e credenciais](#segurança-e-credenciais)
- [Créditos de terceiros](#créditos-de-terceiros)
- [Licença](#licença)

## Destaques

- **Transcrição com tempo por palavra.** faster-whisper `large-v3` na GPU NVIDIA, ou `medium` em int8 na CPU quando
  não há GPU (ou quando falta o cuBLAS). Um glossário acerta os nomes próprios. O idioma do canal vem do
  `clipline.toml`, e a legenda, os cartões e a limpeza seguem esse idioma.
- **Entrada por link.** `baixar <url>` traz o episódio com o yt-dlp para `0 - Entrada/`, depois de mostrar o resumo
  e o aviso de direitos.
- **Zoom em quem fala.** A diarização (pyannote) diz quem fala e quando; os rostos (YuNet e SFace)
  dizem onde a pessoa está. A esteira calcula o enquadramento vertical de cada trecho e gera folhas
  de contato para conferir. Opcionais: o recorte acompanha o rosto sem tremer, e um diálogo rápido entre duas
  pessoas sai em tela dividida.
- **Corte limpo.** Remove pausas, hesitações e repetições e lista cada remoção em `edicoes.md`. Uma pausa só sai se
  o áudio confirmar o silêncio: riso, "uhum" ou fala que a transcrição perdeu ficam no corte.
- **Legenda queimada no vídeo**, com uma cópia `.srt` editável e correção do texto pelo painel. Opcional: a palavra
  falada acende, no estilo dos Shorts.
- **Música por clima.** Uma biblioteca de faixas livres (Kevin MacLeod, CC BY 4.0), volume ajustável
  e crédito escrito automaticamente nos textos dos posts.
- **Imagens ilustrativas no vídeo:**
  - fotos de licença livre do Wikimedia Commons, com crédito;
  - cartões de notícia no estilo do canal;
  - imagens de IA (OpenAI ou Google), com aprovação do prompt e do custo antes de gerar e bloqueio
    de prompts que citam pessoas reais.
- **Painel de revisão no navegador**, que também abre no celular pela mesma Wi-Fi: vídeo com a
  "linha do corte", troca de música com prévia, escolha das imagens, edição dos posts com limite de
  caracteres, calendário e botão de aprovar. O início e o fim do corte mudam com um clique na transcrição. O player
  tem atalhos de editor (J, K, L, quadro a quadro, velocidade) e mostra as áreas que o TikTok, os Shorts e os Reels
  cobrem. A fila de montagens chega em tempo real, sobrevive a um reinício do painel e pode ser cancelada.
- **Publicação com trava.** YouTube, Instagram e TikTok, sempre a partir de um resumo que o dono
  confirma, pelo painel ou pelo terminal. O YouTube recebe o vídeo na hora, num envio retomável. Instagram e TikTok
  entram numa fila que o agendador do sistema publica no horário: Agendador de Tarefas no Windows, systemd ou cron no
  Linux, launchd no macOS. Vídeo com imagem de IA vai com o rótulo nativo de conteúdo sintético (YouTube e TikTok
  direto), e foto livre no vídeo exige o crédito nos textos.
- **Agente com travas de verdade.** O Claude Code segue `CLAUDE.md` e skills versionadas, e um hook impede que ele
  publique, gaste, sobrescreva ou toque em credenciais, mesmo se for induzido a isso por um texto que leu. O hook
  vale para o Bash e para o PowerShell. O servidor MCP (`esteira mcp`) dá ao agente a esteira em ferramentas tipadas,
  sem shell e sem nenhuma que confirme.
- **Instalação em um comando**, no Windows, no Linux e no macOS, e uma imagem Docker com a esteira em CPU e o painel.
- **Cuidado com os arquivos.** A gravação é confinada a duas pastas, nada é sobrescrito sem
  `--forcar` e um corte com erro não derruba os outros.

## Como funciona

```mermaid
flowchart LR
    V[Episódio .mp4] --> T[transcrever<br/>Whisper]
    V --> VZ[vozes<br/>pyannote]
    T --> E{{Claude Code<br/>escolhe os cortes}}
    E --> VAL[validar]
    VAL --> P[planos<br/>rostos e zoom]
    VZ --> P
    P --> PR[preparar<br/>pausas, legenda, música]
    PR --> I{{Claude Code<br/>escolhe os momentos}}
    I --> IMG[imagens<br/>Wikimedia e IA]
    PR --> M[montar<br/>ffmpeg]
    IMG --> M
    M --> PA[painel<br/>revisão]
    PA --> A[[Dono do canal<br/>aprova]]
    A --> PUB[publicar<br/>resumo e confirmação]
```

Retângulos são comandos da CLI; hexágonos, decisões do Claude Code; colchetes duplos, decisões do
dono do canal.

As etapas conversam por arquivos JSON e Markdown na pasta de cada episódio (`palavras.json`,
`vozes.json`, `aprovados.json`, `montagem.json`, `pedidos.json`...). Cada etapa pode ser refeita
sozinha, e o estado nunca fica só em memória.

## Tecnologias

| Peça | Para quê |
|---|---|
| Python 3.12 ou 3.13 | A esteira (`esteira/`) e a CLI |
| ffmpeg e ffprobe | Corte, filtros, medição de áudio e render; usa NVENC (`h264_nvenc`) e recua para `libx264` |
| faster-whisper | Transcrição com tempo por palavra: `large-v3` em CUDA ou `medium` em int8 na CPU |
| pyannote `speaker-diarization-3.1` | Quem fala e quando (CUDA ou CPU, opcional) |
| OpenCV YuNet e SFace | Detecção de rostos e a mesma pessoa entre cenas |
| Pillow | Folhas de contato, cartões de notícia e preparo das fotos |
| Wikimedia Commons API | Fotos com licença livre |
| OpenAI e Google (Gemini) | Imagens de IA, só com aprovação |
| yt-dlp | `baixar <url>` (opcional, extra `entrada`) |
| SDK do MCP e da Anthropic | Servidor MCP, revisão visual e classificador de pessoa real (opcionais, extras `mcp` e `ia`) |
| FastAPI e uvicorn | API do painel, com eventos da fila por SSE |
| React 18, TypeScript, React Router 7 e Vite 8 | Interface do painel |
| pytest, Vitest e Playwright | Testes |

## Requisitos

- **Windows 10 ou 11, Linux ou macOS.** O canal original roda no Windows; a CI testa no Windows e no Linux. A
  publicação agendada usa o agendador de cada sistema e guarda as chaves no cofre de credenciais dele, pelo `keyring`.
- **Python 3.12 ou 3.13.**
- **GPU NVIDIA com CUDA 12, opcional.** Sem ela, a transcrição roda na CPU, bem mais devagar: um episódio longo pode
  levar horas. A esteira roda em uso real numa RTX 4060 de 8 GB.
- **ffmpeg e ffprobe**, de preferência com NVENC. Sem NVENC, o render usa `libx264`.
- **Node.js 22.12 ou mais novo**, só para gerar o build do painel.
- **Claude Code**, para as etapas de julgamento. Os arquivos que ele grava (`aprovados.json`,
  `pedidos.json`, `post.md`) também podem ser escritos à mão.
- **Opcional:** um token do Hugging Face com acesso ao `pyannote/speaker-diarization-3.1`, para o
  comando `vozes`.

## Instalação

**1. Crie a pasta do canal e clone o repositório dentro dela.** A esteira usa a pasta *acima* do clone como raiz
(ou a que o `clipline.toml` disser):

```powershell
mkdir "Meu Canal"; cd "Meu Canal"
git clone https://github.com/gabrielmrezende/clipline.git Automacao
cd Automacao
```

**2. Rode o instalador.** Ele confere o Python e o Node, cria o `.venv`, instala o pacote, gera o build do painel,
cria as pastas do canal que faltam (pelo `esteira init`) e termina com o `doctor`. Rodar de novo não estraga nada.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1   # Windows
```

```bash
scripts/instalar.sh                                              # Linux e macOS
```

```text
Meu Canal/
├── 0 - Entrada/      vídeos que o baixar traz por link (criada no primeiro uso)
├── 1 - Programas/    episódios gravados (a esteira só lê)
├── 2 - Cortes/       saída: uma pasta por episódio, uma subpasta por corte
├── 3 - Identidade/   logo e vídeos de encerramento
├── Contexto/         regras editoriais do canal (Markdown) e glossario.md
└── Automacao/        este repositório
```

Opções, Docker e a instalação à mão estão em [`docs/instalacao.md`](docs/instalacao.md). As chaves do
`clipline.toml` (pastas, identidade, idioma, legenda, voz, credenciais) estão em
[`docs/configuracao.md`](docs/configuracao.md).

**3. O que o git não traz.** O `doctor` diz o que falta de cada item:

- **ffmpeg e ffprobe**, no `PATH` ou em `bin/`.
- **Modelos de rosto**: `face_detection_yunet_2023mar.onnx` e `face_recognition_sface_2021dec.onnx` do
  [OpenCV Zoo](https://github.com/opencv/opencv_zoo), em `modelos/`. O [`modelos/LEIA.md`](modelos/LEIA.md) tem os
  links.
- **Músicas.** O git guarda o catálogo (`musicas/catalogo.json`) com as 40 faixas do
  [incompetech.com](https://incompetech.com); os `.mp3` ficam fora. `musicas baixar` baixa as faixas de
  `musicas/aprovadas.json` que não estão no disco. Para escolher outras, `musicas propor` sugere uma seleção por clima.
- **Vozes (opcional).** O comando `vozes` precisa do extra `vozes` (`torch` 2.5.1, `pyannote.audio`; o comando certo
  do `torch` para a sua GPU está em [pytorch.org](https://pytorch.org/get-started/previous-versions/)) e de um token
  do Hugging Face na variável `HF_TOKEN`.
- **Extras opcionais**: `entrada` (yt-dlp, para o `baixar`), `mcp` (servidor MCP) e `ia` (revisão visual e
  classificador). Instale com `pip install -e ".[entrada,mcp,ia]"`.

**Docker.** `docker compose up --build` sobe o painel em `http://localhost:8765` com a esteira em CPU e as pastas do
canal montadas. Publicar não roda no contêiner. Detalhes em [`docs/instalacao.md`](docs/instalacao.md#docker).

## Uso

Todos os comandos seguem o formato `.venv\Scripts\python.exe -m esteira <comando>`. Os que agem
sobre um episódio recebem a pasta dele em `2 - Cortes/` e aceitam `--numero N` para um corte só.
O resultado sai por corte: `ok`, `ok com alertas: ...` ou `erro: ...`.

| # | Etapa | Comando | O que faz |
|---|---|---|---|
| 0 | Baixar (opcional) | `baixar <url>` | Mostra o resumo e o aviso de direitos; com `--confirmar`, baixa para `0 - Entrada/` |
| 1 | Transcrever | `transcrever <vídeo> --quadro Q --numero N --convidado C` | Cria a pasta do episódio e a transcrição com tempo por palavra (`--dispositivo auto\|cuda\|cpu`) |
| 2 | Vozes | `vozes <vídeo> <pasta>` | Quem fala e quando |
| 3 | Escolher | *Claude Code* | Escolhe os trechos e grava `aprovados.json` |
| 4 | Validar | `validar <pasta>` | Confere os cortes escolhidos |
| 5 | Enquadrar | `planos <pasta>` | Rostos, quem fala e zoom, com a folha `planos.jpg` para conferir |
| 6 | Preparar | `preparar <pasta>` | Pausas, legenda e música; grava a receita `montagem.json` |
| 7 | Imagens | `imagens buscar\|resumo\|sugerir\|gerar <pasta>` | Candidatas do Wikimedia, resumo do download, fotos preparadas e imagens de IA |
| 8 | Montar | `montar <pasta>` | Renderiza o `corte.mp4` de cada corte |
| 9 | Textos | *Claude Code* | `post.md` de cada corte e `calendario.md` |
| 10 | Revisão | `revisao <pasta>` | Resumo do episódio em `revisao.md` |
| 11 | Aprovar | `painel` | Revisão e aprovação no navegador |
| 12 | Publicar | `publicar agendar <pasta> --numero N --data "AAAA-MM-DD HH:MM"` | Mostra o resumo; com `--confirmar`, envia |

Comandos de apoio:

- `init`: cria as pastas e o `clipline.toml` de um canal novo, sem sobrescrever nada.
- `status [<pasta>]`: em que etapa está cada corte e qual o próximo comando (`--json` para o painel e o agente).
- `trecho <pasta> --de S --ate S`: palavras, tempos e quem fala de um intervalo do episódio.
- `doctor`: confere o ambiente e diz o que falta (GPU, modelos, músicas no disco, extras, chaves, tarefa).
- `validar <pasta> --json`: confere todos os arquivos que o agente escreve e diz arquivo, campo e correção.
- `musica <pasta>`: troca a música de um corte já montado.
- `musicas propor|baixar`: monta a biblioteca de música.
- `cartao`: gera um cartão de notícia avulso.
- `revisao-visual <pasta>`: um modelo de visão olha quadros de cada corte e grava `revisao-visual.md`. Sem
  `--confirmar`, só mostra o custo.
- `mcp`: servidor MCP (stdio) com a esteira em ferramentas tipadas para o agente.
- `publicar conectar|fila|rodar|cancelar|marcar|instalar-tarefa|desinstalar-tarefa`: contas, fila e tarefa de
  publicação ([`docs/publicacao.md`](docs/publicacao.md)).

Exemplo do começo de um episódio:

```powershell
.venv\Scripts\python.exe -m esteira transcrever "..\1 - Programas\Entre Assuntos 03.mp4" --quadro "Entre Assuntos" --numero 3 --convidado "Nome do Convidado"
.venv\Scripts\python.exe -m esteira vozes "..\1 - Programas\Entre Assuntos 03.mp4" "..\2 - Cortes\Entre Assuntos 03 - Nome do Convidado"
```

O passo a passo completo, com as pausas para confirmação, está em
[`docs/operacao.md`](docs/operacao.md).

## Claude Code

A integração com o agente está no repositório:

| Arquivo | Para quê |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Regras invioláveis e como economizar contexto |
| [`.claude/hooks/travas.py`](.claude/hooks/travas.py) | Hook `PreToolUse`: nega confirmar, sobrescrever, credenciais e pastas protegidas |
| [`.claude/skills/`](.claude/skills) | `escolher-cortes`, `momentos-de-imagem`, `textos-e-calendario` |
| [`.claude/commands/`](.claude/commands) | `/episodio`, `/corrigir-corte`, `/agendar` |
| [`docs/esquemas/`](docs/esquemas) | Formato dos arquivos que o agente grava |
| [`Contexto.exemplo/`](Contexto.exemplo) | Modelos das regras editoriais do canal |
| [`esteira/mcp_servidor.py`](esteira/mcp_servidor.py) | Servidor MCP: status, trecho, validar, gravações pelo contrato, etapas que só fazem o que falta e resumos. Nenhuma ferramenta confirma |

Abra o Claude Code dentro de `Automacao/`. As pastas irmãs entram pelo `.claude/settings.json`. Com o servidor MCP
ligado ([`docs/mcp.md`](docs/mcp.md)), dá para tirar o shell do agente. Detalhes e limites em
[`docs/seguranca-do-agente.md`](docs/seguranca-do-agente.md).

## Painel de revisão

```powershell
.venv\Scripts\python.exe -m esteira painel          # http://127.0.0.1:8765
.venv\Scripts\python.exe -m esteira painel codigo   # cria o código de acesso (uma vez)
.venv\Scripts\python.exe -m esteira painel --rede   # abre para o celular na mesma Wi-Fi
```

- **Monitor:** o vídeo em pé, fixo ao lado da página, e a **linha do corte** embaixo dele, uma
  régua do tempo que mostra onde entra cada imagem e o que a limpeza tirou, e leva o player até lá com um clique.
- **Player:** atalhos de editor (espaço ou K, J e L, setas, vírgula e ponto para quadro a quadro, `<` e `>` para a
  velocidade, `?` para a lista) e as áreas que a interface do TikTok, dos Shorts e dos Reels cobre por cima do vídeo.
- **Trecho:** a transcrição em volta do corte, com as falas dos outros cortes em cinza. Um clique numa palavra marca
  o início, Shift e clique marca o fim. Antes de trocar, o painel diz o que muda e o que se perde, e o corte é
  preparado e montado de novo.
- **Música:** biblioteca por clima, prévia de 15 segundos no ponto do vídeo, volume e remontagem
  em fila.
- **Imagens:** cada momento aparece como uma linha de roteiro. Dá para escolher fotos, buscar
  outras, aprovar prompts de IA (com o custo antes), escolher a versão que vai para o vídeo e
  montar de novo.
- **Legenda:** o texto de cada tela, com um clique para ir ao tempo dela e o botão de montar de novo.
- **Post:** títulos, descrições e legendas com contador de limite por rede, avisos e proteção
  contra edição simultânea.
- **Publicar:** data, redes, o mesmo resumo do `publicar agendar` e a confirmação; a fila do corte com cancelar.
- **Aprovar:** copia o corte para `video-final/corte-aprovado.mp4`, que é o vídeo que a publicação
  usa.
- **Fila:** montagens, prévias e imagens entram numa fila gravada em disco. O andamento chega por eventos (SSE), com
  consulta periódica de reserva; dá para cancelar e tentar de novo, e o que estava rodando quando o painel fechou
  aparece como interrompido.
- Confirmações num diálogo do próprio painel, com o custo no botão e o foco em Cancelar quando a ação gasta ou não
  volta. Tema claro, escuro ou do sistema, uso pelo teclado e movimento reduzido quando o sistema pede.

Detalhes em [`docs/painel.md`](docs/painel.md) e [`docs/painel-revisao.md`](docs/painel-revisao.md).

## Testes

```powershell
.venv\Scripts\python.exe -m pytest -n auto   # esteira e API do painel (mais de 1.500 testes; Windows, Linux e CI)

cd painel-web
npm test                             # componentes do painel (Vitest)
npx playwright install chromium      # uma vez
npm run e2e                          # ponta a ponta, com um episódio falso
```

Os testes não usam GPU, rede nem vídeos do canal. Modelos, APIs e downloads entram como
dependências trocáveis por falsos, e o ffmpeg de `bin/` gera vídeos sintéticos de poucos segundos
quando é preciso. O teste com os modelos de rosto reais é pulado se os `.onnx` não estiverem em
`modelos/`. Nos testes de ponta a ponta, o painel roda com montagem e geração de imagem falsas, e o
teste das imagens falha se a página tentar acessar a internet.

## Estrutura do repositório

```text
Automacao/
├── CLAUDE.md             regras do agente
├── .claude/              hook das travas, skills e comandos do Claude Code
├── Contexto.exemplo/     modelos das regras editoriais do canal
├── clipline.exemplo.toml configuração do canal (opcional)
├── esteira/              pacote Python
│   ├── cli.py            ponto de entrada, um subcomando por etapa
│   ├── transcrever.py, vozes.py, rostos.py, pessoas.py, enquadrar.py, planos.py
│   ├── acompanhar.py, dividida.py   acompanhamento suave e tela dividida
│   ├── limpeza.py, legenda.py, receita.py, musica.py, montar.py, render.py
│   ├── pedidos.py, wikimedia.py, imagens.py, imagens_no_video.py, cartao.py
│   ├── contrato.py, falantes.py, diagnostico.py, config.py, caminhos.py, canal.py, idiomas.py
│   ├── entrada.py        baixar por link (yt-dlp)
│   ├── mcp_servidor.py, revisao_visual.py, classificador.py   peças do agente
│   ├── imagens_ia/       provedores de imagem de IA
│   ├── painel/           API FastAPI do painel, fila persistente e eventos (SSE)
│   └── publicar/         YouTube, Instagram, TikTok, fila e tarefa agendada
├── painel-web/           interface do painel (React + TypeScript + Vite)
├── scripts/              instalação em um comando e apoio do Docker
├── Dockerfile, compose.yaml  imagem em CPU com o painel
├── tests/                testes da esteira e da API
├── docs/                 operação, arquitetura, specs, planos e resultados
├── musicas/              catálogo e uso da biblioteca (os .mp3 ficam fora do git)
├── modelos/              modelos de rosto (os .onnx ficam fora do git)
├── assets/               fonte da legenda e imagem do encerramento
└── pyproject.toml
```

## Princípios de projeto

1. **Regras editoriais fora do código.** O estilo do canal fica em `Contexto/*.md` e orienta o
   Claude Code. O código só lê o glossário de nomes.
2. **Cada etapa grava em disco e pode ser refeita sozinha.**
3. **Nada é sobrescrito sem `--forcar`**, para proteger as edições feitas à mão.
4. **Um corte com erro não derruba os outros.**
5. **Escrita confinada.** A esteira recusa gravar fora de `2 - Cortes/` e da própria pasta.
   `1 - Programas/` é só leitura.
6. **Humano no fim.** Só o dono aprova um corte, e publicar exige um sim dele ao resumo.
7. **Lógica pura separada de I/O.** Enquadramento, limpeza e legenda recebem dados e devolvem
   dados; o que toca modelo, ffmpeg ou rede é injetado e pode ser trocado por um falso nos testes.

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/operacao.md`](docs/operacao.md) | Passo a passo de um episódio, do vídeo à publicação |
| [`docs/instalacao.md`](docs/instalacao.md) | Instalação em um comando, Docker e ferramentas do repositório |
| [`docs/configuracao.md`](docs/configuracao.md) | O `clipline.toml`, chave por chave, e o `clipline init` |
| [`docs/entrada-e-idiomas.md`](docs/entrada-e-idiomas.md) | Sem GPU NVIDIA, canal em outro idioma, `baixar <url>`, licenças e tamanhos de imagem |
| [`docs/enquadramento.md`](docs/enquadramento.md) | Acompanhamento suave do rosto e tela dividida |
| [`docs/painel.md`](docs/painel.md) | Instalar, abrir e usar o painel |
| [`docs/painel-revisao.md`](docs/painel-revisao.md) | Player, áreas das redes, remoções, confirmações e tema |
| [`docs/publicacao.md`](docs/publicacao.md) | Tarefa agendada no Windows, Linux e macOS, registro, trava e extras do YouTube |
| [`docs/mcp.md`](docs/mcp.md) | Servidor MCP, revisão visual e classificador de pessoa real |
| [`docs/arquitetura.md`](docs/arquitetura.md) | Módulos, arquivos entre etapas e decisões (escrito antes do painel) |
| [`docs/superpowers/specs/`](docs/superpowers/specs) | Especificação de cada funcionalidade |
| [`docs/superpowers/plans/`](docs/superpowers/plans) | Planos de implementação |
| [`docs/resultados/`](docs/resultados) | Medições e testes com episódios reais |
| [`docs/seguranca-do-agente.md`](docs/seguranca-do-agente.md) | Travas do agente, defesa do painel e limites |
| [`docs/esquemas/`](docs/esquemas) | JSON Schema dos arquivos que o agente grava |
| [`docs/auditoria/`](docs/auditoria) | Auditorias do projeto e o que falta fazer |
| [`CHANGELOG.md`](CHANGELOG.md) | O que mudou em cada versão |

## Roadmap

- [x] Esteira completa: transcrição, vozes, enquadramento, limpeza, legenda, música e render
- [x] Imagens: Wikimedia, cartões de notícia e IA com aprovação, já dentro do vídeo
- [x] Painel de revisão: vídeos, posts, calendário, música, imagens e aprovação
- [x] Publicação no YouTube, Instagram e TikTok com resumo e confirmação
- [x] Licença MIT
- [x] Painel, fase 2: agendar pela tela e acompanhar a fila do corte
- [x] Integração com o Claude Code versionada, com travas por hook
- [x] Integração contínua com os testes
- [x] `clipline.toml` para duração, identidade, legenda e voz
- [x] Painel, fase 3: início e fim do corte pela transcrição clicável
- [x] Configuração completa por canal (pastas, encerramentos, idioma, credenciais) e `clipline init`
- [x] Instalação com um comando, imagem Docker e publicação agendada no Linux e no macOS
- [x] Acompanhamento suave do rosto e tela dividida (opcionais)
- [x] Transcrição sem GPU NVIDIA e entrada por link
- [x] Servidor MCP para o agente trabalhar sem shell
- [ ] Imagem Docker com GPU (CUDA) e com o `vozes`
- [ ] Nomes das tarefas agendadas e `User-Agent` vindos do `clipline.toml`
- [ ] Interface do painel em outros idiomas

O que falta, com prioridade e motivo, está em [`docs/auditoria/`](docs/auditoria).

## Contribuindo

Sugestões e correções são bem-vindas.

Veja [`CONTRIBUTING.md`](CONTRIBUTING.md). Em resumo:

1. Abra uma issue descrevendo o problema ou a ideia antes de um pull request grande.
2. Crie um branch a partir do `master`.
3. Mantenha os testes passando (`pytest` e `npm test`) e escreva testes para o que mudar.
4. Use mensagens no formato [Conventional Commits](https://www.conventionalcommits.org/pt-br/), em
   português (`feat:`, `fix:`, `docs:`, `refactor:`).
5. Não envie vídeos, músicas, modelos, chaves ou dados de canal.

O código, os comentários e a interface são em português.

## Segurança e credenciais

- Nenhuma chave fica em arquivo. As chaves das APIs de imagem e das redes sociais ficam no cofre de credenciais do
  sistema, pelo `keyring` (no Windows, o Gerenciador de Credenciais), com o prefixo do canal; o token do Hugging Face
  vem da variável `HF_TOKEN` e aparece mascarado nas mensagens de erro.
- O painel abre só em `127.0.0.1`. Na rede local (`--rede`), ele exige o código de acesso, com trava por aparelho, e
  a sessão dura 7 dias. Pedidos vindos de outra página são recusados e as respostas levam CSP.
- O agente não confirma nada: ver [`docs/seguranca-do-agente.md`](docs/seguranca-do-agente.md) e
  [`SECURITY.md`](SECURITY.md).
- Gerar imagem de IA e publicar sempre mostram um resumo com o custo ou o destino antes de agir.

## Créditos de terceiros

| Item | Autor e licença | No repositório? |
|---|---|---|
| Músicas | Kevin MacLeod ([incompetech.com](https://incompetech.com)), CC BY 4.0 | Só o catálogo |
| Fonte da legenda: Montserrat | Julieta Ulanovsky e colaboradores, SIL OFL 1.1 | Sim (`assets/fonts/`) |
| Fonte do painel: Schibsted Grotesk | Bakken & Bæck para a Schibsted, SIL OFL 1.1 | Pelo npm (`@fontsource-variable`) |
| YuNet e SFace | OpenCV Zoo, MIT e Apache 2.0 | Não |
| Fotos | Wikimedia Commons, licença de cada arquivo, creditada nos posts | Não |

## Licença

O código está sob a [licença MIT](LICENSE). Os itens de terceiros listados acima seguem as
próprias licenças. As marcas **Tudo é Política** (incluindo o encerramento em `assets/`) e
**clipline** (`docs/marca/`) não fazem parte da licença do código.

---

<p align="center">
  Feito por <a href="https://github.com/gabrielmrezende">gabrielmrezende</a> para o canal Tudo é Política.
</p>
