"""Trocar o início e o fim de um corte pelo painel (o editor pela transcrição).

O painel grava o trecho novo no aprovados.json (com uma cópia da versão anterior em `aprovados-anteriores/`) e refaz
o corte: preparar e, se ele já tinha vídeo, montar. O preparar refaz a receita do zero; o que dá para preservar volta
depois dele:

- a música escolhida (a mesma faixa e o mesmo volume; o uso.json fica como estava);
- as telas da legenda corrigidas no painel, quando o texto gerado daquela tela continua o mesmo no trecho novo;
- os momentos de imagem (pedidos.json, em tempos do corte.mp4): passam para os tempos novos e as imagens prontas
  ganham o nome da chave nova; os que ficam fora do trecho são descartados, com o motivo.

Tudo o que muda é guardado antes num marcador (`trabalho/trecho-em-andamento.json`). Se o preparar ou a montagem
falham, o corte volta ao que era; se o painel cai no meio, ele desfaz na próxima vez que abrir. `video-final/` nunca
é tocado: se o corte já estava aprovado, a aprovação deixa de valer e o painel pede para aprovar de novo.
"""

import base64
import copy
import json
import os
import re
import sys
import time
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path

from esteira.aprovacao import EXTENSOES_VIDEO, da_esteira
from esteira.caminhos import EscritaProibida, garantir_escrita, gravar_atomico
from esteira.cortar import CORTE_MP4, IMAGENS_SUGERIDAS, TRABALHO, VIDEO_FINAL, ler_aprovados, pasta_do_corte
from esteira.enquadrar import _mmss
from esteira.fluxo_imagens import CREDITOS, GUIA, IA, SUGERIDAS, _ler_sugeridas, chave_momento, escrever_guia, ler_ia
from esteira.legenda import corrigir_palavras, escrever_srt, montar_cues
from esteira.limpeza import planejar_limpeza
from esteira.modelos import Corte, Cue, Palavra
from esteira.musica import MUSICAS, gravar_uso, ler_uso
from esteira.painel.troca_musica import (
    VIDEO_ABERTO,
    Resultado,
    _alertas_da_montagem,
    _corte_pronto_para_montar,
    _substituir_com_espera,
    resumir_erro,
)
from esteira.pedidos import ARQUIVO as PEDIDOS, Momento, ajustar_tempos, pedidos_dos_bytes, rotulo_momento
from esteira.publicar.post import trocar_credito, versao_dos_bytes
from esteira.receita import NOME_ARQUIVO, Musica, Receita, gravar_receita, ler_receita
from esteira.transcrever import ler_palavras
from esteira.validar import INTERVALO_DE_FRASE, _termina_frase, validar_trecho

MARCADOR = "trecho-em-andamento.json"
VIDEO_GUARDADO = "corte-antes-do-trecho.mp4"
PASTA_COPIAS = "aprovados-anteriores"
SAIU_DO_TRECHO = "fora do trecho novo do corte"
NOME_EM_USO = "as imagens não puderam mudar de nome (outro arquivo já usa o nome novo)"
APROVADOS_MUDOU = "O aprovados.json mudou enquanto o pedido esperava. Abra o trecho de novo e confira."
ALERTAS_PLANOS = "alertas-planos.json"
EPSILON = 1e-6
FOLGA_ENQUADRAMENTO = 0.05  # segundos sem plano que não valem um aviso

Preparar = Callable[[Path, int, list[str]], str]
Montar = Callable[[Path, int], str]


# --- lógica pura ------------------------------------------------------------------------------------------------


def tempo_texto(segundos: float) -> str:
    """724.1 -> "12:04,1"; com hora, "1:02:03,4"."""
    decimos = round(max(0.0, segundos) * 10)
    s, d = divmod(decimos, 10)
    h, resto = divmod(s, 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d},{d}" if h else f"{m}:{s:02d},{d}"


def segundos_texto(segundos: float) -> str:
    return f"{segundos:.1f} s".replace(".", ",")


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def alinhar(palavras: list[Palavra], inicio: float, fim: float) -> tuple[float, float]:
    """O início vai para o começo da palavra mais próxima e o fim, para o fim da palavra mais próxima.

    É o mesmo critério do `validar` (a palavra mais perto de cada ponta)."""
    if not palavras:
        raise ValueError("transcrição sem palavras")
    primeira = min(palavras, key=lambda p: abs(p.inicio - inicio))
    ultima = min(palavras, key=lambda p: abs(p.fim - fim))
    return round(primeira.inicio, 3), round(ultima.fim, 3)


def pode_iniciar(palavras: list[Palavra], i: int) -> bool:
    """A palavra começa frase (pela regra do `validar`): o corte pode começar nela."""
    if i == 0:
        return True
    anterior = palavras[i - 1]
    return _termina_frase(anterior) or palavras[i].inicio - anterior.fim > INTERVALO_DE_FRASE


def pode_terminar(palavras: list[Palavra], i: int) -> bool:
    """A palavra fecha frase (pela regra do `validar`): o corte pode terminar nela."""
    if _termina_frase(palavras[i]):
        return True
    return i + 1 == len(palavras) or palavras[i + 1].inicio - palavras[i].fim > INTERVALO_DE_FRASE


def no_episodio(t: float, faixas: list[tuple[float, float]]) -> float | None:
    """Tempo do corte.mp4 (sem o encerramento) -> tempo do episódio. Depois do fim do corte: None."""
    acumulado = 0.0
    for de, ate in faixas:
        if t <= acumulado + (ate - de) + EPSILON:
            return de + max(0.0, t - acumulado)
        acumulado += ate - de
    return None


