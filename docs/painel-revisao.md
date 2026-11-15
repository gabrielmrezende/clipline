# Painel: revisão do corte

Complementa o [`painel.md`](painel.md) com o que ajuda a revisar um corte: o player com atalhos, as áreas das
redes, as remoções da limpeza na linha do corte, as confirmações e o tema.

## Player

Os atalhos valem na tela do corte, com o foco fora de um campo de texto (título, descrição, legenda, busca) e sem
diálogo aberto. O `?` (ou o botão `?` ao lado do player) mostra a lista.

| Tecla | O que faz |
| --- | --- |
| Espaço ou K | Toca ou pausa |
| J / L | Volta ou avança 10 s |
| ← / → | Volta ou avança 5 s |
| , / . | Quadro anterior ou seguinte (1/30 s) e pausa |
| < / > | Mais devagar ou mais rápido: 0,5x, 0,75x, 1x, 1,25x, 1,5x, 2x |
| Home / End | Começo ou fim do vídeo |
| A | Troca as áreas da rede: TikTok, Shorts, Reels, desligadas |
| ? | Abre a ajuda |

A velocidade também tem um seletor abaixo do vídeo e continua a mesma quando se troca entre o corte e um vídeo
final. Espaço num botão continua sendo clicar no botão, e as setas no seletor continuam mudando o seletor.

### Áreas das redes

O seletor "Áreas da rede" (ou a tecla A) põe por cima do vídeo, hachurado em vermelho, o que a interface do
TikTok, do Shorts ou do Reels cobre: as abas no alto, a coluna de botões à direita e o nome, texto e música
embaixo. O retângulo tracejado é a área livre. Serve para ver se uma legenda ou imagem some atrás dos botões.

As medidas são aproximadas, tiradas dos guias públicos de áreas seguras de 2025 e 2026 para um quadro 1080x1920
(`painel-web/src/componentes/areasSeguras.ts`). Cada rede muda a interface de tempos em tempos: na dúvida,
confira no app. A escolha fica guardada no navegador.

## Remoções da limpeza na linha do corte

A linha do corte, abaixo do player, marca onde o `preparar` tirou alguma coisa do corte:

- **âmbar**: fala tirada (hesitação, repetição, ou um trecho sem motivo registrado);
- **cinza**: pausa tirada;
- **azul**: onde entra uma imagem (como antes).

"O que a limpeza tirou" abre a lista com tempo, motivo, palavras tiradas e duração. Clicar num item leva o player
2 s antes da emenda, para ouvir se a fala continua natural. Pausas com som mantidas não aparecem: não foram
tiradas.

As marcas vêm de `GET /api/episodios/{ep}/cortes/{n}/remocoes` (`esteira/painel/rotas_revisao.py`, só leitura).
A rota junta os cortes de verdade (as `faixas` do `trabalho/montagem.json`) com os motivos do
`trabalho/edicoes.md` e põe cada corte no tempo do `corte.mp4`, com a mesma conta do `remapear`. Sem
`montagem.json` a lista vem vazia com o aviso "rode preparar"; sem `edicoes.md`, os cortes aparecem como
"trecho removido".

```json
{
  "remocoes": [{"tempo": 3.55, "duracao": 0.6, "motivo": "pausa", "texto": "", "episodio": 104.0}],
  "removido": 0.6,
  "avisos": []
}
```

`tempo` é no corte.mp4; `episodio` é onde começa o trecho tirado, no tempo do episódio.

## Confirmações

Tudo o que o painel pedia com a caixa do navegador agora abre um diálogo do próprio painel: título, resumo, os
itens envolvidos e, quando gasta dinheiro, o custo em destaque. O botão de confirmar muda de cor conforme o
caso: azul no normal, âmbar quando gasta dinheiro (com o preço no rótulo) e vermelho quando não tem volta. Nesses
dois últimos o foco começa em "Cancelar". Esc ou clicar fora cancela, e o foco volta ao botão que abriu.

## Tema

Os três botões no topo escolhem claro, escuro ou o do sistema (o padrão). A escolha fica no navegador, vale para
as outras abas e é aplicada antes da primeira pintura pelo `public/tema.js`, então a tela não pisca. O arquivo é
separado porque a CSP do painel não aceita script dentro da página.

As cores do escuro escolhido à mão (`painel-web/src/componentes/tema.css`) repetem as do escuro do sistema
(`estilo.css`); um teste confere que os dois blocos continuam iguais. Mudou uma cor do escuro: mude nos dois.

## Carregamento

Cada tela é baixada na primeira visita (a lista de episódios não traz o código da tela do corte). Enquanto a
tela ou os dados chegam, aparece a forma do que vem no lugar do "Carregando…"; o leitor de tela continua
ouvindo o texto. Com "reduzir movimento" ligado no sistema, os esqueletos ficam parados.
