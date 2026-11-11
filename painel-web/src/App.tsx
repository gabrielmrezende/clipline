import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { ErroDaTela } from "./componentes/ErroDaTela";
import { MarcaClipline } from "./componentes/MarcaClipline";
import { Configuracoes } from "./telas/Configuracoes";
import { Corte } from "./telas/Corte";
import { Entrada } from "./telas/Entrada";
import { Episodio } from "./telas/Episodio";
import { Episodios } from "./telas/Episodios";

export function App() {
  const { pathname } = useLocation();
  const naEntrada = pathname === "/entrar";
  // A tela do corte usa a largura toda (monitor + folha); o topo acompanha.
  const largo = /\/cortes\/[^/]+$/.test(pathname);
  return (
    <>
      <header className={largo ? "topo largo" : "topo"}>
        <div className="topo-dentro">
          <Link to="/" className="marca-link" title="Episódios">
            <MarcaClipline />
          </Link>
          {naEntrada ? null : (
            <NavLink to="/configuracoes" className="topo-link">
              Configurações
            </NavLink>
          )}
        </div>
      </header>
      <ErroDaTela key={pathname}>
        <Rotas />
      </ErroDaTela>
    </>
  );
}

function Rotas() {
  return (
    <Routes>
      <Route path="/entrar" element={<Entrada />} />
      <Route path="/" element={<Episodios />} />
      <Route path="/configuracoes" element={<Configuracoes />} />
      <Route path="/episodios/:ep" element={<Episodio />} />
      <Route path="/episodios/:ep/cortes/:n" element={<Corte />} />
      <Route
        path="*"
        element={
          <main className="coluna">
            <h1>Página não encontrada</h1>
            <a href="/">Voltar aos episódios</a>
          </main>
        }
      />
    </Routes>
  );
}
