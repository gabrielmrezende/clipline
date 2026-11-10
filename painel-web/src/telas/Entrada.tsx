import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErroApi, enviarJson } from "../api";

export function Entrada() {
  const [codigo, setCodigo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const navegar = useNavigate();

  async function entrar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setErro(null);
    try {
      await enviarJson("/api/entrar", "POST", { codigo });
      navegar("/");
    } catch (x) {
      setErro(x instanceof ErroApi ? x.detail : "Não foi possível entrar.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="coluna estreita entrada">
      <h1>Entrar</h1>
      <form onSubmit={entrar}>
        <label htmlFor="codigo">Código de acesso</label>
        <input
          id="codigo"
          type="password"
          autoComplete="off"
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
        />
        <button type="submit" disabled={enviando || !codigo}>
          Entrar
        </button>
        {erro ? (
          <p role="alert" className="mensagem-erro">
            {erro}
          </p>
        ) : null}
      </form>
    </main>
  );
}
