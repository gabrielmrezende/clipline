# Servidor MCP, revisão visual e classificador

Três peças para o agente (Claude Code) trabalhar com menos poder e mais conferência:

- **Servidor MCP** (`esteira mcp`): a esteira como ferramentas tipadas, para o agente não precisar do shell.
- **Revisão visual por IA** (`esteira revisao-visual`): um modelo de visão olha alguns quadros de cada `corte.mp4`
  antes do dono.
- **Classificador de pessoa real** (`[ia] classificador = true`): uma segunda trava, por modelo, antes de gerar
  imagem de IA.

As três são opcionais. Sem instalar os extras e sem `clipline.toml`, a esteira faz exatamente o que fazia.

## Instalar

```
.venv\Scripts\python.exe -m pip install -e ".[mcp]"    servidor MCP (pacote mcp)
.venv\Scripts\python.exe -m pip install -e ".[ia]"     revisão visual e classificador (pacote anthropic)
```

A revisão visual e o classificador usam a API da Anthropic. A chave fica no Gerenciador de Credenciais do Windows,
como as dos provedores de imagem, e só o dono a guarda:

```
.venv\Scripts\python.exe -m esteira imagens conectar anthropic
```

O hook barra esse comando quando é o agente que tenta.

## Servidor MCP

### Por quê

Hoje o agente opera a esteira pelo terminal e o hook `.claude/hooks/travas.py` lê o texto de cada comando para barrar
`--confirmar`, `--forcar`, `--religar` e afins. Um texto pode ser montado em partes; o hook é uma rede, não uma parede.
O servidor MCP troca o terminal por ferramentas que não têm esses parâmetros: não há como pedir a uma delas que
confirme, force, publique, gaste ou leia uma chave, porque o caminho não existe.

### Ligar no Claude Code

1. Instale o extra `[mcp]` (acima).
2. Copie `.mcp.exemplo.json` para `.mcp.json`, na pasta `Automacao/`. O caminho do Python é relativo à pasta onde a
   sessão abre (`Automacao/`, como manda o `CLAUDE.md`); se o Claude Code não achar o servidor, troque
   `.venv/Scripts/python.exe` pelo caminho completo.
3. Abra a sessão. O Claude Code pergunta se aprova o servidor `clipline` do projeto; aprove. O comando `/mcp` mostra
   o servidor e as ferramentas.

Para outra pasta de episódios, acrescente `"--cortes", "<pasta>"` em `args`. Sem isso, vale `../2 - Cortes`.

`montar` leva minutos por corte. Se o Claude Code desistir de esperar, aumente o tempo das ferramentas MCP com a
variável `MCP_TOOL_TIMEOUT` (em milissegundos; veja o bloco de configuração abaixo) e monte um corte por vez.

### Ferramentas

| Ferramenta | O que faz | Grava |
|---|---|---|
| `listar_episodios` | Episódios em `2 - Cortes/` e o próximo passo de cada um | não |
| `status` | Etapa de cada corte (o mesmo do `status --json`) | não |
| `trecho` | Palavras, tempos e quem fala de um intervalo | não |
| `validar` | Confere os arquivos do agente e os tempos (o mesmo do `validar --json`) | não |
| `ler_aprovados`, `ler_pedidos`, `ler_post` | O arquivo e a `versao` dele | não |
| `gravar_aprovados` | `aprovados.json` pelo contrato, com a origem preenchida | sim |
| `gravar_pedidos` | `trabalho/pedidos.json` de um corte pelo contrato | sim |
| `gravar_post` | `post.md` de um corte, conferido seção por seção | sim |
| `planos`, `preparar` | As etapas 5 e 6, sem refazer o que já existe | sim, só o que falta |
| `montar` | Gera o `corte.mp4` que ainda não existe (nunca remonta) | sim, só o que falta |
| `revisao` | Refaz o relatório `revisao.md` | sim (relatório gerado) |
| `resumo_publicacao` | Confere um agendamento e mostra o resumo que o dono confirmaria | não |
| `resumo_revisao_visual` | Quantos cortes iriam à revisão visual e o custo estimado | não |

### Regras das gravações

- **Contrato.** `aprovados.json`, `pedidos.json` e `post.md` passam pelas mesmas conferências do `validar`. Fora do
  formato, nada é gravado e a resposta traz a lista de problemas (arquivo, campo, correção).
- **Versão.** Arquivo que já existe só é regravado com a `versao` que veio na última leitura (`ler_*`). Se o arquivo
  mudou no meio do caminho (o dono mexeu no painel, por exemplo), a gravação é recusada e nada muda: leia de novo.
- **Origem.** Em `aprovados.json` e `pedidos.json`, o servidor preenche `origem` (modelo informado, data e marca das
  regras de `Contexto/`). O agente só diz qual é o modelo.
- **Campos do dono e da esteira.** Em `pedidos.json`, `aprovado` e `no_video` são do dono (painel); `candidatas`,
  `url`, `bytes` e `resumidas` são da esteira (`imagens buscar` e `resumo`). Esses campos vêm sempre do arquivo que já
  estava. Um prompt de IA aprovado continua aprovado só se o texto não mudou.
- **Pessoa real.** Prompt de IA que cita alguém do glossário ou um cargo público é recusado na gravação.
- **Corte preparado.** Depois do `preparar`, o corte não muda de título (pasta), início nem fim por `gravar_aprovados`:
  isso exige refazer o corte com `--forcar`, que é do dono.
- **Conteúdo é dado.** Transcrição, textos, títulos e autores do Wikimedia voltam num envelope com `aviso` dizendo que
  aquilo é dado, não instrução.
