#!/usr/bin/env bash
# Instala o clipline num comando (Linux e macOS; também roda no Git Bash do Windows).
#
#   scripts/instalar.sh [--sem-painel] [--canal "Nome do canal"]
#
# Confere o Python (3.12 ou 3.13) e o Node (22.12 ou mais novo), cria o .venv, instala o pacote com os extras
# painel e dev, gera o build do painel, cria as pastas do canal ao lado do repositório se faltarem e roda o doctor.
# Pode rodar de novo: o que já existe fica como está (nada é apagado nem sobrescrito).
# CLIPLINE_PYTHON=/caminho/do/python escolhe o interpretador.
set -euo pipefail

passo() { printf '\n==> %s\n' "$*"; }
erro() { printf 'Erro: %s\n' "$*" >&2; exit 1; }
uso() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; }

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAIZ="$(dirname "$REPO")"
SEM_PAINEL=0
CANAL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --sem-painel) SEM_PAINEL=1 ;;
    --canal)
      [ $# -ge 2 ] || erro "--canal precisa de um nome"
      CANAL="$2"
      shift
      ;;
    -h | --help) uso; exit 0 ;;
    *) erro "opção desconhecida: $1 (veja --help)" ;;
  esac
  shift
done
# Tudo roda de dentro do repositório: "python -m esteira" pega primeiro a pasta esteira/ do diretório atual.
cd "$REPO"

versao_aceita() { "$@" -c 'import sys; sys.exit(0 if sys.version_info[:2] in ((3, 12), (3, 13)) else 1)' >/dev/null 2>&1; }

achar_python() {
  if [ -n "${CLIPLINE_PYTHON:-}" ]; then
    versao_aceita "$CLIPLINE_PYTHON" || erro "CLIPLINE_PYTHON=$CLIPLINE_PYTHON não é Python 3.12 nem 3.13."
    PYTHON=("$CLIPLINE_PYTHON")
    return
  fi
  local candidato versao
  for candidato in python3.12 python3.13 python3 python; do
    if command -v "$candidato" >/dev/null 2>&1 && versao_aceita "$candidato"; then
      PYTHON=("$candidato")
      return
    fi
  done
  if command -v py >/dev/null 2>&1; then # lançador do Python no Windows (Git Bash)
    for versao in 3.12 3.13; do
      if versao_aceita py "-$versao"; then
        PYTHON=(py "-$versao")
        return
      fi
    done
  fi
  erro "Python 3.12 ou 3.13 não encontrado. Instale (python.org ou o gerenciador de pacotes do sistema) e rode de novo."
}

conferir_node() {
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 ||
    erro "Node.js não encontrado. Instale o Node 22.12 ou mais novo (nodejs.org) ou rode com --sem-painel."
  node -e 'const [a, b] = process.versions.node.split(".").map(Number); process.exit(a > 22 || (a === 22 && b >= 12) ? 0 : 1)' ||
    erro "Node $(node --version) é antigo para o build do painel. Instale o 22.12 ou mais novo, ou rode com --sem-painel."
}

python_do_venv() {
  if [ -x "$REPO/.venv/bin/python" ]; then
    printf '%s\n' "$REPO/.venv/bin/python"
  elif [ -x "$REPO/.venv/Scripts/python.exe" ]; then
    printf '%s\n' "$REPO/.venv/Scripts/python.exe"
  fi
}

pasta_vazia() { [ -z "$(ls -A "$1" 2>/dev/null)" ]; }

criar_layout_do_canal() {
  local pasta
  for pasta in "1 - Programas" "2 - Cortes" "3 - Identidade"; do
    mkdir -p "$RAIZ/$pasta"
  done
  # Regras de exemplo só onde ainda não há regra nenhuma: um Contexto/ do canal nunca recebe arquivo de exemplo.
  if [ ! -d "$RAIZ/Contexto" ] || pasta_vazia "$RAIZ/Contexto"; then
    mkdir -p "$RAIZ/Contexto"
    cp -R "$REPO/Contexto.exemplo/." "$RAIZ/Contexto/"
    echo "Contexto/ criado com as regras de exemplo; reescreva com as do seu canal."
  fi
}

layout_completo() {
  local pasta
  for pasta in "1 - Programas" "2 - Cortes" "3 - Identidade" "Contexto"; do
    [ -d "$RAIZ/$pasta" ] || return 1
  done
  ! pasta_vazia "$RAIZ/Contexto"
}

passo "Python"
achar_python
echo "$("${PYTHON[@]}" --version) (${PYTHON[*]})"

if [ "$SEM_PAINEL" = 0 ]; then
  passo "Node"
  conferir_node
  echo "Node $(node --version), npm $(npm --version)"
fi

passo "Ambiente virtual (.venv)"
VENV_PY="$(python_do_venv)"
if [ -z "$VENV_PY" ]; then
  [ ! -e "$REPO/.venv" ] || erro "$REPO/.venv existe mas não tem Python. Apague essa pasta e rode de novo."
  "${PYTHON[@]}" -m venv "$REPO/.venv"
  VENV_PY="$(python_do_venv)"
  echo "criado em $REPO/.venv"
else
  versao_aceita "$VENV_PY" ||
    erro "o .venv existente usa $("$VENV_PY" --version 2>&1), e o projeto pede 3.12 ou 3.13. Apague $REPO/.venv e rode de novo."
  echo "já existe ($("$VENV_PY" --version)); só atualizo os pacotes"
fi

passo "Pacote clipline com os extras painel e dev"
(cd "$REPO" && "$VENV_PY" -m pip install --upgrade pip && "$VENV_PY" -m pip install -e ".[painel,dev]")

if [ "$SEM_PAINEL" = 0 ]; then
  passo "Build do painel (painel-web/)"
  (cd "$REPO/painel-web" && npm ci --no-audit --no-fund && npm run build)
else
  passo "Build do painel: pulado (--sem-painel)"
fi

passo "Pastas do canal em $RAIZ"
if layout_completo; then
  echo "já existem; nada mudou"
elif "$VENV_PY" -m esteira init --help >/dev/null 2>&1; then
  ARGS=(init "$RAIZ" --sem-perguntas)
  [ -z "$CANAL" ] || ARGS+=(--canal "$CANAL")
  "$VENV_PY" -m esteira "${ARGS[@]}"
else
  criar_layout_do_canal
  echo "1 - Programas/, 2 - Cortes/, 3 - Identidade/ e Contexto/ prontos"
fi

passo "Diagnóstico (esteira doctor)"
if (cd "$REPO" && "$VENV_PY" -m esteira doctor); then
  echo
  echo "Tudo pronto."
else
  echo
  echo "Instalação feita. O doctor apontou o que ainda falta (linhas FALTA acima): modelos de rosto em modelos/"
  echo "(veja modelos/LEIA.md), ffmpeg no PATH ou encerramentos em 3 - Identidade/."
fi
echo "Para abrir o painel: $VENV_PY -m esteira painel"
