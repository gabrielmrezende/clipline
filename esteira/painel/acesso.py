import hashlib
import hmac
import secrets
import threading
from collections.abc import Callable
from typing import Protocol

SERVICO = "tudo-e-politica-painel"
ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sem I, L, O, 0 e 1, que se confundem
TAMANHO_CODIGO = 8
ITERACOES = 200_000
DURACAO_SESSAO = 30 * 86400
MAX_ERROS = 5
TRAVA_SEGUNDOS = 60
COOKIE = "painel_sessao"


class Cofre(Protocol):
    def ler(self, campo: str) -> str | None: ...

    def gravar(self, campo: str, valor: str) -> None: ...


class CofreKeyring:
    def _keyring(self):
        import keyring  # importado aqui: os testes não precisam do pacote

        return keyring

    def ler(self, campo: str) -> str | None:
        return self._keyring().get_password(SERVICO, campo)

    def gravar(self, campo: str, valor: str) -> None:
        self._keyring().set_password(SERVICO, campo, valor)


class CodigoErrado(Exception):
    pass


class Travado(Exception):
    def __init__(self, segundos_restantes: int):
        self.segundos_restantes = segundos_restantes
        super().__init__(f"Muitas tentativas. Tente de novo em {segundos_restantes} s.")


def _hash(codigo: str, sal: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", codigo.encode("utf-8"), sal, ITERACOES).hex()


def gerar_codigo(cofre: Cofre) -> str:
    """Gera um código novo e uma chave de sessão nova (derruba as sessões abertas)."""
    codigo = "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO_CODIGO))
    sal = secrets.token_bytes(16)
    cofre.gravar("codigo", f"{sal.hex()}${_hash(codigo, sal)}")
    cofre.gravar("chave_sessao", secrets.token_hex(32))
    return codigo


class Porteiro:
    def __init__(self, cofre: Cofre, relogio: Callable[[], float]):
        self._cofre = cofre
        self._relogio = relogio
        self._erros = 0
        self._travado_ate = 0.0
        self._trava = threading.Lock()

    def _assinar(self, chave: str, expira: str) -> str:
        return hmac.new(chave.encode("utf-8"), expira.encode("utf-8"), hashlib.sha256).hexdigest()

    def _confere(self, codigo: str) -> bool:
        guardado = self._cofre.ler("codigo")
        if not guardado or "$" not in guardado:
            return False
        sal_hex, esperado = guardado.split("$", 1)
        try:
            sal = bytes.fromhex(sal_hex)
        except ValueError:
            return False
        return hmac.compare_digest(_hash(codigo.strip().upper(), sal), esperado)

    def entrar(self, codigo: str) -> str:
        with self._trava:  # serializa: o PBKDF2 solta o GIL e burlaria a contagem
            return self._entrar(codigo)

    def _entrar(self, codigo: str) -> str:
        agora = self._relogio()
        if agora < self._travado_ate:
            raise Travado(int(self._travado_ate - agora) + 1)
        chave = self._cofre.ler("chave_sessao")
        if not chave or not self._confere(codigo):
            self._erros += 1
            if self._erros >= MAX_ERROS:
                self._erros = 0
                self._travado_ate = agora + TRAVA_SEGUNDOS
            raise CodigoErrado()
        self._erros = 0
        expira = str(int(agora) + DURACAO_SESSAO)
        return f"{expira}.{self._assinar(chave, expira)}"

    def sessao_valida(self, cookie: str | None) -> bool:
        chave = self._cofre.ler("chave_sessao")
        if not cookie or not chave or "." not in cookie:
            return False
        expira, assinatura = cookie.split(".", 1)
        if not expira.isdigit():
            return False
        if not hmac.compare_digest(self._assinar(chave, expira), assinatura):
            return False
        return self._relogio() < int(expira)
