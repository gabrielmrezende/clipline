import json
import queue
import secrets
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path

from esteira.caminhos import garantir_escrita, gravar_atomico
from esteira.musica import Faixa
from esteira.painel.troca_musica import Resultado, resumir_erro

ATIVOS = ("na fila", "montando")
MONTAGEM = ("musica", "montar")  # os dois refazem o corte.mp4: um de cada vez por corte
LIMITE_LISTA = 50
FECHADO_ANTES = "o painel foi fechado antes de montar este pedido"
FECHADO_NO_MEIO = "o painel foi fechado no meio deste pedido"
INTERROMPIDO = "interrompido"
CANCELADO = "cancelado"
ESTADOS = (*ATIVOS, "pronto", "erro", INTERROMPIDO, CANCELADO)
ARQUIVO = "painel-fila.json"  # na pasta de cortes: cada --cortes tem o seu histórico
FORMATO = 1
TENTATIVAS_GRAVAR = 10
ESPERA_GRAVAR = 0.05  # 10 x 0,05 s: o bastante para um antivírus soltar o arquivo
PARA_NO_MEIO = ("ia",)  # param no próximo `progresso`, antes da próxima imagem paga, sem estragar nada
CANCELADO_ANTES = "cancelado antes de começar"
CANCELADO_NO_MEIO = "cancelado no meio: o que já ficou pronto foi mantido"
DESCARTADO = "interrompido e descartado: não vai rodar de novo"
CANCELAMENTO_TARDE = "O cancelamento chegou depois do último passo: o pedido terminou."
JA_COMECOU = "Este pedido já começou e não para no meio. Espere terminar."
JA_TERMINOU = "Este pedido já terminou."


class PedidoAtivo(Exception):
    pass


class NaoCancela(Exception):
    """O pedido não pode ser cancelado agora: já terminou, ou já começou e não para no meio."""


class Interrompido(BaseException):
    """O painel está fechando (ou o dono cancelou): a tarefa para no próximo `progresso`, antes de começar outro
    passo pago.

    Herda de BaseException para atravessar os `except Exception` que isolam um item (um download, por exemplo)."""

    def __init__(self, mensagem: str, estado: str = INTERROMPIDO) -> None:
        super().__init__(mensagem)
        self.estado = estado


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
    cancelando: bool = False

    def como_dict(self) -> dict:
        return asdict(self)


