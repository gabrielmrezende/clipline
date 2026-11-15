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


ORIGEM_DA_RAIZ = {
    "padrão": "padrão: a pasta acima do repositório",
    "clipline.toml": "[pastas] raiz do clipline.toml",
    "CLIPLINE_RAIZ": "variável de ambiente CLIPLINE_RAIZ",
}


def _configuracao() -> tuple[list[Item], object | None]:
    """O clipline.toml e a Config lida dele (None se estiver quebrado)."""
    from esteira import config

    erro = caminhos.ERRO_CONFIG
    ajustes = None
    if not erro:
        try:
            ajustes = config.atual()
        except config.ErroConfig as falha:
            erro = str(falha)
    if erro:
        return [Item("clipline.toml", "falta", f"{erro} (nada é gravado até corrigir)")], None
    if config.ARQUIVO.is_file():
        return [Item("clipline.toml", "ok", str(config.ARQUIVO))], ajustes
    return [Item("clipline.toml", "ok", "ausente: valem os padrões (modelo em clipline.exemplo.toml)")], ajustes


def _pastas() -> list[Item]:
    """As pastas em uso, de onde vieram e se existem."""
    origem = ORIGEM_DA_RAIZ.get(caminhos.PASTAS.origem_raiz, caminhos.PASTAS.origem_raiz)
    raiz = caminhos.RAIZ
    itens = [Item("pasta raiz", "ok" if raiz.is_dir() else "falta",
                  f"{raiz} ({origem})" if raiz.is_dir() else f"{raiz} não existe ({origem}); rode clipline init")]
    contexto = caminhos.CONTEXTO
    itens.append(Item("pasta de contexto", "ok" if contexto.is_dir() else "falta",
                      str(contexto) if contexto.is_dir() else f"{contexto} não existe; rode clipline init "
                      "ou copie Contexto.exemplo/ para lá"))
    itens.append(Item("glossário", "ok" if (contexto / "glossario.md").is_file() else "falta",
                      "nomes da transcrição e pessoas reais (glossario.md na pasta de contexto)"))
    for nome, pasta, papel in (
        ("pasta de programas", caminhos.PROGRAMAS, "episódios gravados, só leitura"),
        ("pasta de cortes", caminhos.CORTES, "saída da esteira"),
        ("pasta de identidade", caminhos.IDENTIDADE, "logo e encerramentos"),
    ):
        itens.append(Item(nome, "ok" if pasta.is_dir() else "aviso",
                          f"{pasta} ({papel})" if pasta.is_dir() else f"{pasta} não existe ({papel})"))
    if caminhos.ENTRADA.is_dir():  # opcional: só aparece para quem já baixou por link
        itens.append(Item("pasta de entrada", "ok", f"{caminhos.ENTRADA} (vídeos baixados com baixar)"))
    return itens


def _identidade(ajustes) -> list[Item]:
    """Nome, arroba, encerramentos, logo e sobreposição em uso; avisa quando ainda são os do canal original."""
    from esteira import config

    itens = []
    if ajustes is not None:
        original = config.Config()
        if ajustes.canal == original.canal or ajustes.arroba == original.arroba:
            itens.append(Item("identidade do canal", "aviso",
                              f"{ajustes.canal} ({ajustes.arroba}) é a identidade padrão do canal original; "
                              "se o seu canal é outro, rode clipline init"))
        else:
            itens.append(Item("identidade do canal", "ok", f"{ajustes.canal} ({ajustes.arroba})"))
    encerramentos = caminhos.ENCERRAMENTOS
    faltando = [e.name for e in encerramentos if not e.is_file()]
    if not encerramentos:
        itens.append(Item("encerramentos", "ok", "nenhum: os cortes terminam sem vídeo de encerramento"))
    else:
        itens.append(Item("encerramentos", "ok" if not faltando else "aviso",
                          f"{len(encerramentos)} vídeos, todos presentes" if not faltando
                          else f"faltam: {', '.join(faltando)}"))
    logo = caminhos.LOGO
    itens.append(Item("logo", "ok" if logo.is_file() else "aviso",
                      str(logo) if logo.is_file() else f"não encontrada: {logo} (cartão de notícia e sobreposição)"))
    if ajustes is not None:
        sobreposicao = caminhos.sobreposicao_do_canal(ajustes.arroba, config.Config().arroba)
        if sobreposicao is None:
            detalhe, estado = "nenhuma: nada por cima do encerramento", "ok"
        elif sobreposicao.is_file():
            detalhe, estado = str(sobreposicao), "ok"
        elif sobreposicao.parent == caminhos.AUTOMACAO / "assets":
            detalhe, estado = f"{sobreposicao} (gerada da logo e da arroba na primeira montagem)", "ok"
        else:
            detalhe, estado = f"não encontrada: {sobreposicao} ([identidade] sobreposicao)", "aviso"
        itens.append(Item("sobreposição", estado, detalhe))
        prefixo = ajustes.credenciais_prefixo
        padrao = " (padrão)" if prefixo == config.Config().credenciais_prefixo else ""
        itens.append(Item("credenciais", "ok", f"prefixo {prefixo}{padrao} no Gerenciador de Credenciais"))
    return itens


def _arquivos() -> list[Item]:
    from esteira.rostos import MODELO_DETECTOR, MODELO_RECONHECEDOR, MODELOS

    itens = []
    for modelo in (MODELO_DETECTOR, MODELO_RECONHECEDOR):
        itens.append(Item(f"modelos/{modelo}", "ok" if (MODELOS / modelo).is_file() else "falta", "ver modelos/LEIA.md"))
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
    from esteira.imagens_ia.chaves import servico as servico_ia
    from esteira.publicar.credenciais import servico as servico_redes

    try:
        SERVICO_IA, SERVICO_REDES = servico_ia(), servico_redes()
    except ValueError:  # clipline.toml quebrado: o item clipline.toml já diz o que corrigir
        return []
    itens = []
    for provedor in ("openai", "google"):
        itens.append(Item(f"chave {provedor}", "ok" if ler(SERVICO_IA, f"{provedor}:chave") else "aviso", "imagens de IA"))
    for rede, campo in (("youtube", "refresh_token"), ("instagram", "token"), ("tiktok", "refresh_token")):
        itens.append(Item(f"conta {rede}", "ok" if ler(SERVICO_REDES, f"{rede}:{campo}") else "aviso", f"publicar conectar {rede}"))
    return itens


def _tarefa_publicacao(executar=None) -> list[Item]:
    """A tarefa agendada de publicação: instalada? É a antiga, que grava o log pelo cmd? Só consulta."""
    from esteira import config
    from esteira.publicar import agendador

    try:
        feito = agendador.situacao(agendador.sistema_atual(), config.ler().canal, Path.home(),
                                   executar or agendador.executar_no_sistema)
    except Exception as erro:  # o doctor nunca para por causa de um item
        return [Item("tarefa de publicação", "aviso", f"não deu para conferir ({type(erro).__name__})")]
    return [Item("tarefa de publicação", feito.estado, feito.detalhe)]


def doctor(ler_credencial=None, executar_tarefa=None) -> list[Item]:
    versao = f"{sys.version_info.major}.{sys.version_info.minor}"
    itens = [Item("Python", "ok" if sys.version_info[:2] == (3, 12) else "aviso", f"{versao} (o projeto é testado no 3.12)")]
    configuracao, ajustes = _configuracao()
    return (itens + _ffmpeg() + _gpu() + configuracao + _pastas() + _identidade(ajustes) + _arquivos()
            + _credenciais(ler_credencial) + _tarefa_publicacao(executar_tarefa))


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