def no_corte(t: float, faixas: list[tuple[float, float]]) -> float:
    """Tempo do episódio -> tempo do corte.mp4. Numa pausa cortada, vai para o ponto do corte; fora, para a ponta."""
    acumulado = 0.0
    for de, ate in faixas:
        if t < de:
            return acumulado
        if t <= ate:
            return acumulado + t - de
        acumulado += ate - de
    return acumulado


def remapear_momentos(
    momentos: list[Momento],
    faixas_antigas: list[tuple[float, float]],
    faixas_novas: list[tuple[float, float]],
    inicio: float,
    fim: float,
) -> tuple[list[Momento], int, list[str]]:
    """Os momentos nos tempos do corte novo: (cópia, quantos mudaram de tempo, rótulos dos que saíram do trecho).

    Cada momento vai para a linha do episódio pelas faixas antigas e volta pelas novas, então as pausas cortadas dos
    dois lados contam. Fica no corte quem começa dentro do trecho novo; quem sai é descartado com o motivo e guarda o
    tempo antigo (assim a chave e as imagens dele continuam batendo)."""
    novos = copy.deepcopy(momentos)
    duracao = sum(b - a for a, b in faixas_novas)
    deslocados, saidos = 0, []
    for posicao, m in enumerate(novos, 1):
        de = no_episodio(m.inicio, faixas_antigas)
        if de is None or not inicio - EPSILON <= de < fim:
            if not m.descartar:
                saidos.append(rotulo_momento(posicao, m, painel=True))
                m.descartar, m.motivo = True, SAIU_DO_TRECHO
            continue
        ate = no_episodio(m.fim, faixas_antigas)
        novo_inicio = round(no_corte(de, faixas_novas), 3)
        novo_fim = round(min(duracao, no_corte(ate, faixas_novas)) if ate is not None else duracao, 3)
        if novo_fim <= novo_inicio:
            novo_fim = round(min(duracao, novo_inicio + (m.fim - m.inicio)), 3)
        if (novo_inicio, novo_fim) != (m.inicio, m.fim):
            deslocados += 1
            m.inicio, m.fim = novo_inicio, novo_fim
    return novos, deslocados, saidos


def cues_geradas(
    palavras: list[Palavra], inicio: float, fim: float, faixas: list[tuple[float, float]], nomes: list[str]
) -> list[Cue]:
    """As telas que o preparar gera para o trecho (o mesmo cálculo do `_preparar_um`)."""
    trecho = [p for p in palavras if p.fim > inicio and p.inicio < fim]
    return montar_cues(corrigir_palavras(trecho, nomes), faixas, nomes)


def _tempos(cue: Cue) -> tuple[float, float]:
    return round(cue.inicio, 3), round(cue.fim, 3)


def correcoes_da_legenda(guardadas: list[Cue], geradas: list[Cue]) -> list[tuple[list[str], list[str]]]:
    """As telas corrigidas no painel, na ordem: (texto gerado, texto corrigido).

    O painel só troca o texto de uma tela, nunca o tempo: a tela guardada se acha na gerada de mesmo tempo."""
    por_tempo: dict[tuple[float, float], list[Cue]] = {}
    for cue in geradas:
        por_tempo.setdefault(_tempos(cue), []).append(cue)
    correcoes = []
    for cue in guardadas:
        candidatas = por_tempo.get(_tempos(cue))
        if not candidatas:
            continue
        gerada = candidatas.pop(0)
        if gerada.linhas != cue.linhas:
            correcoes.append((list(gerada.linhas), list(cue.linhas)))
    return correcoes


def _contar_palavras(linhas: list[str]) -> int:
    return sum(len(linha.split()) for linha in linhas)


def reaplicar_correcoes(
    cues: list[Cue], correcoes: list[tuple[list[str], list[str]]]
) -> tuple[list[Cue], list[list[str]]]:
    """Põe cada correção na tela nova com o mesmo texto gerado, em ordem. Devolve (telas, correções sem tela)."""
    novas = copy.deepcopy(cues)
    perdidas: list[list[str]] = []
    posicao = 0
    for gerado, corrigido in correcoes:
        achada = next((i for i in range(posicao, len(novas)) if novas[i].linhas == gerado), None)
        if achada is None:
            perdidas.append(corrigido)
            continue
        cue = novas[achada]
        if _contar_palavras(corrigido) != _contar_palavras(cue.linhas):
            cue.palavras = None  # como no editor da legenda: o tempo por palavra não vale mais
        cue.linhas = list(corrigido)
        posicao = achada + 1
    return novas, perdidas


_SUFIXOS_DE_IMAGEM = re.compile(r"(?:-\d+\.jpg|\.png|-ia-\d+\.jpg)")


def arquivos_da_chave(chave: str, nomes: Iterable[str]) -> list[str]:
    """Arquivos do momento em imagens-sugeridas/: fotos (chave-K.jpg), notícia (chave.png), IA (chave-ia-V.jpg)."""
    return sorted(n for n in nomes if n.startswith(chave) and _SUFIXOS_DE_IMAGEM.fullmatch(n[len(chave):]))


