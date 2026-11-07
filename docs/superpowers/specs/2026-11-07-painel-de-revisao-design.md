# Painel de revisão (Fase 1 da interface web)

Data: 2026-11-07. Status: aprovado em conversa, aguardando revisão da spec.

## Objetivo

Uma interface web local para o dono do canal revisar os cortes de um episódio
numa tela só, no notebook ou no celular, na mesma Wi-Fi. Ela substitui a
navegação manual por `revisao.md`, pastas e arquivos. Tem dois usos ao mesmo
tempo: **uso real no canal** e **projeto de portfólio**, que depois vira open
source.

O fluxo atual continua: o Claude Code escolhe os cortes e escreve os textos, e
o dono do canal aprova. O painel lê e edita os mesmos arquivos e não duplica a
esteira.

### Fases da interface

| Fase | Conteúdo | Spec |
|---|---|---|
| **1** | Painel de revisão (esta spec) | este arquivo |
| 2 | Agendar pela tela (resumo e confirmação explícita) e acompanhar a fila | futura |
| 3 | Editor de cortes: transcrição clicável, ajuste de início e fim, re-renderização | futura |

### Critérios de sucesso da Fase 1

1. `python -m esteira painel` abre o painel no notebook com os episódios reais
   de `2 - Cortes/`.
2. Com `--rede` e o código de acesso, o mesmo painel abre no celular.
3. Para cada corte dá para ver: os dois vídeos (corte e final), as
   informações, os alertas, os nomes suspeitos e o guia de imagens.
4. O `post.md` é editado pela tela, com os mesmos avisos do
   `publicar agendar`, sem perder nada do resto do arquivo e sem sobrescrever
   uma edição feita por fora.
5. O `revisao.md` e o painel mostram os mesmos dados, porque vêm da mesma
   função.

### Fora da Fase 1

Enviar o vídeo final pela tela, corrigir nomes no glossário, agendar, editar
cortes, HTTPS, atalhos para o Explorer.

## Arquitetura

```
Automacao/
  esteira/painel/          backend FastAPI (pacote da esteira)
    __init__.py
    app.py                 cria o app, monta /api e serve o build estático
    rotas.py               endpoints /api/...
    leitura.py             episódios, cortes, status (usa revisao.dados_revisao)
    acesso.py              código de acesso, sessão, trava de tentativas
    estatico/              saída do `npm run build` (no .gitignore)
  painel-web/              frontend React + TypeScript + Vite
```

- **Pilha:** FastAPI + Uvicorn no backend; React + TypeScript + Vite no
  frontend. O Node só é necessário para desenvolver e gerar o build. Em uso
  normal roda um único processo Python.
- **Dependências novas** ficam num extra opcional `painel` no
  `pyproject.toml` (`fastapi`, `uvicorn`), para não pesar na esteira.
- **Comando:**
  - `python -m esteira painel`: escuta só em `127.0.0.1:8765`.
  - `python -m esteira painel --rede`: escuta em `0.0.0.0:8765`, exige o
    código de acesso e mostra no terminal o endereço da rede local.
  - `python -m esteira painel codigo`: gera um código novo (ver Acesso).
- **Sem build:** se `estatico/` não existir, o comando avisa
  "rode `npm run build` em painel-web/" e sai com erro.

### Uma fonte única de verdade

O `esteira/revisao.py` é dividido em duas partes:

- `dados_revisao(pasta) -> list[BlocoRevisao]`: devolve, para cada corte,
  número, título, pasta, clima, redes, data, música, antes, depois, alertas
  (de `registro.json` + nomes suspeitos), arquivos do vídeo final, guia
  presente e erro (`"registro ilegível"`, `"corte não montado"`,
  `"montagem ilegível"` ou a mensagem do `registro.json`).
- `escrever_revisao(pasta)`: só formata esses dados no mesmo Markdown de hoje.

Os testes atuais do `revisao` precisam continuar passando sem mudança. A API
usa `dados_revisao`.

### Nomes suspeitos

Hoje o Claude acrescenta esses nomes à mão no `revisao.md`, e eles se perdem
se o comando rodar de novo. Proposta:

