"""O registro do `publicar rodar` em logs/publicar.log, com rotação por tamanho.

A tarefa instalada antes desta versão ainda manda a saída para o mesmo arquivo pelo cmd (`>> logs\\publicar.log`).
Nesse caso o arquivo fica aberto pelo cmd a execução inteira: o registro escreve só pela saída (um escritor por
arquivo) e avisa para reinstalar a tarefa. Se a rotação falhar por outro motivo (no Windows, um arquivo aberto
por outro programa não pode ser renomeado), o registro segue no arquivo atual e a publicação não para.
"""
import io
import logging
import os
import sys
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from esteira.caminhos import AUTOMACAO

LOG = AUTOMACAO / "logs" / "publicar.log"
TAMANHO_MAXIMO = 1_000_000  # bytes por arquivo
COPIAS = 5  # publicar.log.1 a publicar.log.5
FORMATO = "%(asctime)s %(message)s"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"
NOME = "esteira.publicar.rodar"
TAREFA_ANTIGA = (
    "aviso: a tarefa agendada é antiga e grava este log pelo cmd (>>), sem rotação; "
    "reinstale com publicar instalar-tarefa --confirmar"
)


class RotacaoTolerante(RotatingFileHandler):
    """Gira o log por tamanho; se não conseguir renomear o arquivo, segue nele até o fim desta execução."""

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError:
            self.maxBytes = 0  # não tenta de novo a cada linha
            if self.stream is None:
                self.stream = self._open()


def saida_e_o_log(log: Path, saida) -> bool:
    """A saída deste processo já vai para o próprio log (a tarefa antiga, com `>>`)?"""
    try:
        return os.path.samestat(os.fstat(saida.fileno()), os.stat(log))
    except (OSError, ValueError, AttributeError, io.UnsupportedOperation):
        return False


@contextmanager
def registro(log: Path | None = None, saida=None):
    """Devolve (logger, tarefa_antiga). Fecha e solta o arquivo na saída do bloco."""
    log = Path(log or LOG)
    saida = saida if saida is not None else sys.stdout
    antiga = saida_e_o_log(log, saida)
    if antiga:
        manipulador: logging.Handler = logging.StreamHandler(saida)
    else:
        log.parent.mkdir(parents=True, exist_ok=True)
        manipulador = RotacaoTolerante(log, maxBytes=TAMANHO_MAXIMO, backupCount=COPIAS, encoding="utf-8")
    manipulador.setFormatter(logging.Formatter(FORMATO, FORMATO_DATA))
    logger = logging.getLogger(NOME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(manipulador)
    try:
        yield logger, antiga
    finally:
        logger.removeHandler(manipulador)
        manipulador.close()