def planejar_renomeacoes(
    chaves: list[tuple[str, str]], movidos: set[str], existentes: set[str]
) -> tuple[list[tuple[str, str]], set[str]]:
    """(arquivo antigo, arquivo novo) de cada momento que mudou de chave, e as chaves antigas que não podem mudar.

    `movidos`: os arquivos que a esteira gravou (os únicos que ela renomeia); `existentes`: tudo o que está na pasta.
    Uma chave fica parada quando algum nome novo já existe, é disputado por dois momentos, ou quando um arquivo dela
    também parece de outra chave: nada é sobrescrito."""
    por_chave = {antiga: arquivos_da_chave(antiga, movidos) for antiga, _ in chaves}
    donos: dict[str, int] = {}
    for arquivos in por_chave.values():
        for nome in arquivos:
            donos[nome] = donos.get(nome, 0) + 1
    pares: list[tuple[str, str]] = []
    paradas: set[str] = set()
    destinos_usados: set[str] = set()
    for antiga, nova in chaves:
        arquivos = por_chave[antiga]
        destinos = [nova + nome[len(antiga):] for nome in arquivos]
        if (
            any(donos[nome] > 1 for nome in arquivos)
            or any(d in existentes or d in destinos_usados for d in destinos)
        ):
            paradas.add(antiga)
            continue
        destinos_usados.update(destinos)
        pares += list(zip(arquivos, destinos))
    return pares, paradas


def deslocar_alertas(alertas: list[str], inicio_antigo: float, inicio: float, fim: float) -> list[str]:
    """Alertas do `planos` ("MM:SS texto", relativos ao início do corte) no início novo; os de fora do trecho saem."""
    saida = []
    for alerta in alertas:
        achado = re.match(r"(\d+):(\d{2}) (.*)", alerta)
        if achado is None:
            saida.append(alerta)
            continue
        minutos, segundos, texto = achado.groups()
        t = inicio_antigo + int(minutos) * 60 + int(segundos)
        if inicio - 1 <= t <= fim:  # o alerta é arredondado para o segundo de baixo
            saida.append(f"{_mmss(t - inicio)} {texto}")
    return saida


def aprovados_com_trecho(conteudo: bytes, numero: int, inicio: float, fim: float) -> str:
    """O aprovados.json com o trecho novo do corte; o resto (origem, outros campos, ordem) fica como estava."""
    dados = json.loads(conteudo.decode("utf-8"))
    for corte in dados["cortes"]:
        if corte.get("numero") == numero:
            corte["inicio"], corte["fim"] = inicio, fim
    return json.dumps(dados, ensure_ascii=False, indent=2) + "\n"


def sobreposicoes(cortes: list[Corte], numero: int, inicio: float, fim: float) -> list[str]:
    avisos = []
    for outro in cortes:
        comum = min(fim, outro.fim) - max(inicio, outro.inicio)
        if outro.numero != numero and comum > 0:
            avisos.append(f"O trecho novo sobrepõe o corte {outro.numero} ({outro.titulo}) em {segundos_texto(comum)}.")
    return avisos


# --- o que muda (para a confirmação) ----------------------------------------------------------------------------


@dataclass
class Previsao:
    resumo: list[str] = field(default_factory=list)
    perdas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _cobertura(trabalho: Path) -> tuple[float, float] | None:
    """O intervalo do episódio que o enquadramento.json cobre; None sem ele."""
    try:
        planos = json.loads((trabalho / "enquadramento.json").read_text("utf-8"))["planos"]
        if not planos:
            return None
        return min(float(p["inicio"]) for p in planos), max(float(p["fim"]) for p in planos)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def aviso_de_enquadramento(trabalho: Path, numero: int, inicio: float, fim: float) -> str | None:
    cobertura = _cobertura(trabalho)
    if cobertura is None:
        return None
    antes, depois = cobertura[0] - inicio, fim - cobertura[1]
    partes = []
    if antes > FOLGA_ENQUADRAMENTO:
        partes.append(f"os {segundos_texto(antes)} novos do começo")
    if depois > FOLGA_ENQUADRAMENTO:
        partes.append(f"os {segundos_texto(depois)} novos do fim")
    if not partes:
        return None
    return (
        f"O enquadramento foi feito para o trecho antigo: {' e '.join(partes)} ficam no centro, sem zoom. "
        f"Para enquadrar, rode no terminal: planos --numero {numero} --forcar."
    )


def _videos_finais(destino: Path) -> list[str]:
    pasta = destino / VIDEO_FINAL
    if not pasta.is_dir():
        return []
    return sorted(a.name for a in pasta.iterdir() if a.is_file() and a.suffix.lower() in EXTENSOES_VIDEO)


def aviso_de_aprovacao(destino: Path) -> tuple[str | None, str | None]:
    """(perda, aviso) sobre o vídeo de video-final/, que a troca do trecho nunca toca."""
    if da_esteira(destino) is not None:
        return (
            "A aprovação deixa de valer: o vídeo de video-final/ continua lá, com o trecho antigo. "
            "Confira o corte novo e aprove de novo."
        ), None
    videos = _videos_finais(destino)
    if videos:
        return None, f"video-final/ tem um vídeo seu ({videos[0]}): ele não muda e continua com o trecho antigo."
    return None, None


def prever(
    pasta_episodio: Path,
    corte: Corte,
    cortes: list[Corte],
    inicio: float,
    fim: float,
    palavras: list[Palavra],
    nomes: list[str] | None,
) -> Previsao:
    """O que a troca vai fazer, sem gravar nada. `nomes` None: glossário ilegível (a legenda não é conferida)."""
    previsao = Previsao(avisos=sobreposicoes(cortes, corte.numero, inicio, fim))
    destino = pasta_do_corte(pasta_episodio, corte)
    trabalho = destino / TRABALHO
    if not (trabalho / NOME_ARQUIVO).is_file():
        previsao.resumo.append("Só o aprovados.json muda: o corte ainda não foi preparado.")
        return previsao
    if (destino / CORTE_MP4).is_file():
        previsao.resumo.append("O corte é preparado e montado de novo (leva cerca de 1 minuto).")
    else:
        previsao.resumo.append("O corte é preparado de novo (ele ainda não tem vídeo montado).")
    previsao.resumo.append("As remoções automáticas de pausas e repetições (edicoes.md) são refeitas.")
    try:
        receita = ler_receita(trabalho)
    except (OSError, ValueError, KeyError, TypeError):
        previsao.avisos.append("montagem.json ilegível: a música, a legenda e as imagens não puderam ser conferidas.")
        return previsao
    faixas_novas, _ = planejar_limpeza(palavras, inicio, fim)  # as pausas com som só mudam os tempos, não o texto
    _prever_musica(receita.musica, previsao)
    _prever_legenda(palavras, corte, receita, faixas_novas, inicio, fim, nomes, previsao)
    _prever_momentos(trabalho, receita.faixas, faixas_novas, inicio, fim, previsao)
    enquadramento = aviso_de_enquadramento(trabalho, corte.numero, inicio, fim)
    if enquadramento:
        previsao.avisos.append(enquadramento)
    perda, aviso = aviso_de_aprovacao(destino)
    previsao.perdas += [perda] if perda else []
    previsao.avisos += [aviso] if aviso else []
    return previsao


