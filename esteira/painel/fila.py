import queue
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from esteira.musica import Faixa
from esteira.painel.troca_musica import Resultado, resumir_erro

ATIVOS = ("na fila", "montando")
MONTAGEM = ("musica", "montar")  # os dois refazem o corte.mp4: um de cada vez por corte
LIMITE_LISTA = 50
FECHADO_ANTES = "o painel foi fechado antes de montar este pedido"
FECHADO_NO_MEIO = "o painel foi fechado no meio deste pedido"


class PedidoAtivo(Exception):
    pass


class Interrompido(BaseException):
    """O painel está fechando: a tarefa para no próximo `progresso`, antes de começar outro passo pago.

    Herda de BaseException para atravessar os `except Exception` que isolam um item (um download, por exemplo)."""


@dataclass
class Pedido:
    id: str
    episodio: str
    numero: int
    arquivo: str
    volume_db: float
    estado: str
    criado: float
    mensagem: str = ""
    avisos: list[str] = field(default_factory=list)
    anterior: dict | None = None
    terminado: float | None = None
    tipo: str = "musica"
    cortes: list[int] = field(default_factory=list)
    progresso: str = ""

    def como_dict(self) -> dict:
        return asdict(self)


class Fila:
    def __init__(
        self,
        executar: Callable[[Path, int, Faixa, float], Resultado],
        relogio: Callable[[], float] = time.time,
    ) -> None:
        self._executar = executar
        self._relogio = relogio
        self._trava = threading.Lock()
        self._pedidos: dict[str, Pedido] = {}
        self._fila: queue.Queue = queue.Queue()
        self._parando = threading.Event()
        self._trabalhador = threading.Thread(target=self._trabalhar, name="fila-de-montagem", daemon=True)
        self._trabalhador.start()

    def pedir(self, pasta_episodio: Path, numero: int, faixa: Faixa, volume_db: float) -> Pedido:
        pasta_episodio = Path(pasta_episodio)
        with self._trava:
            if self._achar_montagem(pasta_episodio.name, numero) is not None:
                raise PedidoAtivo(f"o corte {numero} já está sendo montado")
            pedido = Pedido(
                id=secrets.token_hex(4),
                episodio=pasta_episodio.name,
                numero=numero,
                arquivo=faixa.arquivo,
                volume_db=volume_db,
                estado="na fila",
                criado=self._relogio(),
                cortes=[numero],
            )
            self._pedidos[pedido.id] = pedido
            copia = _copiar(pedido)
        self._fila.put((pedido.id, lambda progresso: self._executar(pasta_episodio, numero, faixa, volume_db)))
        return copia

    def pedir_tarefa(
        self,
        tipo: str,
        pasta_episodio: Path,
        cortes: list[int],
        executar: Callable[[Callable[[str], None]], Resultado],
    ) -> Pedido:
        """Pedido genérico (fotos, IA…) na mesma fila; `executar` recebe a função que atualiza o progresso."""
        pasta_episodio = Path(pasta_episodio)
        cortes = list(cortes)
        if not cortes:
            raise ValueError("o pedido precisa de ao menos um corte")
        with self._trava:
            for n in cortes:
                if tipo in MONTAGEM and self._achar_montagem(pasta_episodio.name, n) is not None:
                    raise PedidoAtivo(f"o corte {n} já está sendo montado")
                if self._achar_ativo(pasta_episodio.name, n, tipo) is not None:
                    raise PedidoAtivo(f"o corte {n} já tem um pedido de {tipo} em andamento")
            pedido = Pedido(
                id=secrets.token_hex(4),
                episodio=pasta_episodio.name,
                numero=cortes[0] if len(cortes) == 1 else 0,
                arquivo="",
                volume_db=0.0,
                estado="na fila",
                criado=self._relogio(),
                tipo=tipo,
                cortes=cortes,
            )
            self._pedidos[pedido.id] = pedido
            copia = _copiar(pedido)
        self._fila.put((pedido.id, executar))
        return copia

    def pedidos(self) -> list[Pedido]:
        with self._trava:
            return [_copiar(p) for p in reversed(list(self._pedidos.values()))][:LIMITE_LISTA]

    def pedido(self, id: str) -> Pedido | None:
        with self._trava:
            achado = self._pedidos.get(id)
            return _copiar(achado) if achado is not None else None

    def ativo(self, episodio: str, numero: int, tipo: str = "musica") -> Pedido | None:
        with self._trava:
            achado = self._achar_ativo(episodio, numero, tipo)
            return _copiar(achado) if achado is not None else None

    def ultimo_pronto(self, episodio: str, numero: int, tipo: str = "musica") -> Pedido | None:
        with self._trava:
            for p in reversed(list(self._pedidos.values())):
                if p.episodio == episodio and p.numero == numero and p.tipo == tipo and p.estado == "pronto":
                    return _copiar(p)
        return None

    def montando_corte(self, episodio: str, numero: int) -> bool:
        """O corte tem uma troca de música ou uma montagem na fila ou rodando."""
        with self._trava:
            return self._achar_montagem(episodio, numero) is not None

    def montando(self) -> bool:
        with self._trava:
            return any(p.estado == "montando" for p in self._pedidos.values())

    def parar(self, timeout: float = 5) -> None:
        """Espera só a montagem atual (até `timeout`); os pedidos ainda na fila terminam em erro."""
        self._parando.set()
        self._fila.put(None)
        self._trabalhador.join(timeout)

    def _achar_montagem(self, episodio: str, numero: int) -> Pedido | None:
        for p in self._pedidos.values():
            if p.episodio == episodio and p.tipo in MONTAGEM and numero in p.cortes and p.estado in ATIVOS:
                return p
        return None

    def _achar_ativo(self, episodio: str, numero: int, tipo: str = "musica") -> Pedido | None:
        for p in self._pedidos.values():
            if p.episodio == episodio and p.tipo == tipo and numero in p.cortes and p.estado in ATIVOS:
                return p
        return None

    def _trabalhar(self) -> None:
        while True:
            item = self._fila.get()
            if item is None:
                return
            id, executar = item
            if self._parando.is_set():
                self._concluir(id, Resultado("erro", FECHADO_ANTES, [], None))
                continue
            with self._trava:
                self._pedidos[id].estado = "montando"

            def progresso(texto: str, id: str = id) -> None:
                if self._parando.is_set():
                    raise Interrompido(FECHADO_NO_MEIO)
                with self._trava:
                    self._pedidos[id].progresso = texto

            resultado = Resultado("erro", "a montagem parou sem resposta", [], None)
            try:
                resultado = executar(progresso)
            except Interrompido:
                resultado = Resultado("erro", FECHADO_NO_MEIO, [], None)
            except Exception as erro:
                resultado = Resultado("erro", resumir_erro(str(erro) or type(erro).__name__), [], None)
            except BaseException as erro:  # SystemExit e afins: o pedido não fica "montando" e a fila segue
                resultado = Resultado("erro", f"a montagem parou ({type(erro).__name__})", [], None)
            finally:
                self._concluir(id, resultado)

    def _concluir(self, id: str, resultado: Resultado) -> None:
        anterior = resultado.anterior
        with self._trava:
            pedido = self._pedidos[id]
            pedido.estado = "pronto" if resultado.estado == "pronto" else "erro"
            pedido.mensagem = resultado.mensagem
            pedido.avisos = list(resultado.avisos)
            if anterior is not None:
                pedido.anterior = {
                    "arquivo": Path(anterior.arquivo).name,
                    "titulo": anterior.titulo or Path(anterior.arquivo).name,
                    "volume_db": anterior.volume_db,
                }
            pedido.terminado = self._relogio()


def _copiar(pedido: Pedido) -> Pedido:
    return replace(pedido, avisos=list(pedido.avisos), cortes=list(pedido.cortes), anterior=dict(pedido.anterior) if pedido.anterior else None)