- O Claude grava `nomes-suspeitos.json` na pasta do episódio, com o número do
  corte como chave: `{"4": ["Massa: conferir 'Felipe Massa'"]}`.
- `dados_revisao` lê esse arquivo e acrescenta os nomes aos alertas do corte.
  Arquivo ausente equivale a `{}`. Arquivo ilegível vira o alerta
  `"nomes-suspeitos.json ilegível"` em todos os cortes, sem derrubar nada.
- A etapa 10 do `docs/operacao.md` muda para descrever o arquivo. O texto
  exato é mostrado ao dono do canal para aprovação antes de ser salvo.

### Segurança das pastas

- O episódio é identificado pelo nome da pasta em `2 - Cortes/` e o corte,
  pelo número em `aprovados.json`. Todo caminho montado a partir da URL é
  resolvido e precisa ficar dentro de `CORTES`; se não ficar, a resposta é 403.
- Arquivos servidos: só `corte.mp4`, os vídeos de `video-final/`, as imagens
  de `imagens-sugeridas/` e os `.md` previstos. Nada fora dessa lista.
- A única gravação é o `post.md`, sempre por `caminhos.garantir_escrita()`.
- `1 - Programas/` e `video-final/` nunca são escritos.

## API

Todas as respostas são em JSON e as mensagens de erro, em português.

| Método e rota | Faz |
|---|---|
| `POST /api/entrar` | recebe `{codigo}`, cria a sessão (só com `--rede`) |
| `GET /api/episodios` | lista os episódios: nome, total de cortes, quantos têm vídeo final, próxima data |
| `GET /api/episodios/{ep}` | cortes do episódio (blocos de `dados_revisao` + selo de status) |
| `GET /api/episodios/{ep}/calendario` | datas de `aprovados.json` e o texto do `calendario.md` |
| `GET /api/episodios/{ep}/descartados` | texto do `candidatos.md` |
| `GET /api/episodios/{ep}/cortes/{n}` | bloco do corte, o `guia.md` e a lista de imagens sugeridas |
| `GET /api/episodios/{ep}/cortes/{n}/video` | `corte.mp4`, com suporte a range |
| `GET /api/episodios/{ep}/cortes/{n}/video-final/{arquivo}` | vídeo final, com suporte a range |
| `GET /api/episodios/{ep}/cortes/{n}/imagens/{arquivo}` | imagem sugerida |
| `GET /api/episodios/{ep}/cortes/{n}/post` | campos do post, partes só para leitura, crédito, versão e avisos |
| `POST /api/episodios/{ep}/cortes/{n}/post/conferir` | avisos para um rascunho, sem gravar |
| `PUT /api/episodios/{ep}/cortes/{n}/post` | grava o post se a versão bater; senão responde 409 |

**Selo de status do corte**, em ordem de prioridade: `erro`, `com alerta`
(alertas ou avisos do post), `sem vídeo final`, `pronto`.

Códigos HTTP: 401 sem sessão, 403 caminho fora de `2 - Cortes/`, 404 episódio,
corte ou arquivo inexistente, 409 conflito no `post.md`, 422 corpo inválido,
429 login travado.

## Telas

1. **Entrada** (só com `--rede`): campo do código de acesso.
2. **Episódios:** um cartão por episódio com nome, número de cortes,
   "N de M prontos" e próxima data.
3. **Episódio**, em abas:
   - **Cortes:** grade de cartões com título, clima, redes, data e selo.
   - **Calendário:** linha do tempo por dia, separando TikTok/Shorts e
     Instagram, com o `calendario.md` exibido abaixo.
   - **Descartados:** `candidatos.md` exibido.
4. **Corte:** uma coluna no celular, duas no notebook.
   - Player do `corte.mp4` e, se houver, do vídeo final, com alternância.
   - Redes, data, música, antes, depois, alertas, nomes suspeitos, erro.
   - Guia de imagens exibido mais as miniaturas das fotos sugeridas.
   - Editor do post.

O Markdown é exibido com um renderizador que não executa HTML embutido.

## Edição do post.md

