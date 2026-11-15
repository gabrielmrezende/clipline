# Enquadramento suave e tela dividida

Dois recursos de enquadramento, **desligados por padrão**. Sem a seção `[enquadramento]` no `clipline.toml`, o
`planos` grava o mesmo `enquadramento.json` de sempre e o `montar` gera o mesmo `corte.mp4`.

| Recurso | O que faz | Chave |
|---|---|---|
| Acompanhamento suave | Dentro de um plano, o centro do recorte segue o rosto de quem fala, sem tremer | `suave` |
| Tela dividida | Diálogo rápido entre duas pessoas da mesma cena sai empilhado: uma em cima, a outra embaixo | `tela_dividida` |

O código está em `esteira/acompanhar.py` e `esteira/dividida.py` (lógica pura, sem ffmpeg nem modelos), em
`esteira/planos.py` (recorte que muda no tempo e marcas da folha) e em `esteira/render.py` (filtros do ffmpeg).

## Como ligar

No `clipline.toml` (modelo em `clipline.exemplo.toml`):

```toml
[enquadramento]
suave = true
tela_dividida = true
```

Os dois são independentes. Valem no próximo `planos`, que é onde o enquadramento é decidido; o `montar` só segue o
que está no `enquadramento.json`.

- **Episódio novo:** rodar `planos` normalmente.
- **Episódio já enquadrado:** o `planos` não sobrescreve `enquadramento.json` existente. Para aplicar, o dono roda
  `planos --forcar` (refaz a detecção de rostos e o enquadramento, preserva a ligação e os nomes de `pessoas.json`) e
  depois `montar --forcar`. Não é preciso rodar `preparar` de novo. Como todo `--forcar`, quem decide é o dono.

## Acompanhamento suave

Hoje cada plano tem um centro e um zoom fixos. Com `suave = true`, o `planos` olha as detecções do rosto enquadrado
ao longo do plano (as mesmas que ele já faz, uma a cada 0,5 s, guardadas em `trabalho/rostos.json`) e calcula o
trajeto do centro do recorte:

1. **Detecções espúrias saem.** Rosto com altura fora de ±40% da mediana do plano (outro rosto, detecção ruim) e
   amostra isolada que pula para longe da mediana das vizinhas. Um movimento de verdade fica, porque as vizinhas
   acompanham. Só valem as detecções da mesma cena (outra câmera depois de um corte não conta).
2. **Zona morta.** Enquanto o rosto anda menos de 8% do recorte, o recorte fica parado. Quando sai da zona, o recorte
   persegue o rosto até alcançá-lo e para de novo ali.
3. **Mola criticamente amortecida** com limite de velocidade (0,6 recorte por segundo, tempo de mola de 0,5 s): o
   recorte acelera e freia sem tranco e não passa do ponto. Ela olha o rosto 0,2 s à frente para não chegar atrasada
   (o vídeo é gravado, então dá para antecipar).
4. **Sempre dentro do quadro.** O centro fica preso de forma que o recorte inteiro caiba na imagem original.
5. **Poucos pontos-chave.** O trajeto, simulado quadro a quadro, é reduzido (Douglas-Peucker) a pontos tais que a reta
   entre dois deles erra menos de 0,15% do quadro. No máximo 2,5 pontos por segundo.

O zoom continua constante dentro do plano. Plano de grupo (zoom 1,0 com vários rostos), plano sem rosto, rosto com
poucas detecções (menos de 3, ou menos da metade das esperadas) e rosto que não se mexe ficam fixos, como sempre.

No `enquadramento.json`, o plano ganha `trajeto`: `[[tempo, x, y], ...]`, com o tempo em segundos do episódio e `x`, `y`
de 0 a 1, como os do plano. O `x` e o `y` do plano continuam lá (a média), mas o trajeto manda.

```json
{"inicio": 732.4, "fim": 741.0, "x": 0.36, "y": 0.47, "zoom": 1.35,
 "trajeto": [[732.4, 0.302, 0.47], [734.1, 0.304, 0.47], [735.0, 0.37, 0.471], [741.0, 0.398, 0.471]]}
```

No render, o `crop` do ffmpeg recebe uma expressão de `t` que interpola os pontos-chave em linha reta, sem `if`
aninhado: o valor inicial mais uma rampa `clip((t-t0)/d,0,1)` por trecho. O crop avalia a expressão a cada quadro;
o resto do filtro (fundo desfocado, faixa, legenda) não muda. Quando o filtro inteiro passa de 20.000 caracteres
(corte longo com muitos trechos suaves), ele vai num arquivo (`-/filter_complex`, ou `-filter_complex_script` no
ffmpeg anterior ao 7), porque a linha de comando do Windows aceita só 32.767.

## Tela dividida

Com `tela_dividida = true`, o `planos` procura, em cada cena (entre dois cortes de câmera), diálogo rápido entre as
duas pessoas que estão na tela e mais falam ali. As duas precisam aparecer na cena (em pelo menos metade das
amostras, como sempre) e estar ligadas a uma voz em `pessoas.json`.

Regras de entrada e saída (histerese, para não piscar entre layouts):

- Não contam como turno a fala com menos de 0,6 s nem a que cabe inteira dentro da fala da outra pessoa (o "aham" de
  quem ouve). A mesma voz depois de uma pausa de até 1,5 s é o mesmo turno.
- **Entra** com 3 turnos curtos seguidos (menos de 4 s cada), alternando as duas vozes, sem pausa maior que 1,5 s
  entre eles. A tela dividida começa no início do primeiro desses turnos.
