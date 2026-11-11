"""`esteira doctor` (o ambiente está pronto?) e `esteira status` (em que etapa está cada corte?).

Os dois servem ao dono, ao painel e ao Claude Code: dizem o que falta e qual o próximo comando.
Nenhum deles mostra um segredo; no máximo diz se ele existe.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from esteira import caminhos


@dataclass
class Item:
    nome: str
    estado: str  # "ok" | "aviso" | "falta"
    detalhe: str = ""

    def como_dict(self) -> dict:
        return asdict(self)


def _tem_modulo(nome: str) -> bool:
    try:
        return importlib.util.find_spec(nome) is not None
    except (ImportError, ValueError):
        return False


def _ffmpeg() -> list[Item]:
    from esteira.midia import binario

    itens = []
    for nome in ("ffmpeg", "ffprobe"):
        caminho = binario(nome)
        try:
            saida = subprocess.run([caminho, "-version"], capture_output=True, text=True, timeout=20)
            versao = saida.stdout.split("\n")[0] if saida.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            versao = ""
        itens.append(Item(nome, "ok" if versao else "falta", versao or f"não encontrado; coloque {nome} em bin/ ou no PATH"))
    if itens[0].estado == "ok":
        try:
            encoders = subprocess.run([binario("ffmpeg"), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.TimeoutExpired):
            encoders = ""
        if "h264_nvenc" in encoders:
            itens.append(Item("NVENC", "ok", "ffmpeg com h264_nvenc (sem GPU NVIDIA, o render recua para libx264)"))
        else:
            itens.append(Item("NVENC", "aviso", "sem h264_nvenc: o render usa libx264 (mais lento)"))
    return itens


def _gpu() -> list[Item]:
    itens = [Item("faster-whisper", "ok" if _tem_modulo("faster_whisper") else "falta", "transcrição")]
    if _tem_modulo("torch"):
        try:
            import torch

            itens.append(Item("CUDA", "ok" if torch.cuda.is_available() else "aviso",
                              torch.cuda.get_device_name(0) if torch.cuda.is_available() else "torch sem GPU: vozes vai ser lento"))
        except Exception as erro:  # torch quebrado por DLL faltando, por exemplo
            itens.append(Item("CUDA", "aviso", f"torch não carregou: {type(erro).__name__}"))
    else:
        itens.append(Item("pyannote (vozes)", "aviso", 'opcional: instale o extra "vozes" para o comando vozes'))
    itens.append(Item("HF_TOKEN", "ok" if os.environ.get("HF_TOKEN") else "aviso",
                      "definido" if os.environ.get("HF_TOKEN") else "não definido: o comando vozes não roda"))
    return itens


def _arquivos() -> list[Item]:
    from esteira.rostos import MODELO_DETECTOR, MODELO_RECONHECEDOR, MODELOS

    itens = []
    for modelo in (MODELO_DETECTOR, MODELO_RECONHECEDOR):
        itens.append(Item(f"modelos/{modelo}", "ok" if (MODELOS / modelo).is_file() else "falta", "ver modelos/LEIA.md"))
    itens.append(Item("Contexto/", "ok" if caminhos.CONTEXTO.is_dir() else "falta",
                      str(caminhos.CONTEXTO) if caminhos.CONTEXTO.is_dir() else "copie Contexto.exemplo/ para ../Contexto"))
    itens.append(Item("Contexto/glossario.md", "ok" if (caminhos.CONTEXTO / "glossario.md").is_file() else "falta",
                      "nomes da transcrição e pessoas reais"))
    itens.append(Item("2 - Cortes/", "ok" if caminhos.CORTES.is_dir() else "aviso", str(caminhos.CORTES)))
    faltando = [e.name for e in caminhos.ENCERRAMENTOS if not e.is_file()]
    itens.append(Item("encerramentos", "ok" if not faltando else "aviso",
                      "todos presentes" if not faltando else f"faltam: {', '.join(faltando)}"))
    catalogo = caminhos.MUSICAS / "catalogo.json"
    itens.append(Item("musicas/catalogo.json", "ok" if catalogo.is_file() else "aviso", "biblioteca de música"))
    estatico = Path(__file__).parent / "painel" / "estatico" / "index.html"
    itens.append(Item("build do painel", "ok" if estatico.is_file() else "aviso", "npm run build em painel-web/"))
    itens.append(Item("fastapi e uvicorn", "ok" if _tem_modulo("fastapi") and _tem_modulo("uvicorn") else "aviso", "painel"))
    return itens


def _credenciais(ler=None) -> list[Item]:
    """Só diz se existe; nunca o valor."""
    if not _tem_modulo("keyring"):
        return [Item("keyring", "aviso", "sem o pacote keyring: chaves de IA e redes indisponíveis")]
    if ler is None:
        import keyring

        def ler(servico, campo):
            try:
                return keyring.get_password(servico, campo)
            except Exception:
                return None
    from esteira.imagens_ia.chaves import SERVICO as SERVICO_IA
    from esteira.publicar.credenciais import SERVICO as SERVICO_REDES

    itens = []
    for provedor in ("openai", "google"):
        itens.append(Item(f"chave {provedor}", "ok" if ler(SERVICO_IA, f"{provedor}:chave") else "aviso", "imagens de IA"))
    for rede, campo in (("youtube", "refresh_token"), ("instagram", "token"), ("tiktok", "refresh_token")):
        itens.append(Item(f"conta {rede}", "ok" if ler(SERVICO_REDES, f"{rede}:{campo}") else "aviso", f"publicar conectar {rede}"))
    return itens


def doctor(ler_credencial=None) -> list[Item]:
    versao = f"{sys.version_info.major}.{sys.version_info.minor}"
    itens = [Item("Python", "ok" if sys.version_info[:2] == (3, 12) else "aviso", f"{versao} (o projeto é testado no 3.12)")]
    return itens + _ffmpeg() + _gpu() + _arquivos() + _credenciais(ler_credencial)


def hash_das_regras(contexto: Path | None = None) -> str:
    """Marca curta do conteúdo de Contexto/: muda quando qualquer regra muda (vai na `origem` do agente)."""
    contexto = Path(contexto or caminhos.CONTEXTO)
    marca = hashlib.sha256()
    if contexto.is_dir():
        for arquivo in sorted(contexto.rglob("*.md")):
            marca.update(arquivo.relative_to(contexto).as_posix().encode("utf-8"))
            marca.update(arquivo.read_bytes())
    return marca.hexdigest()[:12]


# --- status ---------------------------------------------------------------------------------------------


def _video_final(destino: Path) -> bool:
    pasta = destino / "video-final"
    return pasta.is_dir() and any(a.suffix.lower() in (".mp4", ".mov") for a in pasta.iterdir() if a.is_file())


def status_episodio(pasta: Path) -> dict:
    """Etapa de cada corte e o próximo passo. Nunca levanta por arquivo ilegível: põe no `erro`."""
    from esteira.cortar import ler_aprovados, pasta_do_corte

    pasta = Path(pasta)
    transcricao = pasta / "transcricao"
    episodio = {
        "pasta": pasta.name,
        "transcricao": (transcricao / "palavras.json").is_file(),
        "vozes": (transcricao / "vozes.json").is_file(),
        "pessoas": (transcricao / "pessoas.json").is_file(),
        "aprovados": (pasta / "aprovados.json").is_file(),
        "calendario": (pasta / "calendario.md").is_file(),
        "revisao": (pasta / "revisao.md").is_file(),
        "cortes": [],
        "erro": None,
        "proximo": None,
    }
    if not episodio["transcricao"]:
        episodio["proximo"] = "transcrever"
        return episodio
    if not episodio["aprovados"]:
        episodio["proximo"] = "vozes" if not episodio["vozes"] else "escolher os cortes (skill escolher-cortes)"
        return episodio
    try:
        cortes = ler_aprovados(pasta)
    except (OSError, ValueError) as erro:
        episodio["erro"] = str(erro)
        episodio["proximo"] = "corrigir aprovados.json (esteira validar)"
        return episodio
    fila = {}
    try:
        dados = json.loads((pasta / "postagens.json").read_text("utf-8"))
        for item in dados.get("itens", []):
            if item.get("estado") != "cancelado":
                fila.setdefault(item.get("numero"), []).append(f"{item.get('rede')}: {item.get('estado')}")
    except (OSError, ValueError, AttributeError):
        pass
    for corte in cortes:
        destino = pasta_do_corte(pasta, corte)
        trabalho = destino / "trabalho"
        etapas = {
            "planos": (trabalho / "enquadramento.json").is_file(),
            "preparar": (trabalho / "montagem.json").is_file(),
            "imagens": (trabalho / "pedidos.json").is_file(),
            "montar": (destino / "corte.mp4").is_file(),
            "post": (destino / "post.md").is_file(),
            "aprovado": _video_final(destino),
        }
        ordem = [
            ("planos", "planos"), ("preparar", "preparar"), ("imagens", "momentos de imagem (skill momentos-de-imagem)"),
            ("montar", "montar"), ("post", "textos (skill textos-e-calendario)"), ("aprovado", "aprovar no painel"),
        ]
        proximo = next((passo for etapa, passo in ordem if not etapas[etapa]), None)
        publicacao = fila.get(corte.numero, [])
        if proximo is None:
            proximo = "agendar (publicar agendar)" if not publicacao else "acompanhar (publicar fila)"
        episodio["cortes"].append({
            "numero": corte.numero, "titulo": corte.titulo, "pasta": destino.name, "etapas": etapas,
            "publicacao": publicacao, "data": corte.data, "proximo": proximo,
        })
    pendentes = [c["proximo"] for c in episodio["cortes"] if c["proximo"] not in ("acompanhar (publicar fila)",)]
    episodio["proximo"] = pendentes[0] if pendentes else "nada: tudo publicado ou agendado"
    return episodio


def texto_do_status(status: dict) -> str:
    sim = lambda v: "✓" if v else "·"  # noqa: E731
    linhas = [
        status["pasta"],
        f"  transcrição {sim(status['transcricao'])}  vozes {sim(status['vozes'])}  pessoas {sim(status['pessoas'])}  "
        f"aprovados {sim(status['aprovados'])}  calendário {sim(status['calendario'])}  revisão {sim(status['revisao'])}",
    ]
    if status["erro"]:
        linhas.append(f"  erro: {status['erro']}")
    for c in status["cortes"]:
        e = c["etapas"]
        marcas = "  ".join(f"{nome} {sim(valor)}" for nome, valor in e.items())
        linhas.append(f"  {c['numero']:02d} {marcas}  →  {c['proximo']}")
        if c["publicacao"]:
            linhas.append(f"     publicação: {', '.join(c['publicacao'])}")
    linhas.append(f"Próximo passo: {status['proximo']}")
    return "\n".join(linhas)
