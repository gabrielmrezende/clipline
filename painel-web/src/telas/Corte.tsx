import { Link, useParams } from "react-router-dom";

// Provisório: a tela do corte (players e editor de post) vem na Task 9.
export function Corte() {
  const { ep = "", n = "" } = useParams();
  return (
    <main className="coluna">
      <p>
        <Link to={`/episodios/${encodeURIComponent(ep)}`} className="alvo-inline">
          ← {ep}
        </Link>
      </p>
      <h1>Corte {n}</h1>
    </main>
  );
}