class Fila:
    """Um trabalhador, um pedido de cada vez. Com `arquivo`, o histórico sobrevive a reinícios do painel."""

    def __init__(
        self,
        executar: Callable[[Path, int, Faixa, float], Resultado],
        relogio: Callable[[], float] = time.time,
        arquivo: Path | None = None,
        base: Path | None = None,
    ) -> None:
        self._executar = executar
        self._relogio = relogio
        self._trava = threading.Lock()
        self._pedidos: dict[str, Pedido] = {}
        self._fila: queue.Queue = queue.Queue()
        self._parando = threading.Event()
        self._versao = 0  # sobe a cada mudança; a gravação nunca troca um estado novo por um velho
        self._gravado = 0
        self._trava_arquivo = threading.Lock()
        self._ouvintes: list[Callable[[], None]] = []
        self._trava_ouvintes = threading.Lock()
        self._arquivo = garantir_escrita(Path(arquivo), base_extra=base) if arquivo is not None else None
        if self._arquivo is not None:
            self._carregar()
        self._trabalhador = threading.Thread(target=self._trabalhar, name="fila-de-montagem", daemon=True)
        self._trabalhador.start()

    def pedir(self, pasta_episodio: Path, numero: int, faixa: Faixa, volume_db: float) -> Pedido:
        pasta_episodio = Path(pasta_episodio)
        with self._trava:
            if self._achar_montagem(pasta_episodio.name, numero) is not None:
                raise PedidoAtivo(f"o corte {numero} já está sendo montado")
            pedido = Pedido(
                id=self._novo_id(),
                episodio=pasta_episodio.name,
                numero=numero,
                arquivo=faixa.arquivo,
                volume_db=volume_db,
                estado="na fila",
                criado=self._relogio(),
                cortes=[numero],
            )
            self._pedidos[pedido.id] = pedido
            self._versao += 1
            copia = _copiar(pedido)
        self._fila.put((pedido.id, lambda progresso: self._executar(pasta_episodio, numero, faixa, volume_db)))
        self._mudou()
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
                id=self._novo_id(),
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
            self._versao += 1
            copia = _copiar(pedido)
        self._fila.put((pedido.id, executar))
        self._mudou()
        return copia

    def cancelar(self, id: str) -> Pedido:
        """Na fila: sai sem rodar. Interrompido: descartado (some do "tentar de novo"). Montando: só os tipos de
        PARA_NO_MEIO, que param no próximo `progresso`. KeyError se não existe; NaoCancela nos outros casos."""
        with self._trava:
            pedido = self._pedidos[id]
            if pedido.estado == "na fila":
                pedido.estado, pedido.mensagem, pedido.terminado = CANCELADO, CANCELADO_ANTES, self._relogio()
            elif pedido.estado == INTERROMPIDO:
                pedido.estado, pedido.mensagem = CANCELADO, DESCARTADO
            elif pedido.estado == "montando" and pedido.tipo in PARA_NO_MEIO:
                pedido.cancelando = True
            elif pedido.estado == "montando":
                raise NaoCancela(JA_COMECOU)
            else:
                raise NaoCancela(JA_TERMINOU)
            self._versao += 1
            copia = _copiar(pedido)
        self._mudou()
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

    def ouvir(self, aviso: Callable[[], None]) -> Callable[[], None]:
        """`aviso()` é chamado, de qualquer thread, a cada mudança na fila. Devolve a função que para de avisar."""
        with self._trava_ouvintes:
            self._ouvintes.append(aviso)

        def parar_de_ouvir() -> None:
            with self._trava_ouvintes:
                if aviso in self._ouvintes:
                    self._ouvintes.remove(aviso)

        return parar_de_ouvir

    def acordar(self) -> None:
        """Chama os ouvintes sem mudança na fila (o painel está fechando, por exemplo)."""
        self._avisar()

    def parar(self, timeout: float = 5) -> None:
        """Espera só a montagem atual (até `timeout`); os pedidos ainda na fila terminam interrompidos."""
        self._parando.set()
        self._fila.put(None)
        self._avisar()
        self._trabalhador.join(timeout)

    def _novo_id(self) -> str:
        while True:
            id = secrets.token_hex(4)
            if id not in self._pedidos:  # o histórico gravado também ocupa ids
                return id

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
                self._concluir(id, Resultado(INTERROMPIDO, FECHADO_ANTES, [], None))
                continue
            with self._trava:
                if self._pedidos[id].estado != "na fila":  # cancelado enquanto esperava
                    continue
                self._pedidos[id].estado = "montando"
                self._versao += 1
            self._mudou()

            def progresso(texto: str, id: str = id) -> None:
                if self._parando.is_set():
                    raise Interrompido(FECHADO_NO_MEIO)
                with self._trava:
                    if self._pedidos[id].cancelando:
                        raise Interrompido(CANCELADO_NO_MEIO, CANCELADO)
                    self._pedidos[id].progresso = texto
                    self._versao += 1
                self._mudou(gravar=False)  # o texto do andamento não precisa ir para o disco

            resultado = Resultado("erro", "a montagem parou sem resposta", [], None)
            try:
                resultado = executar(progresso)
            except Interrompido as parada:
                resultado = Resultado(parada.estado, str(parada), [], None)
            except Exception as erro:
                resultado = Resultado("erro", resumir_erro(str(erro) or type(erro).__name__), [], None)
            except BaseException as erro:  # SystemExit e afins: o pedido não fica "montando" e a fila segue
                resultado = Resultado("erro", f"a montagem parou ({type(erro).__name__})", [], None)
            finally:
                self._concluir(id, resultado)

    def _concluir(self, id: str, resultado: Resultado) -> None:
        anterior = resultado.anterior
        estado = resultado.estado if resultado.estado in ("pronto", INTERROMPIDO, CANCELADO) else "erro"
        with self._trava:
            pedido = self._pedidos[id]
            if pedido.estado not in ATIVOS:  # já cancelado: fica como está
                return
            pedido.estado = estado
            pedido.mensagem = resultado.mensagem
            pedido.avisos = list(resultado.avisos)
            if pedido.cancelando and estado == "pronto":
                pedido.avisos.append(CANCELAMENTO_TARDE)
            pedido.cancelando = False
            if anterior is not None:
                pedido.anterior = {
                    "arquivo": Path(anterior.arquivo).name,
                    "titulo": anterior.titulo or Path(anterior.arquivo).name,
                    "volume_db": anterior.volume_db,
                }
            pedido.terminado = self._relogio()
            self._versao += 1
        self._mudou()

    # --- persistência e avisos -------------------------------------------------------------------------------

    def _mudou(self, gravar: bool = True) -> None:
        if gravar:
            self._gravar()
        self._avisar()

    def _avisar(self) -> None:
        with self._trava_ouvintes:
            ouvintes = list(self._ouvintes)
        for aviso in ouvintes:
            try:
                aviso()
            except Exception:  # uma conexão que caiu não derruba a fila
                pass

    def _gravar(self) -> None:
        """Grava os 50 mais recentes (e qualquer ativo mais antigo). Se falhar, só avisa: a fila em memória segue."""
        if self._arquivo is None:
            return
        with self._trava:
            versao = self._versao
            todos = list(self._pedidos.values())
            lista = [p.como_dict() for p in todos[:-LIMITE_LISTA] if p.estado in ATIVOS]
            lista += [p.como_dict() for p in todos[-LIMITE_LISTA:]]
        texto = json.dumps({"formato": FORMATO, "pedidos": lista}, ensure_ascii=False, indent=1)
        with self._trava_arquivo:
            if versao <= self._gravado:  # outra thread já gravou um estado mais novo
                return
            for tentativa in range(TENTATIVAS_GRAVAR):
                try:
                    gravar_atomico(self._arquivo, texto + "\n")
                    break
                except PermissionError:  # no Windows, o arquivo aberto por outro programa (antivírus) não é trocado
                    if tentativa == TENTATIVAS_GRAVAR - 1:
                        self._avisar_falha("arquivo em uso por outro programa")
                        return
                    time.sleep(ESPERA_GRAVAR)
                except OSError as erro:  # disco cheio, pasta sem permissão…
                    self._avisar_falha(erro)
                    return
            self._gravado = versao

    def _avisar_falha(self, motivo: object) -> None:
        print(f"Não consegui gravar a fila do painel ({self._arquivo.name}): {motivo}", file=sys.stderr)

    def _carregar(self) -> None:
        """Lê o histórico. O que estava na fila ou montando volta interrompido e não roda sozinho: alguns pedidos
        gastam dinheiro, então só o dono, pelo painel, pede de novo."""
        try:
            dados = json.loads(self._arquivo.read_text("utf-8"))
            itens = dados["pedidos"]
            if not isinstance(itens, list):
                raise TypeError("pedidos não é uma lista")
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError) as erro:  # inclui JSON e UTF-8 inválidos
            print(f"Fila do painel ilegível ({self._arquivo.name}: {erro}): começando vazia.", file=sys.stderr)
            return
        agora = self._relogio()
        recuperou = False
        for item in itens:
            pedido = _pedido_do_dict(item)
            if pedido is None or pedido.id in self._pedidos:
                continue
            if pedido.estado in ATIVOS:
                pedido.mensagem = FECHADO_ANTES if pedido.estado == "na fila" else FECHADO_NO_MEIO
                pedido.estado, pedido.terminado, pedido.cancelando = INTERROMPIDO, agora, False
                recuperou = True
            self._pedidos[pedido.id] = pedido
        if recuperou:
            self._versao += 1
            self._gravar()


