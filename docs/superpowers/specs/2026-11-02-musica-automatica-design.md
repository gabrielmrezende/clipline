# Música automática (Parte 2): design

Data: 2026-11-02
Status: desenho aprovado em conversa, spec aguardando revisão do dono do canal.

## 1. Objetivo

Todo corte sai com música de fundo escolhida pela esteira conforme o clima,
sem o dono do canal escolher faixa. Só ferramentas gratuitas, com a licença
de cada faixa registrada e o crédito pronto no post.

O motor da Parte 1 já mixa a música do `montagem.json`. Esta parte cria a
biblioteca, a escolha e o crédito.

## 2. Decisões

- Biblioteca local, montada uma vez e reaproveitada nos episódios.
- Fonte: Incompetech (Kevin MacLeod), licença CC BY 4.0. Uso comercial
  liberado, com crédito no post.
- 4 climas, cerca de 10 faixas cada: `leve`, `tenso`, `inspirador`,
  `reflexivo`.
- A esteira propõe as faixas a partir do catálogo; o dono do canal ouve e
  aprova a lista antes do download.
- Risco conhecido: terceiros às vezes reivindicam indevidamente faixas do
  Incompetech no Content ID. A reivindicação se contesta com a licença.

## 3. Arquivos

```text
Automacao/
  musicas/
    proposta.md        lista para aprovação (no Git)
    aprovadas.json     faixas aprovadas por clima (no Git)
    catalogo.json      faixas baixadas (no Git)
    uso.json           histórico de uso por corte (no Git)
    leve/ tenso/ inspirador/ reflexivo/   arquivos .mp3 (fora do Git)
  esteira/
    musica.py          proposta, download, escolha
```

`*.mp3` entra no `.gitignore`.

## 4. Biblioteca

### 4.1 Proposta (`esteira musicas propor`)

Lê o catálogo público do Incompetech
(`https://incompetech.com/music/royalty-free/pieces.json`), com título,
arquivo, duração, instrumentos, descrição e marcações de clima (`feel`).

Correspondência de clima:

| Clima | Marcações aceitas |
|---|---|
| leve | Bright, Bouncy, Humorous |
| tenso | Suspenseful, Driving, Intense |
| inspirador | Uplifting, Epic |
| reflexivo | Calming, Relaxed, Somber |

Filtros:
- duração de 1 min 30 s a 6 min;
- fora as marcações Eerie, Unnerving, Dark, Aggressive e Action;
- fora faixas com vocal (instrumentos com "Voice", "Vocal" ou "Choir");
- preferência por instrumentação leve (piano, cordas, violão, sintetizador,
  pads) sobre bateria pesada e metais.

Saída: `musicas/proposta.md`, com 10 faixas por clima, cada uma com título,
duração, instrumentos, link para ouvir e motivo. O dono do canal aprova,
corta ou troca. A aprovação é gravada em `musicas/aprovadas.json`.

### 4.2 Download (`esteira musicas baixar`)

Baixa só as faixas de `aprovadas.json` para `musicas/<clima>/`, a partir de
`https://incompetech.com/music/royalty-free/mp3-royaltyfree/<arquivo>`.

Cada faixa é normalizada para -16 LUFS (filtro `loudnorm` do ffmpeg) antes
de entrar na biblioteca. Assim o mesmo ganho de mixagem soa igual em
qualquer faixa.

`catalogo.json` guarda, por faixa: título, clima, duração, arquivo (relativo
a `musicas/`) e crédito:

```text
Música: <Título> — Kevin MacLeod (incompetech.com), licença CC BY 4.0
```

Falha em uma faixa: ela fica fora do catálogo, o comando informa, e as
demais seguem. Faixa já baixada não é baixada de novo.

## 5. Escolha por corte

No `preparar`, para cada corte de `aprovados.json`:

1. O `clima` precisa ser um dos 4. A validação (`esteira validar`) acusa
   outro valor.
2. Candidatas: faixas do catálogo com esse clima.
3. Ficam de fora as usadas nos últimos 10 cortes, de qualquer episódio
   (`uso.json`, ordenado pela data de uso). Se todas foram usadas, volta a
   valer a menos recente.
4. Preferência: duração maior que o corte; depois, a que está há mais
   tempo sem uso; empate pela ordem do catálogo.
5. A escolha é determinística.

`uso.json` guarda uma entrada por corte (chave `episódio/pasta do corte`),
com arquivo e data. Preparar o mesmo corte de novo substitui a entrada.

Sem faixa para o clima: o corte sai sem música e a revisão mostra
`sem música para o clima <clima>`.

`Musica` ganha `titulo: str = ""` e `credito: str = ""`. O `arquivo`
continua absoluto, e `volume_db` continua -20 por padrão.

## 6. Crédito e revisão

- `revisao.md` mostra `Música: <Título>` em cada corte.
- O `post.md` traz o crédito da receita na descrição do YouTube e nos textos
  de Instagram e TikTok. A seção "Música" deixa de sugerir busca no CapCut.

## 7. Mudanças de regra

Aplicadas na implementação, com o texto mostrado ao dono do canal antes de
salvar:
- `Contexto/redes-e-publicacao.md`: crédito da música no post.
- `Automacao/docs/operacao.md`: os 4 climas, a etapa da música e a nova
  seção "Música" do post.

## 8. Testes

1. Automáticos: filtro da proposta com catálogo de exemplo; escolha (clima,
   rodízio, preferência de duração, clima vazio, preparar de novo);
   normalização com som gerado; crédito na receita e na revisão; validação
   do clima.
2. Teste real: remontar os 10 cortes do F1 com música; o dono do canal ouve
   e aprova.

## 9. Critérios de sucesso

- Os 10 cortes do F1 saem com música do clima certo, sem faixa repetida.
- O dono do canal aprova o volume da música sem precisar de ajuste por corte.
- Todo post traz o crédito correto.

## 10. Fora desta parte

- Escolha de música por IA ouvindo o trecho.
- Corte da faixa no ponto "mais forte" da música.
- Outras fontes (Pixabay, Free Music Archive, YouTube Audio Library).
