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
LIMITE_LISTA = 50
FECHADO_ANTES = "o painel foi fechado antes de montar este pedido"


class PedidoAtivo(Exception):
    pass


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
            if self._achar_ativo(pasta_episodio.name, numero) is not None:
                raise PedidoAtivo(f"o corte {numero} já tem uma troca de música em andamento")
            pedido = Pedido(
                id=secrets.token_hex(4),
                episodio=pasta_episodio.name,
                numero=numero,
                arquivo=faixa.arquivo,
                volume_db=volume_db,
                estado="na fila",
                criado=self._relogio(),
            )
            self._pedidos[pedido.id] = pedido
            copia = _copiar(pedido)
        self._fila.put((pedido.id, pasta_episodio, numero, faixa, volume_db))
        return copia

    def pedidos(self) -> list[Pedido]:
        with self._trava:
            return [_copiar(p) for p in reversed(list(self._pedidos.values()))][:LIMITE_LISTA]

    def pedido(self, id: str) -> Pedido | None:
        with self._trava:
            achado = self._pedidos.get(id)
            return _copiar(achado) if achado is not None else None

    def ativo(self, episodio: str, numero: int) -> Pedido | None:
        with self._trava:
            achado = self._achar_ativo(episodio, numero)
            return _copiar(achado) if achado is not None else None

    def ultimo_pronto(self, episodio: str, numero: int) -> Pedido | None:
        with self._trava:
            for p in reversed(list(self._pedidos.values())):
                if p.episodio == episodio and p.numero == numero and p.estado == "pronto":
                    return _copiar(p)
        return None

    def montando(self) -> bool:
        with self._trava:
            return any(p.estado == "montando" for p in self._pedidos.values())

    def parar(self, timeout: float = 5) -> None:
        """Espera só a montagem atual (até `timeout`); os pedidos ainda na fila terminam em erro."""
        self._parando.set()
        self._fila.put(None)
        self._trabalhador.join(timeout)

    def _achar_ativo(self, episodio: str, numero: int) -> Pedido | None:
        for p in self._pedidos.values():
            if p.episodio == episodio and p.numero == numero and p.estado in ATIVOS:
                return p
        return None

    def _trabalhar(self) -> None:
        while True:
            item = self._fila.get()
            if item is None:
                return
            id, pasta, numero, faixa, volume_db = item
            if self._parando.is_set():
                self._concluir(id, Resultado("erro", FECHADO_ANTES, [], None))
                continue
            with self._trava:
                self._pedidos[id].estado = "montando"
            resultado = Resultado("erro", "a montagem parou sem resposta", [], None)
            try:
                resultado = self._executar(pasta, numero, faixa, volume_db)
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
                    "titulo": anterior.titulo,
                    "volume_db": anterior.volume_db,
                }
            pedido.terminado = self._relogio()


def _copiar(pedido: Pedido) -> Pedido:
    return replace(pedido, avisos=list(pedido.avisos), anterior=dict(pedido.anterior) if pedido.anterior else None)
