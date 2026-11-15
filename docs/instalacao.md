# Instalação em um comando, Docker e ferramentas do repositório

## Instalar em um comando

Clone o repositório dentro da pasta do canal (a esteira usa a pasta *acima* do clone como raiz) e rode:

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
```

```bash
# Linux e macOS (também roda no Git Bash do Windows)
scripts/instalar.sh
```

O script:

1. confere o Python 3.12 ou 3.13 (no Windows, pelo lançador `py`) e o Node 22.12 ou mais novo;
2. cria o `.venv` e instala o pacote com os extras `painel` e `dev`;
3. gera o build do painel (`npm ci` e `npm run build` em `painel-web/`);
4. cria `1 - Programas/`, `2 - Cortes/`, `3 - Identidade/` e `Contexto/` ao lado do repositório se faltarem. Usa o
   `esteira init` quando ele existe; senão copia as regras de exemplo de `Contexto.exemplo/`, mas só para um
   `Contexto/` que ainda não existe ou está vazio;
5. roda o `esteira doctor`, que diz o que ainda falta (os modelos de rosto, por exemplo; veja `modelos/LEIA.md`).

Rodar de novo não estraga nada: o `.venv` é reaproveitado, os pacotes só são atualizados e nenhuma pasta ou regra do
canal é sobrescrita. Se o `.venv` existente for de outro Python, o script para e pede para apagá-lo.

| Opção | Para quê |
|---|---|
| `-SemPainel` / `--sem-painel` | Pula o build do painel e dispensa o Node |
| `-Canal "Nome"` / `--canal "Nome"` | Nome do canal, repassado ao `esteira init` |
| `CLIPLINE_PYTHON` (variável) | Caminho de um Python 3.12 ou 3.13 específico |

O `torch` e o `pyannote` do comando `vozes` continuam à parte (extra `vozes`; veja o README).

## Docker

A imagem tem a esteira em CPU (com o ffmpeg do Debian, que renderiza com `libx264`) e o painel. Os comandos
`transcrever` e `vozes` hoje pedem uma GPU NVIDIA e ficam para a instalação no Windows.

```bash
docker compose up --build                                   # painel em http://localhost:8765
docker compose run --rm clipline python -m esteira doctor
docker compose run --rm clipline python -m esteira status "/canal/2 - Cortes/<episódio>"
```

O `compose.yaml` monta as pastas do canal (por padrão, a pasta acima do repositório; troque com
`CLIPLINE_CANAL=/caminho/do/canal`): `1 - Programas/`, `3 - Identidade/` e `Contexto/` só para leitura e
`2 - Cortes/` para gravação. Também monta `musicas/` e `modelos/` do repositório e guarda os downloads do Whisper num
volume. As pastas precisam existir; o script de instalação cria as que faltam. O contêiner roda sem root, com o
uid 1000; no Linux, se o seu usuário tiver outro uid, acrescente `user: "<uid>:<gid>"` ao serviço para ele conseguir
gravar em `2 - Cortes/` e `musicas/`.

O painel publica a porta só em `127.0.0.1` do computador. Dentro do contêiner ele escuta em todas as interfaces
(`scripts/painel_conteiner.py`, que se recusa a rodar fora de um contêiner), porque o Docker não alcança o
`127.0.0.1` de dentro. Para abrir no celular, use o painel fora do Docker com `--rede` e o código de acesso.

Publicar não funciona no contêiner: as credenciais ficam no Gerenciador de Credenciais do Windows.

## Ferramentas do repositório

- **pre-commit:** `pip install pre-commit && pre-commit install` liga as conferências antes de cada commit: o mesmo
  `ruff check` da CI, arquivo grande esquecido (mais de 1 MB), conflito de merge, nome que o Windows não aceita e
  JSON, TOML e YAML válidos. Nenhum hook reescreve arquivo.
- **`requirements-ci.txt`:** as dependências da CI em versões fixas. Para reproduzir a CI num venv limpo:
  `python -m pip install -r requirements-ci.txt` e depois `python -m pytest -n 4`.
- **Dependabot:** uma vez por mês, um pull request com as versões menores e as correções de cada ecossistema (pip, npm
  e GitHub Actions) e um pull request por versão maior. O React 19 fica de fora até a rodada própria.
- **Teste de ponta a ponta em paralelo:** `ESTEIRA_E2E_PORTA=8777 npm run e2e` sobe o painel de teste em outra porta
  (o padrão é 8766), para rodar duas cópias do repositório ao mesmo tempo.