def _prever_musica(musica, previsao: Previsao) -> None:
    if musica is None:
        previsao.resumo.append("A música sai do clima do corte, como no preparar.")
    elif Path(musica.arquivo).is_file():
        titulo = musica.titulo or Path(musica.arquivo).name
        previsao.resumo.append(f"A música continua a mesma: {titulo} ({musica.volume_db:g} dB).")
    else:
        previsao.perdas.append(
            f"A música de agora ({musica.titulo or Path(musica.arquivo).name}) não foi encontrada: "
            "o preparar escolhe outra pelo clima."
        )


def _prever_legenda(palavras, corte, receita, faixas_novas, inicio, fim, nomes, previsao: Previsao) -> None:
    if nomes is None:
        previsao.avisos.append("Glossário ilegível: as correções da legenda não puderam ser conferidas.")
        return
    geradas = cues_geradas(palavras, corte.inicio, corte.fim, receita.faixas, nomes)
    correcoes = correcoes_da_legenda(receita.legenda, geradas)
    if not correcoes:
        previsao.resumo.append("A legenda é gerada de novo (não há telas corrigidas no painel).")
        return
    _, perdidas = reaplicar_correcoes(cues_geradas(palavras, inicio, fim, faixas_novas, nomes), correcoes)
    mantidas = len(correcoes) - len(perdidas)
    if mantidas:
        verbo = "volta" if mantidas == 1 else "voltam"
        telas = _plural(mantidas, "tela corrigida", "telas corrigidas")
        previsao.resumo.append(f"{telas} no painel {verbo} no trecho novo.")
    for linhas in perdidas:
        previsao.perdas.append(f"Correção da legenda que sai do corte: “{' / '.join(linhas)}”.")


def _prever_momentos(trabalho, faixas_antigas, faixas_novas, inicio, fim, previsao: Previsao) -> None:
    arquivo = trabalho / PEDIDOS
    if not arquivo.is_file():
        return
    try:
        momentos = pedidos_dos_bytes(arquivo.read_bytes())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        previsao.avisos.append("pedidos.json ilegível: os momentos de imagem não puderam ser conferidos.")
        return
    _, deslocados, saidos = remapear_momentos(momentos, faixas_antigas, faixas_novas, inicio, fim)
    if deslocados:
        verbo = "passa" if deslocados == 1 else "passam"
        previsao.resumo.append(
            f"{_plural(deslocados, 'momento de imagem', 'momentos de imagem')} {verbo} para os tempos novos, "
            "com as imagens prontas."
        )
    for rotulo in saidos:
        previsao.perdas.append(f"Momento de imagem fora do trecho novo (fica descartado): {rotulo}.")


# --- o marcador: guardar antes de mudar, desfazer se der errado -------------------------------------------------


def _gravar_bytes(caminho: Path, conteudo: bytes) -> None:
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        temporario.write_bytes(conteudo)
        os.replace(temporario, caminho)
    finally:
        temporario.unlink(missing_ok=True)


