# Configuração do canal (`clipline.toml`)

Tudo o que é do canal, e não lógica da esteira, mora no `clipline.toml`: nome e arroba, duração dos cortes, estilo
da legenda, pastas, vídeos de encerramento, logo e o prefixo das credenciais.

- **Onde fica:** na raiz do repositório (`Automacao/clipline.toml`, ao lado do `pyproject.toml`). Fica fora do git.
- **Sem o arquivo**, valem os padrões, que são os do canal original (Tudo é Política): as pastas irmãs do
  repositório, os quatro encerramentos, a logo, `@tudoepoliticabr` e os nomes de credenciais de sempre. Quem já usa a
  esteira sem `clipline.toml` não precisa fazer nada.
- **Modelo comentado:** [`clipline.exemplo.toml`](../clipline.exemplo.toml), com todos os padrões.
- **Quando vale:** o arquivo é lido uma vez por processo. Mudou? Feche e abra o painel de novo.
- **Arquivo com erro** (TOML quebrado, chave que não existe, tipo errado): a CLI para e diz o arquivo, a chave e o
  que corrigir, antes de gravar qualquer coisa. Só `doctor` e `init` rodam assim, e o `doctor` mostra o erro.

## Canal novo: `clipline init`

```powershell
mkdir "Meu Canal"; cd "Meu Canal"
git clone https://github.com/gabrielmrezende/clipline.git Automacao
cd Automacao
py -3.12 -m esteira init          # antes do venv: o init só usa a biblioteca padrão do Python
```

O `init` cria, sem sobrescrever nada que já exista:

- a pasta do canal e as pastas `Contexto`, `1 - Programas`, `2 - Cortes` e `3 - Identidade` (com `Encerramentos/` e
  `Logos/`);
- o `Contexto/` com as regras de exemplo de `Contexto.exemplo/` (só se a pasta não existir ou estiver vazia: regra
  de exemplo misturada com as do canal confundiria o agente);
- o `clipline.toml` com nome, arroba, perfil do TikTok, duração dos cortes, pastas, identidade e prefixo das
  credenciais. Se o arquivo já existe, ele fica como está e só as pastas que faltam são criadas.

No fim, ele lista os próximos passos (venv, regras, logo e encerramentos, `doctor`, primeiro `transcrever`).

O que não vier por flag é perguntado no terminal, com o padrão entre colchetes (Enter aceita). Com
`--sem-perguntas`, ficam os padrões: o nome do canal vem do nome da pasta ("Meu Canal" vira `@meucanal`).

| Flag | O que é | Padrão |
|---|---|---|
| `pasta` (posicional) | Pasta do canal | A raiz em uso: `CLIPLINE_RAIZ`, `[pastas] raiz` ou a pasta acima do repositório |
| `--canal` | Nome do canal | O nome da pasta |
| `--arroba` | Arroba nas redes (o `@` é acrescentado se faltar) | Tirada do nome |
| `--perfil-tiktok` | Endereço do perfil no TikTok | `https://www.tiktok.com/<arroba>` |
| `--duracao-minima`, `--duracao-maxima` | Faixa de duração dos cortes, em segundos | 60 e 120 |
| `--contexto`, `--programas`, `--cortes`, `--identidade` | Nome de cada pasta, relativo à pasta do canal | Os de sempre |
| `--prefixo-credenciais` | Prefixo no Gerenciador de Credenciais | Tirado do nome (`Meu Canal` vira `meu-canal`) |
| `--sem-perguntas` | Não pergunta nada | — |

`clipline iniciar` é o mesmo comando.

**Dois jeitos de usar:**

1. **Ao redor do clone** (o jeito do README): clone o repositório como `Automacao/` dentro da pasta do canal e rode
   `init` sem a pasta. As pastas nascem ao lado de `Automacao/` e o `clipline.toml` não precisa de `raiz`.
2. **Numa pasta escolhida**: `clipline init "D:\Canais\Meu Canal"`. As pastas nascem lá e o `clipline.toml` ganha
   `[pastas] raiz = "D:/Canais/Meu Canal"`. A pasta do canal não pode ficar dentro do repositório.

