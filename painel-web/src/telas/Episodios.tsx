import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErroApi, Resumo, pedir } from "../api";

export function Episodios() {
  const [lista, setLista] = useState<Resumo[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    pedir<Resumo[]>("/api/episodios")
      .then(setLista)
      .catch((x) => setErro(x instanceof ErroApi ? x.detail : "Erro inesperado."));
  }, []);

  return (
    <main className="coluna">
      <p>
        <Link to="/configuracoes" className="alvo-inline">
          Configurações
        </Link>
      </p>
      <h1>Episódios</h1>
      {erro ? (
        <p role="alert" className="mensagem-erro">
          {erro}
        </p>
      ) : null}
      {!lista && !erro ? <p>Carregando…</p> : null}
      {lista && lista.length === 0 ? <p>Nenhum episódio em 2 - Cortes.</p> : null}
      <ul className="cartoes">
        {lista?.map((r) => (
          <li key={r.nome} className="cartao">
            <Link to={`/episodios/${encodeURIComponent(r.nome)}`} className="alvo">
              <h2>{r.nome}</h2>
              <p>
                {r.prontos} de {r.total} cortes prontos
              </p>
              {r.proxima_data ? <p>Próxima publicação: {r.proxima_data}</p> : null}
              {r.aviso ? <p className="aviso">⚠ {r.aviso}</p> : null}
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