class _Guarda:
    """Guarda cada arquivo antes da primeira mudança e devolve tudo se a troca não termina.

    O marcador em disco tem o necessário para desfazer depois de uma queda: o conteúdo de antes de cada arquivo
    (None = não existia), as renomeações feitas, se o corte.mp4 foi posto de lado e a entrada do uso.json."""

    def __init__(self, pasta_corte: Path, base: Path | None, substituir, dormir, dados: dict | None = None) -> None:
        self.pasta_corte = Path(pasta_corte)
        self.episodio = self.pasta_corte.parent
        self.trabalho = self.pasta_corte / TRABALHO
        self.marcador = garantir_escrita(self.trabalho / MARCADOR, base_extra=base)
        self.base, self.substituir, self.dormir = base, substituir, dormir
        self.dados = dados or {"fase": "aplicando", "arquivos": {}, "renomeados": [], "video": False, "uso": None}

    def _gravar(self) -> None:
        gravar_atomico(self.marcador, json.dumps(self.dados, ensure_ascii=False), newline="\n")

    def _relativo(self, caminho: Path) -> str:
        return Path(caminho).resolve().relative_to(self.episodio.resolve()).as_posix()

    def _caminho(self, relativo: str) -> Path:
        alvo = garantir_escrita(self.episodio / relativo, base_extra=self.base)
        if not alvo.is_relative_to(self.episodio.resolve()):  # marcador adulterado: nada fora do episódio
            raise EscritaProibida(f"fora do episódio: {relativo}")
        return alvo

    def comecar(self) -> None:
        self._gravar()

    def guardar(self, *caminhos: Path) -> None:
        novos = False
        for caminho in caminhos:
            garantir_escrita(caminho, base_extra=self.base)
            relativo = self._relativo(caminho)
            if relativo in self.dados["arquivos"]:
                continue
            conteudo = Path(caminho).read_bytes() if Path(caminho).is_file() else None
            guardado = base64.b64encode(conteudo).decode("ascii") if conteudo is not None else None
            self.dados["arquivos"][relativo] = guardado
            novos = True
        if novos:
            self._gravar()

    def guardar_uso(self, pasta_musicas: Path, chave: str) -> bool:
        """Guarda a entrada do corte no uso.json (o preparar troca a música e a registra). False se não pode gravar."""
        arquivo = Path(pasta_musicas) / "uso.json"
        try:
            garantir_escrita(arquivo, base_extra=self.base)
            entrada = ler_uso(Path(pasta_musicas)).get(chave)
        except (EscritaProibida, OSError, ValueError, AttributeError):
            return False
        self.dados["uso"] = {
            "pasta": str(pasta_musicas), "chave": chave, "entrada": entrada, "existia": arquivo.exists(),
        }
        self._gravar()
        return True

    def devolver_uso(self) -> None:
        """A entrada do corte no uso.json volta a ser a de antes (as outras entradas não mudam)."""
        guardado = self.dados.get("uso")
        if not guardado:
            return
        pasta = Path(guardado["pasta"])
        garantir_escrita(pasta / "uso.json", base_extra=self.base)
        uso = ler_uso(pasta)
        chave, entrada = guardado["chave"], guardado["entrada"]
        if uso.get(chave) == entrada:
            return
        if entrada is None:
            uso.pop(chave, None)
        else:
            uso[chave] = entrada
        if not uso and not guardado["existia"]:
            (pasta / "uso.json").unlink(missing_ok=True)
        else:
            gravar_uso(pasta, uso)

    def por_de_lado_o_video(self) -> bool:
        """Tira o corte.mp4 do lugar (para voltar se a montagem falhar). False se o vídeo está aberto num player."""
        video = garantir_escrita(self.pasta_corte / CORTE_MP4, base_extra=self.base)
        guardado = garantir_escrita(self.trabalho / VIDEO_GUARDADO, base_extra=self.base)
        self.dados["video"] = True
        self._gravar()
        if _substituir_com_espera(video, guardado, self.substituir, self.dormir):
            return True
        self.dados["video"] = False
        self._gravar()
        return False

    def renomear(self, pares: list[tuple[Path, Path]]) -> None:
        if not pares:
            return
        for origem, destino in pares:
            garantir_escrita(origem, base_extra=self.base)
            garantir_escrita(destino, base_extra=self.base)
        self.dados["renomeados"] += [[self._relativo(a), self._relativo(b)] for a, b in pares]
        self._gravar()  # antes de mexer: uma queda no meio sabe o que desfazer
        for origem, destino in pares:
            os.replace(origem, destino)

    def desfazer(self) -> None:
        """Volta tudo ao que era antes. Se o corte.mp4 não pode voltar (aberto num player), o marcador fica para a
        próxima abertura do painel e levanta PermissionError."""
        for origem, destino in reversed(self.dados["renomeados"]):
            de, para = self._caminho(destino), self._caminho(origem)
            if de.exists() and not para.exists():
                os.replace(de, para)
        for relativo, conteudo in self.dados["arquivos"].items():
            alvo = self._caminho(relativo)
            if conteudo is None:
                alvo.unlink(missing_ok=True)
            else:
                _gravar_bytes(alvo, base64.b64decode(conteudo))
        self.devolver_uso()
        guardado = self.trabalho / VIDEO_GUARDADO
        if self.dados["video"] and guardado.exists():
            if not _substituir_com_espera(guardado, self.pasta_corte / CORTE_MP4, self.substituir, self.dormir):
                raise PermissionError(f"não consegui devolver o corte.mp4: {VIDEO_ABERTO}")
        self.marcador.unlink(missing_ok=True)

    def concluir(self) -> None:
        self.dados["fase"] = "pronto"
        self._gravar()  # daqui em diante uma queda não desfaz mais: só termina a limpeza
        self.limpar()

    def limpar(self) -> None:
        try:
            (self.trabalho / VIDEO_GUARDADO).unlink(missing_ok=True)
        except OSError:
            pass
        self.marcador.unlink(missing_ok=True)


def _resolver_marcador(pasta_corte: Path, base: Path | None, substituir, dormir) -> bool:
    """Trata um marcador que ficou de uma troca anterior: desfaz (ou só limpa, se ela tinha terminado).

    True se desfez. Levanta se não conseguiu (o marcador fica para a próxima tentativa)."""
    marcador = Path(pasta_corte) / TRABALHO / MARCADOR
    if not marcador.exists():
        return False
    dados = json.loads(marcador.read_text("utf-8"))
    guarda = _Guarda(pasta_corte, base, substituir, dormir, dados)
    if dados.get("fase") == "pronto":
        guarda.limpar()
        return False
    guarda.desfazer()
    return True


def recuperar_trechos_interrompidos(
    cortes: Path,
    substituir: Callable[[Path, Path], None] = os.replace,
    dormir: Callable[[float], None] = time.sleep,
) -> list[str]:
    """Desfaz as trocas de trecho que o painel deixou pela metade (queda, Ctrl+C). Devolve "<episódio>/<corte>".

    Uma troca que já tinha terminado (fase "pronto") só tem a limpeza concluída."""
    recuperados: list[str] = []
    for marcador in sorted(Path(cortes).glob(f"*/*/{TRABALHO}/{MARCADOR}")):
        pasta_corte = marcador.parent.parent
        nome = f"{pasta_corte.parent.name}/{pasta_corte.name}"
        try:
            if _resolver_marcador(pasta_corte, cortes, substituir, dormir):
                recuperados.append(nome)
        except Exception as erro:
            print(f"Não consegui desfazer a troca de trecho interrompida em {nome}: {erro}", file=sys.stderr)
    return recuperados