O `init` também encontra o que já está na pasta de identidade: os vídeos de `Encerramentos/` entram na lista de
encerramentos (em ordem de nome; se forem os quatro do canal original, na ordem de sempre) e a logo de `Logos/`
entra em `logo`. Rodar o `init` com o nome e a arroba do canal original, na pasta dele, dá exatamente a
configuração de hoje (pastas, encerramentos na mesma ordem, logo, sobreposição e credenciais).

## Todas as chaves

### `[canal]`

| Chave | Tipo | Padrão | O que faz |
|---|---|---|---|
| `nome` | texto | `"Tudo é Política"` | Nome do canal |
| `arroba` | texto | `"@tudoepoliticabr"` | Vai nos cartões de notícia e no "SIGA @arroba" da sobreposição. Vazia: só a logo |
| `perfil_tiktok` | texto | `"https://www.tiktok.com/@tudoepoliticabr"` | Endereço que a fila mostra depois de publicar no TikTok |

### `[duracao]`

| Chave | Tipo | Padrão | O que faz |
|---|---|---|---|
| `minima` | número | `60` | Segundos. O `validar` recusa corte mais curto |
| `maxima` | número | `120` | Segundos. O `validar` recusa corte mais longo. Precisa ser maior que a mínima |

### `[legenda]`

| Chave | Tipo | Padrão | O que faz |
|---|---|---|---|
| `estilo` | texto | `"fixa"` | `"fixa"` (bloco branco) ou `"palavra"` (a palavra falada acende na cor de destaque) |
| `cor_destaque` | texto | `"&H0000E5FF"` | Cor ASS no formato `&HAABBGGRR`. O padrão é amarelo |

### `[voz]`

| Chave | Tipo | Padrão | O que faz |
|---|---|---|---|
| `normalizar` | sim/não | `false` | `true`: a voz de todos os cortes fica no mesmo volume percebido |
| `lufs` | número | `-14.0` | Alvo de volume integrado quando `normalizar = true` |

### `[youtube]`

| Chave | Tipo | Padrão | O que faz |
|---|---|---|---|
| `categoria` | texto | `"22"` | Categoria do vídeo no YouTube |
| `limite_shorts` | número | `180` | Segundos. O `publicar agendar` recusa mandar para o YouTube um corte mais longo |

### `[pastas]`

| Chave | Tipo | Padrão | O que faz |
|---|---|---|---|
| `raiz` | caminho | a pasta acima do repositório | Pasta do canal. Relativa ao repositório, ou absoluta |
| `contexto` | caminho | `"Contexto"` | Regras editoriais (Markdown) e `glossario.md`. Relativa à raiz |
| `programas` | caminho | `"1 - Programas"` | Episódios gravados. A esteira só lê. Relativa à raiz |
| `cortes` | caminho | `"2 - Cortes"` | Saída: uma pasta por episódio. Relativa à raiz |
| `identidade` | caminho | `"3 - Identidade"` | Logo e vídeos de encerramento. Relativa à raiz |

Todos aceitam caminho absoluto e `~`. Prefira a barra normal (`D:/Canais/Meu Canal`), que funciona no Windows; no
TOML, a barra invertida precisa ir dobrada.

**A variável de ambiente `CLIPLINE_RAIZ`** troca a raiz sem mexer no arquivo e vale mais que `[pastas] raiz`.
Relativa, ela também parte do repositório. Cuidado: a publicação agendada roda pelo Agendador de Tarefas, que não
herda a variável de um terminal. Para ela, prefira `[pastas] raiz` ou defina a variável no usuário do Windows
(`setx CLIPLINE_RAIZ "D:\Canais\Meu Canal"`).

**Escrita confinada.** A esteira só grava na pasta de cortes configurada e no próprio repositório
(`caminhos.garantir_escrita`). Por isso o arquivo é recusado quando a pasta de programas ou a de identidade fica
dentro da pasta de cortes ou do repositório (por exemplo `cortes = "."`, que deixaria a esteira gravar entre os
episódios gravados).

### `[identidade]`