- **Campos:** título do YouTube (contador até 100), descrição do YouTube,
  Instagram (até 2200), TikTok (até 2200). As seções "Música" e
  "Publicação sugerida" aparecem só para leitura, com o crédito da música
  visível para copiar.
- **Avisos:** a API roda `publicar.post.conferir_textos()` com o crédito de
  `montagem.json` e as redes do corte (Instagram só se `instagram: true`). O
  frontend pede os avisos ao rascunho com atraso de 400 ms após a digitação.
- **Gravação:** a função nova `publicar.post.gravar_textos(caminho, textos)`
  troca só o título, a descrição e os textos de Instagram e TikTok, e mantém
  todo o resto do arquivo igual byte a byte. Ela grava num arquivo temporário
  na mesma pasta e depois troca pelo original (`os.replace`).
- **Versão e conflito:** a versão é o hash SHA-256 do conteúdo do arquivo. O
  `GET` devolve a versão e o `PUT` a envia de volta. Se o arquivo mudou nesse
  meio tempo, a resposta é 409 com a versão atual. O painel mostra a versão
  nova e mantém o rascunho na tela, sem gravar nada.
- **Avisos não bloqueiam:** dá para salvar com problemas. Eles ficam
  destacados no corte e no selo.
- **Sem post.md**, ou sem as seções obrigatórias: o editor mostra o erro de
  `ler_post` e fica desabilitado. O painel não cria `post.md`.

## Acesso pela rede

- `python -m esteira painel codigo` gera um código aleatório de 8 caracteres
  (`secrets`), guarda o hash no keyring (serviço `tudo-e-politica-painel`) e
  mostra o código uma vez no terminal. Também gera uma nova chave de sessão,
  o que derruba as sessões abertas. Nada vai para arquivo.
- Sem código cadastrado, `--rede` recusa iniciar e manda rodar
  `painel codigo`.
- Ao entrar, o servidor emite um cookie assinado com a chave de sessão
  (`HttpOnly`, `SameSite=Strict`, 30 dias).
- Depois de 5 erros seguidos, o login trava por 1 minuto (resposta 429).
- Sem `--rede` (só `127.0.0.1`), não há login.
- **Limitação assumida:** HTTP sem TLS. Serve para a Wi-Fi de casa, não para
  rede pública. O README diz isso.
- O firewall do Windows pode perguntar na primeira vez. Quem responde é o dono
  do canal; o painel não mexe nessa configuração.

## Erros

- Arquivo ausente ou ilegível nunca derruba a tela. O bloco do corte leva
  `erro` e o cartão mostra a mensagem, como o `revisao` já faz hoje.
- Episódio sem `aprovados.json` aparece na lista com "sem cortes aprovados".
- O frontend mostra as mensagens da API como vieram, sem traduzir códigos.

## Testes

- **Backend (pytest):** `TestClient` do FastAPI sobre um episódio falso em
  `tmp_path`, com `CORTES` trocado por monkeypatch e o keyring trocado por um
  falso. Cobre:
  - lista de episódios, blocos e selos;
  - caminho malicioso (`..`, absoluto, link simbólico) com resposta 403;
  - vídeo com range (206);
  - login, sessão, trava de tentativas;
  - post: leitura, avisos, gravação, conflito 409;
  - `gravar_textos`: ler e gravar sem mudar nada deixa o arquivo idêntico;
  - `nomes-suspeitos.json` ausente, válido e ilegível.
- **Refatoração do revisao:** os testes atuais passam sem mudança, mais testes
  de `dados_revisao`.
- **Frontend:** Vitest + Testing Library para contadores, avisos, conflito e
  selos.
- **Fumaça:** um teste Playwright abre o painel com o episódio falso, edita um
  post e salva.

## Dependências e ordem

- A Fase 1 usa `esteira/publicar/post.py`, que ainda não tem commit (trabalho
  da publicação em andamento). Esse trabalho precisa de commit antes de a
  implementação do painel começar.
- O pacote `painel` só importa FastAPI dentro do comando `painel`, para a CLI
  continuar funcionando sem o extra instalado.