# --- a troca --------------------------------------------------------------------------------------------------


class _Falhou(Exception):
    """A troca não terminou: a mensagem vai para a tela, depois de tudo voltar ao que era."""


def _nada(_texto: str) -> None:
    pass


def copiar_aprovados(
    pasta: Path, conteudo: bytes, agora: Callable[[], datetime], base: Path | None, guarda: "_Guarda | None" = None
) -> Path:
    """Cópia do aprovados.json de antes em aprovados-anteriores/aprovados-AAAAMMDD-HHMMSS.json (nunca sobrescreve).

    Com `guarda`, a cópia some se a troca for desfeita (o aprovados.json volta a ser ela)."""
    pasta_copias = Path(pasta) / PASTA_COPIAS
    carimbo = agora().strftime("%Y%m%d-%H%M%S")
    destino = pasta_copias / f"aprovados-{carimbo}.json"
    numero = 2
    while destino.exists():
        destino = pasta_copias / f"aprovados-{carimbo}-{numero}.json"
        numero += 1
    garantir_escrita(destino, base_extra=base)
    if guarda is not None:
        guarda.guardar(destino)
    pasta_copias.mkdir(exist_ok=True)
    _gravar_bytes(destino, conteudo)
    return destino


def _ler_contexto(pasta: Path, numero: int) -> tuple[bytes, Corte, list[Palavra], float]:
    conteudo = (pasta / "aprovados.json").read_bytes()
    corte = next((c for c in ler_aprovados(pasta) if c.numero == numero), None)
    if corte is None:
        raise _Falhou(f"corte {numero} não encontrado")
    duracao = float(json.loads((pasta / "episodio.json").read_text("utf-8"))["duracao"])
    return conteudo, corte, ler_palavras(pasta), duracao


def trocar_trecho(
    pasta_episodio: Path,
    numero: int,
    inicio: float,
    fim: float,
    versao: str,
    preparar: Preparar,
    montar: Montar,
    nomes: Callable[[], list[str]],
    base: Path | None = None,
    pasta_musicas: Path = MUSICAS,
    trava: AbstractContextManager | None = None,
    progresso: Callable[[str], None] = _nada,
    agora: Callable[[], datetime] = datetime.now,
    substituir: Callable[[Path, Path], None] = os.replace,
    dormir: Callable[[float], None] = time.sleep,
) -> Resultado:
    """Grava o trecho novo (já alinhado às palavras) e refaz o corte. `versao`: a do aprovados.json que o dono viu.

    `preparar(pasta, numero, nomes)` e `montar(pasta, numero)` devolvem o texto do resultado ("ok…" ou "erro: …")."""
    pasta = Path(pasta_episodio)
    pasta_corte = _corte_pronto_para_montar(pasta, numero, base, substituir, dormir)  # desfaz troca de música caída
    if isinstance(pasta_corte, Resultado):
        return pasta_corte
    try:
        _resolver_marcador(pasta_corte, base, substituir, dormir)
        conteudo, corte, palavras, duracao = _ler_contexto(pasta, numero)
    except _Falhou as falha:
        return Resultado("erro", str(falha), [], None)
    except Exception as erro:
        return Resultado("erro", resumir_erro(f"não consegui ler o corte: {erro}"), [], None)
    if versao_dos_bytes(conteudo) != versao:
        return Resultado("erro", APROVADOS_MUDOU, [], None)
    novo = replace(corte, inicio=inicio, fim=fim)
    problemas = validar_trecho(palavras, novo, duracao)
    if problemas:
        return Resultado("erro", "; ".join(problemas), [], None)

    trabalho = pasta_corte / TRABALHO
    feito = f"Trecho novo: {tempo_texto(inicio)} a {tempo_texto(fim)} ({segundos_texto(fim - inicio)})."
    if not (trabalho / NOME_ARQUIVO).is_file():
        aprovados = garantir_escrita(pasta / "aprovados.json", base_extra=base)
        copiar_aprovados(pasta, conteudo, agora, base)
        gravar_atomico(aprovados, aprovados_com_trecho(conteudo, numero, inicio, fim), newline="\n")
        return Resultado("pronto", f"{feito} O corte ainda não foi preparado: só o aprovados.json mudou.", [], None)
    try:
        lista_de_nomes = nomes()
    except (OSError, UnicodeDecodeError):
        return Resultado("erro", "Não consegui ler o glossário (Contexto/glossario.md): nada mudou.", [], None)
    try:
        receita_antiga = ler_receita(trabalho)
    except (OSError, ValueError, KeyError, TypeError) as erro:
        return Resultado("erro", resumir_erro(f"montagem.json ilegível: {erro}"), [], None)

    troca = _Troca(
        pasta, corte, novo, pasta_corte, receita_antiga, palavras, lista_de_nomes, base, pasta_musicas, trava
    )
    guarda = _Guarda(pasta_corte, base, substituir, dormir)
    guarda.comecar()
    try:
        avisos = troca.aplicar(guarda, conteudo, preparar, montar, progresso, agora)
    except _Falhou as falha:
        return _desfeito(guarda, str(falha))
    except Exception as erro:
        return _desfeito(guarda, resumir_erro(str(erro) or type(erro).__name__))
    except BaseException:  # o painel está fechando: volta tudo antes de sair
        _desfazer_sem_erro(guarda)
        raise
    guarda.concluir()
    return Resultado("pronto", feito, avisos, None)