| Chave | Tipo | Padrão | O que faz |
|---|---|---|---|
| `encerramentos` | lista de caminhos | os quatro vídeos `Encerramentos/Final Corte (...).mp4` do canal original | Um vídeo por corte, em rodízio: o corte 1 usa o primeiro, o 2 o segundo, e assim por diante. `[]`: os cortes terminam na última fala, sem encerramento |
| `logo` | caminho | `"Logos/Logo sem Fundo.png"` | PNG transparente. Vai no cartão de notícia e na sobreposição |
| `sobreposicao` | caminho | gerada pela esteira (abaixo) | Imagem 1080x1920 transparente por cima do encerramento. `""`: nada por cima |

Os caminhos são relativos à pasta de identidade (ou absolutos).

**A sobreposição gerada.** Sem a chave `sobreposicao`, a esteira gera a imagem (a logo no alto e "SIGA @arroba")
na primeira montagem e guarda em `assets/`:

- com a arroba do canal original, é o `assets/encerramento.png` que vem no repositório, como sempre;
- com qualquer outra arroba, é `assets/encerramento-<arroba>.png`, fora do git. Um canal novo nunca herda a logo do
  original, e trocar de arroba gera uma imagem nova sozinho.

Trocou a logo e quer a sobreposição nova? Apague o arquivo gerado em `assets/` e monte de novo. Uma sobreposição
apontada em `[identidade] sobreposicao` que não existe é erro na montagem: a esteira não grava na pasta de
identidade.

### `[credenciais]`

| Chave | Tipo | Padrão | O que faz |
|---|---|---|---|
| `prefixo` | texto | `"tudo-e-politica"` | Prefixo dos nomes de serviço no Gerenciador de Credenciais |

Com o prefixo `P`, as chaves ficam em três serviços:

| Serviço | O que guarda | Padrão |
|---|---|---|
| `P` | Contas das redes (`publicar conectar`) | `tudo-e-politica` |
| `P-imagens` | Chaves das APIs de imagem (`imagens conectar`) | `tudo-e-politica-imagens` |
| `P-painel` | Código de acesso e chave de sessão do painel (`painel codigo`) | `tudo-e-politica-painel` |

**Trocar o prefixo esconde o que já foi guardado.** As chaves continuam no Gerenciador de Credenciais com o nome
antigo, mas a esteira passa a procurar no nome novo, e tudo parece desconectado. Por isso o prefixo é coisa de canal
novo: o `init` tira do nome do canal antes de qualquer conta ser conectada. Num canal que já tem contas, deixe como
está ou, se precisar trocar, rode `publicar conectar`, `imagens conectar` e `painel codigo` de novo.
Dois canais na mesma máquina precisam de prefixos diferentes.

## Conferir: `clipline doctor`

O `doctor` mostra o `clipline.toml` em uso (ou o erro dele), a raiz e de onde ela veio (padrão, `clipline.toml` ou
`CLIPLINE_RAIZ`), cada pasta, a identidade (nome e arroba, encerramentos, logo, sobreposição e prefixo das
credenciais) e avisa quando a identidade ainda é a padrão do canal original, sugerindo o `clipline init`.
`clipline doctor --json` dá a mesma lista como dados (`nome`, `estado`, `detalhe`).

## Claude Code

- `.claude/settings.json` dá ao agente acesso às pastas irmãs de sempre (`../Contexto`, `../2 - Cortes`...). Com
  outras pastas, troque `permissions.additionalDirectories` lá ou ponha as suas em `.claude/settings.local.json`. O
  `init` lembra disso nos próximos passos.
- O hook `.claude/hooks/travas.py` também protege a pasta de programas de `[pastas] programas` e nega ao agente
  editar o próprio `clipline.toml`, que decide onde a esteira grava.

## O que ainda é do canal original fora do `clipline.toml`

- Os nomes das tarefas do Agendador (`publicar instalar-tarefa`), em `esteira/publicar/tarefa.py`.
- O `User-Agent` dos pedidos à web (`esteira/rede.py`).
- O `assets/encerramento.png` do repositório, que só é usado com a arroba do canal original.
