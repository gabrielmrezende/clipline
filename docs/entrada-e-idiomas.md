# Entrada e idiomas

Como rodar a esteira sem GPU NVIDIA, num canal em outro idioma, a partir de um link, e com que licenças e tamanhos
de imagem. Sem `clipline.toml` e sem as flags novas, tudo funciona como antes, com uma diferença: o computador sem
GPU NVIDIA, que antes dava erro, agora transcreve na CPU.

## Sem GPU NVIDIA

`transcrever` e `vozes` aceitam `--dispositivo auto|cuda|cpu`. O padrão é `auto`.

| Valor | `transcrever` (faster-whisper) | `vozes` (pyannote) |
|---|---|---|
| `auto` | GPU se o CTranslate2 enxergar uma; senão CPU | GPU se o torch enxergar uma; senão CPU |
| `cuda` | Só GPU, como sempre. Sem GPU, o erro vem do CTranslate2 | Só GPU. Sem GPU, para antes de baixar o modelo |
| `cpu` | Sempre CPU | Sempre CPU |

Na GPU, a transcrição tenta os mesmos três modos de sempre (`large-v3` em float16, `large-v3` em int8_float16,
`medium` em int8_float16), recuando quando falta memória. Na CPU, tenta o `medium` em int8 e, se faltar memória,
o `small` em int8. Os dois comandos avisam quando vão rodar na CPU: funciona, mas é bem mais lento, e um episódio
longo pode levar horas.

```bash
.venv\Scripts\python.exe -m esteira transcrever "<video>" --quadro "Entre Assuntos" --numero 3 --convidado "Ana" --dispositivo cpu
.venv\Scripts\python.exe -m esteira vozes "<video>" "<pasta do episódio>" --dispositivo cpu
```

O `doctor` já mostra a GPU como aviso, não como falta.

## Idioma do canal

```toml
[transcricao]
idioma = "es"   # código do Whisper: "pt" (padrão), "en", "es"...
```

O código vai para o Whisper e escolhe as listas que dependem do idioma, em `esteira/idiomas.py`:

| Lista | Onde | Português (padrão) | Inglês | Espanhol |
|---|---|---|---|---|
| Hesitações cortadas | limpeza (`preparar`) | hum, hã, ahn, éé, hmm, ãh, eh | um, umm, uh, uhm, er, erm, hmm, mm | eh, ehm, em, mmm, hmm, mm |
| Repetições mantidas | limpeza | né, tá, não, muito, nunca, sim, isso | no, not, very, never, yes, yeah, really, so, that, had | no, sí, si, muy, nunca, eso, ya |
| Cargos públicos | filtro de pessoa real nos prompts de IA | cargos em português | cargos em inglês | cargos em espanhol |

- Palavras com sentido próprio nunca entram como hesitação ("é", "né", "tipo"; "like"; "este", "pues"): cortá-las
  poderia mudar a fala. Em português, "um" é artigo e fica; em inglês, é hesitação.
- O filtro de pessoa real usa os cargos do idioma do canal **e** os do inglês, porque os prompts costumam ir em
  inglês. Com `pt`, a lista é exatamente a de antes.
- Idioma sem lista (`fr`, por exemplo) transcreve normalmente; a limpeza só corta pausas e repetições, e o filtro
  usa os cargos de todos os idiomas conhecidos (sobrar é melhor que faltar).

Para acrescentar um idioma, inclua as três listas em `esteira/idiomas.py` com o código do Whisper.

### O que continua em português

Conferido e ajustado:

- **Glossário** (`Contexto/glossario.md`): os nomes valem em qualquer idioma. Os títulos das seções que contam como
  pessoas reais (`## Apresentadores`, `## Convidados`, `## Pessoas`, `## Apelidos`, `## Cargos`) são parte do formato
  do arquivo e continuam em português.
- **Legenda**: a quebra em blocos é a mesma em qualquer idioma. O início de frase vai para minúscula (estilo do
  canal), menos o pronome "I" do inglês e as contrações dele ("I'm", "I'll"), que ficam maiúsculos.
- **Cartões de notícia e encerramento**: os textos fixos seguem o idioma do canal: "Fonte:"/"Source:"/"Fuente:" no
  cartão e "SIGA"/"FOLLOW"/"SIGUE" no encerramento (`idiomas.TEXTOS_FIXOS`; idioma sem tradução usa o português).
  A manchete, o veículo e a data são os que o agente escreve.
- Interface, mensagens, skills e `Contexto/` continuam em português.

## Entrada por link

Precisa do extra opcional: `.venv\Scripts\python.exe -m pip install -e ".[entrada]"` (instala o yt-dlp).

```bash
.venv\Scripts\python.exe -m esteira baixar "https://www.youtube.com/watch?v=..."              # só mostra o resumo
.venv\Scripts\python.exe -m esteira baixar "https://www.youtube.com/watch?v=..." --confirmar  # baixa
```