def _desfazer_sem_erro(guarda: _Guarda) -> str | None:
    try:
        guarda.desfazer()
    except Exception as erro:
        return f"{erro}. O painel termina de desfazer na próxima vez que abrir"
    return None


def _desfeito(guarda: _Guarda, mensagem: str) -> Resultado:
    problema = _desfazer_sem_erro(guarda)
    mensagem = mensagem.rstrip(". ")
    texto = f"{mensagem}. O corte voltou ao que era." if problema is None else f"{mensagem}; {problema}."
    return Resultado("erro", resumir_erro(texto), [], None)


@dataclass
class _Troca:
    pasta: Path
    corte: Corte
    novo: Corte
    pasta_corte: Path
    receita_antiga: Receita
    palavras: list[Palavra]
    nomes: list[str]
    base: Path | None
    pasta_musicas: Path
    trava: AbstractContextManager | None

    @property
    def trabalho(self) -> Path:
        return self.pasta_corte / TRABALHO

    def aplicar(
        self, guarda: _Guarda, conteudo: bytes, preparar: Preparar, montar: Montar, progresso, agora
    ) -> list[str]:
        """Grava, prepara, devolve o que dá para preservar e monta. Devolve os avisos (os da troca primeiro)."""
        trabalho = self.trabalho
        aprovados = self.pasta / "aprovados.json"
        guarda.guardar(
            aprovados, trabalho / ALERTAS_PLANOS, trabalho / NOME_ARQUIVO, trabalho / "registro.json",
            trabalho / "legenda.srt", trabalho / "edicoes.md",
        )
        guardou_uso = guarda.guardar_uso(self.pasta_musicas, f"{self.pasta.name}/{self.pasta_corte.name}")
        montado = (self.pasta_corte / CORTE_MP4).is_file()
        if montado and not guarda.por_de_lado_o_video():
            raise _Falhou(VIDEO_ABERTO)
        progresso("Preparando o trecho novo…")
        copiar_aprovados(self.pasta, conteudo, agora, self.base, guarda)
        novo = self.novo
        gravar_atomico(aprovados, aprovados_com_trecho(conteudo, novo.numero, novo.inicio, novo.fim), newline="\n")
        self._deslocar_alertas_dos_planos()
        resultado = preparar(self.pasta, novo.numero, self.nomes)
        if not str(resultado).startswith("ok"):
            raise _Falhou(f"o preparar falhou: {resumir_erro(str(resultado))}")
        with self.trava if self.trava is not None else nullcontext():
            proprios, musica_mantida = self._preservar(guarda, guardou_uso)
        da_esteira = _alertas_da_montagem(resultado)
        if montado:
            progresso("Montando o corte…")
            resultado = montar(self.pasta, novo.numero)
            if not str(resultado).startswith("ok"):
                raise _Falhou(f"a montagem falhou: {resumir_erro(str(resultado))}")
            da_esteira = _alertas_da_montagem(resultado)
        if musica_mantida:
            da_esteira = [a for a in da_esteira if not a.startswith("sem música")]
        enquadramento = aviso_de_enquadramento(trabalho, novo.numero, novo.inicio, novo.fim)
        perda, aviso = aviso_de_aprovacao(self.pasta_corte)
        return [a for a in (perda, enquadramento, aviso) if a] + proprios + da_esteira

    def _deslocar_alertas_dos_planos(self) -> None:
        arquivo = self.trabalho / ALERTAS_PLANOS
        try:
            alertas = json.loads(arquivo.read_text("utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(alertas, list):
            return
        novos = deslocar_alertas([str(a) for a in alertas], self.corte.inicio, self.novo.inicio, self.novo.fim)
        gravar_atomico(arquivo, json.dumps(novos, ensure_ascii=False, indent=1), newline="\n")

    def _preservar(self, guarda: _Guarda, guardou_uso: bool) -> tuple[list[str], bool]:
        """Depois do preparar: música, legenda corrigida e momentos de imagem voltam. (avisos, música mantida)."""
        receita = ler_receita(self.trabalho)
        avisos, musica_mantida, musica_nova = self._musica(receita, guarda, guardou_uso)
        receita.legenda, perdidas = reaplicar_correcoes(receita.legenda, self._correcoes())
        avisos += [f"Correção da legenda que saiu do corte: “{' / '.join(linhas)}”." for linhas in perdidas]
        gravar_receita(self.trabalho, receita)
        escrever_srt(receita.legenda, self.trabalho / "legenda.srt")
        avisos += self._momentos(guarda, receita.faixas)
        if musica_nova is not None:
            avisos += self._credito(guarda, musica_nova)
        return avisos, musica_mantida

    def _musica(self, receita: Receita, guarda: _Guarda, guardou_uso: bool) -> tuple[list[str], bool, Musica | None]:
        """(avisos, se a música de antes voltou, a música nova quando o crédito do post precisa mudar)."""
        antiga = self.receita_antiga.musica
        if antiga is None:
            return [], False, None
        titulo = antiga.titulo or Path(antiga.arquivo).name
        if not Path(antiga.arquivo).is_file():
            nova = receita.musica
            if nova is None:
                aviso = f"A música de antes ({titulo}) não foi encontrada e o clima não tem outra: ficou sem música."
                return [aviso], False, None
            entrou = nova.titulo or Path(nova.arquivo).name
            return [f"A música de antes ({titulo}) não foi encontrada: entrou {entrou}."], False, nova
        receita.musica = antiga
        avisos = []
        if guardou_uso:
            guarda.devolver_uso()
        else:
            avisos.append("O uso.json das músicas não pôde voltar à música de antes: ficou a que o preparar escolheu.")
        _tirar_alerta_de_musica(self.trabalho)
        return avisos, True, None

    def _correcoes(self) -> list[tuple[list[str], list[str]]]:
        antiga = self.receita_antiga
        geradas = cues_geradas(self.palavras, self.corte.inicio, self.corte.fim, antiga.faixas, self.nomes)
        return correcoes_da_legenda(antiga.legenda, geradas)

    def _momentos(self, guarda: _Guarda, faixas_novas: list[tuple[float, float]]) -> list[str]:
        arquivo = self.trabalho / PEDIDOS
        if not arquivo.is_file():
            return []
        bruto = arquivo.read_bytes()
        dados = json.loads(bruto.decode("utf-8"))
        momentos = pedidos_dos_bytes(bruto)
        novos, _, saidos = remapear_momentos(
            momentos, self.receita_antiga.faixas, faixas_novas, self.novo.inicio, self.novo.fim
        )
        avisos = [f"Momento de imagem fora do trecho novo, descartado: {rotulo}." for rotulo in saidos]
        imagens = self.pasta_corte / IMAGENS_SUGERIDAS
        existentes = {a.name for a in imagens.iterdir() if a.is_file()} if imagens.is_dir() else set()
        sugeridas = _ler_sugeridas(self.trabalho)
        movidos = {n for n in sugeridas if n in existentes} | {n for n in existentes if re.search(r"-ia-\d+\.jpg$", n)}
        chaves = [
            (chave_momento(antes), chave_momento(depois))
            for antes, depois in zip(momentos, novos)
            if chave_momento(antes) != chave_momento(depois)
        ]
        pares, paradas = planejar_renomeacoes(chaves, movidos, existentes)
        for posicao, antes in enumerate(momentos, 1):
            if chave_momento(antes) in paradas:
                novos[posicao - 1] = replace(antes, descartar=True, motivo=NOME_EM_USO)
                rotulo = rotulo_momento(posicao, antes, painel=True)
                avisos.append(f"Momento de imagem descartado: {rotulo}: {NOME_EM_USO}.")
        nomes_novos = dict(pares)
        guarda.guardar(arquivo, self.trabalho / SUGERIDAS, self.trabalho / CREDITOS, self.trabalho / IA, imagens / GUIA)
        guarda.renomear([(imagens / a, imagens / b) for a, b in pares])
        for m in novos:
            if m.no_video in nomes_novos:
                m.no_video = nomes_novos[m.no_video]
        dados["momentos"] = [asdict(m) for m in novos]
        gravar_atomico(arquivo, json.dumps(dados, ensure_ascii=False, indent=2), newline="\n")
        if nomes_novos:
            self._renomear_nos_registros(nomes_novos, {a: b for a, b in chaves if a not in paradas}, sugeridas)
        if (imagens / GUIA).is_file():
            ajustados = copy.deepcopy(novos)
            ajustar_tempos(ajustados, sum(b - a for a, b in faixas_novas), painel=True)
            escrever_guia(self.pasta_corte, novos, ajustados)
        return avisos

    def _renomear_nos_registros(self, nomes: dict[str, str], chaves: dict[str, str], sugeridas: list[str]) -> None:
        """sugeridas.json, creditos.json e ia.json com os nomes e as chaves novas."""
        trabalho = self.trabalho
        if (trabalho / SUGERIDAS).is_file():
            texto = json.dumps(sorted(nomes.get(n, n) for n in sugeridas), ensure_ascii=False, indent=2) + "\n"
            gravar_atomico(trabalho / SUGERIDAS, texto, newline="\n")
        try:
            creditos = json.loads((trabalho / CREDITOS).read_text("utf-8"))
        except (OSError, ValueError):
            creditos = None
        if isinstance(creditos, dict):
            novos = {nomes.get(nome, nome): c for nome, c in creditos.items()}
            gravar_atomico(trabalho / CREDITOS, json.dumps(novos, ensure_ascii=False, indent=2) + "\n", newline="\n")
        ia = ler_ia(trabalho)
        if ia:
            for item in ia:
                if item.get("momento") in chaves:
                    item["momento"] = chaves[item["momento"]]
                if item.get("arquivo") in nomes:
                    item["arquivo"] = nomes[item["arquivo"]]
            gravar_atomico(trabalho / IA, json.dumps(ia, ensure_ascii=False, indent=2) + "\n", newline="\n")

    def _credito(self, guarda: _Guarda, nova: Musica) -> list[str]:
        post = self.pasta_corte / "post.md"
        if not post.is_file():
            return ["post.md não encontrado: crédito da música não atualizado"]
        guarda.guardar(post)
        try:
            return trocar_credito(post, self.receita_antiga.musica, nova, base=self.base)
        except Exception as erro:
            return [f"crédito da música não atualizado: {erro}"]


def _tirar_alerta_de_musica(trabalho: Path) -> None:
    """A música de antes voltou: o "sem música para o clima" do preparar não vale para este corte."""
    arquivo = trabalho / "registro.json"
    try:
        registro = json.loads(arquivo.read_text("utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(registro, dict) or not any(
        str(a).startswith("sem música") for a in registro.get("alertas") or []
    ):
        return
    for campo in ("alertas", "alertas_preparar"):
        if isinstance(registro.get(campo), list):
            registro[campo] = [a for a in registro[campo] if not str(a).startswith("sem música")]
    if str(registro.get("resultado", "")).startswith("ok"):
        alertas = registro.get("alertas") or []
        registro["resultado"] = f"ok com alertas: {'; '.join(alertas)}" if alertas else "ok"
    gravar_atomico(arquivo, json.dumps(registro, ensure_ascii=False, indent=2))