_TIPOS: dict[str, type | tuple[type, ...]] = {
    "id": str, "episodio": str, "numero": int, "arquivo": str, "volume_db": (int, float), "estado": str,
    "criado": (int, float), "mensagem": str, "avisos": list, "anterior": (dict, type(None)),
    "terminado": (int, float, type(None)), "tipo": str, "cortes": list, "progresso": str, "cancelando": bool,
}
_CAMPOS = {f.name for f in fields(Pedido)}


def _pedido_do_dict(item: object) -> Pedido | None:
    """Um pedido gravado; None se falta campo, o tipo não confere ou o estado é desconhecido (entrada ignorada)."""
    if not isinstance(item, dict):
        return None
    dados = {k: v for k, v in item.items() if k in _CAMPOS}
    if any(not isinstance(v, _TIPOS[k]) for k, v in dados.items()):
        return None
    try:
        pedido = Pedido(**dados)
    except TypeError:  # falta um campo obrigatório
        return None
    if not pedido.id or pedido.estado not in ESTADOS:
        return None
    if not all(isinstance(n, int) for n in pedido.cortes) or not all(isinstance(a, str) for a in pedido.avisos):
        return None
    return pedido


def _copiar(pedido: Pedido) -> Pedido:
    return replace(pedido, avisos=list(pedido.avisos), cortes=list(pedido.cortes), anterior=dict(pedido.anterior) if pedido.anterior else None)