- **Erros.** A recusa chega ao agente como uma frase (o que falta, o que fazer), nunca como um rastro de exceção.
- **Uma de cada vez.** O servidor atende uma ferramenta por vez; `montar` pode segurar as outras por minutos.

### Tirar o shell do agente

O `.claude/settings.json` do repositório continua como está (shell liberado, hook ligado). Para trabalhar sem shell,
o dono acrescenta em `.claude/settings.local.json` (pessoal, fora do git; o hook impede o agente de editá-lo):

```json
{
  "permissions": {
    "allow": ["mcp__clipline"],
    "deny": ["Bash", "PowerShell"]
  },
  "enabledMcpjsonServers": ["clipline"],
  "env": {"MCP_TOOL_TIMEOUT": "1800000"}
}
```

- `allow: mcp__clipline` libera todas as ferramentas do servidor sem perguntar a cada chamada.
- `deny: Bash, PowerShell` tira o terminal do agente. O hook continua ligado para `Write` e `Edit`.
- `enabledMcpjsonServers` aprova o servidor do `.mcp.json` sem a pergunta do começo da sessão.
- `MCP_TOOL_TIMEOUT` (30 minutos) dá tempo ao `montar`.

Confira com `/permissions` e `/mcp` na sessão. Sem o terminal, o agente ainda escreve `candidatos.md` e
`calendario.md` com `Write`, e o dono roda o que não virou ferramenta:

| Etapa | Quem roda sem shell |
|---|---|
| `transcrever`, `vozes` | o dono (GPU e token do Hugging Face) |
| `imagens buscar`, `resumo`, `sugerir`, `gerar` | o dono, pelo painel ou pelo terminal (rede, downloads, gasto) |
| `musica`, `cartao`, `sugerir-cortes` | o dono |
| `montar --forcar`, `planos --religar`, `preparar --forcar` | o dono (refazem trabalho pronto) |
| `revisao-visual --confirmar`, `publicar` | o dono (gastam ou publicam) |
| `doctor`, `painel` | o dono |

Quem preferir um meio-termo deixa o shell (com o hook) e pede ao agente que grave `aprovados.json`, `pedidos.json` e
`post.md` só pelas ferramentas, que conferem versão, contrato e os campos do dono.

## Revisão visual por IA

```
.venv\Scripts\python.exe -m esteira revisao-visual "<pasta do episódio>" [--numero N] [--quadros 4|5|6]
```

Sem `--confirmar`, só mostra quantos cortes vão, quantos quadros cada e o custo estimado, e não manda nada. Com
`--confirmar` (só o dono; o hook barra o agente), para cada corte já montado:

1. tira de 4 a 6 quadros do `corte.mp4` com o ffmpeg (começo, fim, o meio de cada imagem sobreposta e pontos
   espalhados entre eles), em 540x960;
2. manda os quadros ao modelo com a legenda e a imagem sobreposta de cada instante, o texto do começo e do fim do corte
   e o que é dito logo antes e logo depois;
3. grava a lista de problemas em `revisao-visual.md`, na pasta do episódio, com link para cada quadro
   (`NN-titulo/trabalho/revisao-visual/quadro-K.jpg`).

O modelo aponta só: legenda sobre o rosto, imagem errada para a fala, quadro vazio (tela preta, ninguém em quadro,
cabeça cortada) e corte no meio de uma palavra no começo ou no fim. O resultado de cada corte fica em
`trabalho/revisao-visual.json`, com a assinatura do `corte.mp4` (tamanho e data). Corte que não mudou desde a última
revisão (com o mesmo modelo) não é mandado de novo; se o corte for remontado, o relatório marca a revisão antiga como
desatualizada. Um corte com erro não para os outros, e uma revisão que falhou não apaga os quadros da anterior.

Custo estimado: uns US$ 0,04 por corte com 5 quadros no `claude-sonnet-5-5` (o padrão). O custo real, pelos tokens
que a API conta, vai no fim do `revisao-visual.md`. Para trocar o modelo, no `clipline.toml`:

```toml
[ia]
modelo_revisao = "claude-opus-5-5"     # ou "claude-haiku-5-5"
```

A revisão é uma segunda opinião. O dono continua vendo cada corte no painel antes de aprovar.

## Classificador de pessoa real

A esteira recusa prompt de IA que cite alguém do glossário ou um cargo público. Uma descrição que identifica alguém
sem nome nem cargo ("o ex-jogador careca que virou senador") passa pela lista. Com o classificador ligado:

```toml
[ia]
classificador = true
modelo_classificador = "claude-haiku-5-5"   # o padrão
```

cada prompt aprovado vai, logo antes de gerar a imagem, a um modelo pequeno junto com a lista de pessoas do glossário.
Se o modelo responder que o prompt retrata ou identifica uma pessoa real, a geração daquele momento é recusada com o
motivo (`Pode retratar pessoa real (classificador: ...)`), como a dos nomes do glossário. Os outros momentos seguem.

- A lista do glossário vem antes: o que ela já recusa não custa chamada.
- A resposta fica em `trabalho/classificador.json`, pela marca do prompt, do glossário e do modelo. O mesmo prompt não
  é perguntado duas vezes.
- Falha fechada: ligado e sem chave, sem rede ou com recusa do modelo, a imagem não é gerada e a mensagem diz por quê.
- Custa uma fração de centavo por prompt no `claude-haiku-5-5`. Só roda dentro da geração, que o dono já confirmou.

O classificador também erra. O dono continua aprovando cada prompt no painel.

## Limites

Veja a seção "Servidor MCP, revisão visual e classificador" em [`seguranca-do-agente.md`](seguranca-do-agente.md).