- **Fica** enquanto os turnos têm menos de 7 s. Um turno de 4 a 7 s não tira da tela dividida (e sozinho não põe).
- **Sai** no começo de um turno de 7 s ou mais, ou numa pausa maior que 1,5 s.
- Depois: tela cheia de menos de 3 s entre duas divididas vira dividida; tela dividida que começa ou termina a menos
  de 3 s da borda da cena vai até a borda; tela dividida com menos de 4 s não entra; pedaço de plano comum com menos
  de 2 s colado nela entra nela.

Layout: duas metades de 1080x960 empilhadas, sem o fundo desfocado. A pessoa da esquerda na imagem original vai em
cima. Cada metade recorta o rosto com o mesmo zoom de sempre (níveis 1,0 a 2,0, meta de 28% da altura): em cima, os
olhos ficam a 36% da altura da metade; embaixo, a 42%, para sobrar espaço na emenda. **A legenda, nesses trechos, vai
para a emenda das duas metades** (centro em y = 960), longe dos dois rostos; nos trechos de tela cheia continua onde
sempre esteve. Uma tela de legenda que atravessa a troca de layout é cortada ali (cada pedaço no seu lugar; pedaço
com menos de 0,2 s some, porque só piscaria).

No `enquadramento.json`, o plano dividido tem `divisao`: `[cima, baixo]`, cada um com `pessoa`, `x`, `y` e `zoom` (e
`trajeto`, se `suave` também estiver ligado: cada metade acompanha o seu rosto). O `x`, `y` e `zoom` do próprio plano
são o enquadramento de grupo, só para referência.

```json
{"inicio": 812.0, "fim": 826.5, "x": 0.5, "y": 0.5, "zoom": 1.0,
 "divisao": [{"pessoa": "P1", "x": 0.3, "y": 0.4, "zoom": 1.7}, {"pessoa": "P2", "x": 0.7, "y": 0.38, "zoom": 1.7}]}
```

## Como conferir

`trabalho/planos.jpg`, como sempre, um quadro por plano (o do meio do plano):

- **SUAVE** (canto de cima, à direita): o retângulo ciano é o recorte no meio do plano; a linha ciano é o caminho
  do centro do recorte, com um ponto onde ele termina.
- **DIVIDIDA**: o retângulo ciano é a metade de cima; o magenta, a de baixo. O rótulo traz os dois nomes
  (`3 Arthur + P2 · ...`). **DIVIDIDA SUAVE** quando as metades também acompanham o rosto.

Depois do `montar`, ver o `corte.mp4` nos trechos marcados: a legenda na emenda não pode cobrir rosto, e o recorte
suave não pode cortar a cabeça de quem se mexe.

## Como corrigir à mão

No `trabalho/enquadramento.json` (depois, `montar --forcar`; não precisa de `preparar`):

- Recorte suave que incomoda: apague o `trajeto` do plano. Ele volta a ser fixo no `x`, `y` e `zoom` do plano.
- Tela dividida que não devia estar ali: apague a `divisao`. O plano vira o enquadramento de grupo (`zoom` 1,0 no
  centro) ou o que você puser em `x`, `y` e `zoom`.
- Metade mal enquadrada: ajuste `x`, `y` e `zoom` dela. Com `trajeto` na metade, apague-o ou o trajeto manda.
- `divisao` precisa ter exatamente duas metades; senão o `montar` para aquele corte com um erro que diz isso.

## Custo de render

Medido em 15/11/2026 nesta máquina (RTX 4070, 16 núcleos, dividida com outros processos, então os números variam de
uma rodada para outra), num vídeo sintético 1920x1080 de 60 s (`testsrc2`): seis planos de 10 s com zoom 1,7, cinco
faixas (pausas removidas) e legenda, sem encerramento. Mediana de três rodadas do `renderizar_final` inteiro:

| Encoder | Fixo (hoje) | Suave | Tela dividida |
|---|---|---|---|
| NVENC (`h264_nvenc`, o padrão) | 14,5 s | 15,1 s (+5%) | 8,9 s (−38%) |
| libx264 (sem GPU NVIDIA) | 20,6 s | 21,3 s (+3%) | 18,0 s (−13%) |

Só o filtro (decodificar, recortar e compor, saída nula), tempo de CPU do `-benchmark` do ffmpeg, mediana de cinco:
fixo 46,1 s, suave 49,1 s (+6%), tela dividida 18,8 s (−59%).

O rosto do teste balança 6% do quadro a cada 6 s, sem parar, o que dá 22 pontos-chave por plano de 10 s (perto do
teto); rosto real, que mais para do que anda, dá menos. O crop com expressão custa pouco perto do desfoque do fundo
(`gblur`) e da codificação. A tela dividida sai mais barata porque não tem fundo desfocado: são dois recortes
redimensionados para 1080x960.

## Limites

- O zoom não muda dentro de um plano; só o centro anda.
- O acompanhamento usa as detecções a cada 0,5 s; movimento muito rápido (levantar de repente) chega com um pouco de
  atraso, pela mola e pelo limite de velocidade.
- A tela dividida depende da ligação voz → pessoa, que o `planos` tira dos closes (cenas com um rosto só) de todos os
  cortes do episódio. Se uma das pessoas nunca aparece sozinha, a voz dela fica sem pessoa; nesse caso, preencha a
  `ligacao` em `pessoas.json` à mão e rode `planos --forcar`.
- Três ou mais pessoas na cena: a tela dividida usa as duas que mais falam ali.
