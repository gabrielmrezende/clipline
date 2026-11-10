import { CSSProperties, useEffect, useState } from "react";
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
      <h1>Episódios</h1>
      {erro ? (
        <p role="alert" className="mensagem-erro">
          {erro}
        </p>
      ) : null}
      {!lista && !erro ? <p>Carregando…</p> : null}
      {lista && lista.length === 0 ? <p>Nenhum episódio em 2 - Cortes.</p> : null}
      <ul className="episodios">
        {lista?.map((r) => (
          <li key={r.nome}>
            <Link to={`/episodios/${encodeURIComponent(r.nome)}`} className="episodio-link">
              <h2>{r.nome}</h2>
              <span className="episodio-conta">
                {r.prontos} de {r.total} cortes prontos
              </span>
              <span
                className="progresso"
                aria-hidden="true"
                style={{ "--feito": r.total > 0 ? r.prontos / r.total : 0 } as CSSProperties}
              />
              {r.proxima_data || r.aviso ? (
                <span className="episodio-extra">
                  {r.proxima_data ? <span>Próxima publicação: {r.proxima_data}</span> : null}
                  {r.aviso ? <span className="aviso">⚠ {r.aviso}</span> : null}
                </span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
