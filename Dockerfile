# syntax=docker/dockerfile:1
#
# Imagem do clipline em CPU: a esteira (com ffmpeg) e o painel de revisão.
#
#   docker compose up --build        # painel em http://localhost:8765
#   docker compose run --rm clipline python -m esteira status "/canal/2 - Cortes/<episódio>"
#
# A esteira usa a pasta acima do repositório como raiz do canal, então o código fica em /canal/Automacao e as
# pastas do canal entram como volumes em /canal (ver compose.yaml). Sem GPU: o render usa libx264, e transcrever e
# vozes, que hoje pedem CUDA, ficam para o Windows com a placa NVIDIA.

# ---- 1. build do painel (React + Vite) -----------------------------------------------------------------------
FROM node:22-slim AS painel
WORKDIR /canal/Automacao/painel-web
COPY painel-web/package.json painel-web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY painel-web/ ./
# o vite.config.ts manda o build para ../esteira/painel/estatico
RUN npm run build

# ---- 2. esteira e painel em Python ---------------------------------------------------------------------------
FROM python:3.12-slim AS esteira

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CLIPLINE_CONTEINER=1

# ffmpeg sem versão fixa de propósito: o Debian troca a revisão do pacote e uma versão fixa quebraria o build.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 clipline
WORKDIR /canal/Automacao

# Dependências primeiro (camada que só muda com o pyproject.toml), sem as bibliotecas CUDA.
COPY pyproject.toml ./
COPY scripts/requisitos_cpu.py scripts/
RUN python scripts/requisitos_cpu.py painel > /tmp/requisitos.txt \
    && pip install -r /tmp/requisitos.txt \
    && rm /tmp/requisitos.txt

COPY --chown=1000:1000 . .
COPY --from=painel --chown=1000:1000 /canal/Automacao/esteira/painel/estatico esteira/painel/estatico
# Editável de propósito: a esteira acha a raiz do canal pela pasta do código (caminhos.py).
RUN pip install --no-deps -e . \
    && mkdir -p logs "/canal/1 - Programas" "/canal/2 - Cortes" "/canal/3 - Identidade" /canal/Contexto \
    && chown 1000:1000 /canal . logs "/canal/1 - Programas" "/canal/2 - Cortes" "/canal/3 - Identidade" /canal/Contexto

# o usuário clipline, sem root
USER 1000:1000
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/', timeout=4)"]
CMD ["python", "scripts/painel_conteiner.py", "--porta", "8765"]