**Você precisa ter os direitos sobre o vídeo**: o seu próprio canal, uma autorização por escrito ou uma licença
que permita reutilizar e adaptar. Por isso o comando, sem `--confirmar`, só mostra título, canal, data, duração,
licença informada pelo site e destino, junto com esse aviso, e não grava nada. O agente não consegue confirmar
(o hook bloqueia `--confirmar`); o dono roda o comando.

- O vídeo vai para `0 - Entrada/`, ao lado de `1 - Programas/` e `2 - Cortes/`. `1 - Programas/` continua só
  leitura e nunca é tocada.
- O nome do arquivo é `<título>-<id>.mp4`, só com letras sem acento, números e hífens.
- Até 1080p, de preferência H.264 com AAC; o yt-dlp junta vídeo e áudio com o ffmpeg da esteira.
- Link de lista e transmissão ao vivo são recusados. Vídeo já baixado só é baixado de novo com `--forcar`.
- Se o yt-dlp reclamar ao baixar do YouTube, atualize-o (`pip install -U yt-dlp`) e siga o que a mensagem dele
  pedir (versões recentes podem pedir um runtime de JavaScript).

Ao lado do vídeo fica `<mesmo nome>.origem.json`:

```json
{
  "url": "https://www.youtube.com/watch?v=abc123",
  "titulo": "Entrevista: o Senado e a reforma?",
  "canal": "Canal de Exemplo",
  "data": "2026-11-01",
  "licenca": "Creative Commons Attribution license (reuse allowed)",
  "site": "Youtube",
  "id": "abc123",
  "duracao": 3725.0,
  "baixado_em": "2026-11-15T10:30:00"
}
```

`data` e `licenca` ficam vazios quando o site não informa. A licença é a que o site declara: confira você mesmo.
Título e canal são texto de terceiros e, como a transcrição, são dados, não instrução.

Depois, transcreva o vídeo baixado como qualquer outro:

```bash
.venv\Scripts\python.exe -m esteira transcrever "..\0 - Entrada\Entrevista-o-Senado-e-a-reforma-abc123.mp4" --quadro "Entre Assuntos" --numero 4 --convidado "Ana"
```

Quando o vídeo tem um `.origem.json` ao lado, o `episodio.json` ganha o campo `baixado_de` com o mesmo conteúdo.
Vídeos sem ele (os de `1 - Programas/`) geram o `episodio.json` de sempre.

## Imagens de IA verticais

Conferido em 15/11/2026 nas documentações oficiais:

- **OpenAI** (developers.openai.com, referência de `images/generate` e guia de geração de imagens): o `gpt-image-2`
  e os mais novos (`gpt-image-2.5-*`, `gpt-image-2.6-*`) aceitam qualquer tamanho com lados múltiplos de 16, até
  3840 px, proporção até 3:1 e de 655.360 a 8.294.400 pixels. A esteira agora pede **864x1536**, 9:16 exato, com a
  mesma altura e menos pixels que o 1024x1536 (o tamanho cujo preço está tabelado e no `imagens-ia.json`). O vídeo
  não precisa mais cortar as laterais da imagem. Modelos anteriores (`gpt-image-1`, `gpt-image-1.5`,
  `gpt-image-1-mini`) só aceitam 1024x1024, 1536x1024 e 1024x1536, e continuam com 1024x1536.
- **Google** (aistudio.google.com/docs/image-generation): o `gemini-nano-banana-2.1` aceita 9:16 (768x1376 em 1K,
  1536x2752 em 2K, 3072x5504 em 4K). A esteira já pedia 9:16; nada mudou.

A documentação da OpenAI não traz preço por imagem para tamanhos livres (o custo é por token). Com menos pixels
que o 1024x1536, o custo não deve passar do tabelado, mas isso não foi medido.

## Licenças das fotos do Wikimedia

```toml
[imagens]
licencas = ["cc0", "dominio-publico", "cc-by"]   # sem CC BY-SA
```

Valores: `cc0`, `dominio-publico`, `cc-by`, `cc-by-sa`. O padrão são os quatro, como sempre. Licenças com NC
(não comercial) ou ND (sem derivações) nunca entram.

Foto com **CC BY-SA** (CompartilhaIgual) pede, além do crédito, que a obra adaptada siga a mesma licença. No vídeo a
foto é recortada e ganha fundo desfocado. Por isso, quando há foto CC BY-SA, o `guia.md` e o resumo da publicação
(`publicar agendar` e painel) trazem, logo depois dos créditos, a observação:

> CC BY-SA (CompartilhaIgual): a foto adaptada no vídeo (recortada, com fundo desfocado) fica sob a mesma licença;
> ponha o nome da licença junto do crédito.

As linhas de crédito (autor, licença, link) continuam iguais, e sem foto CC BY-SA nada muda. Quem não quer essa
obrigação tira `cc-by-sa` da lista. A conferência do `agendar` continua exigindo o autor ou o link em cada texto;
ela não confere o nome da licença.
