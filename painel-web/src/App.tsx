import { Suspense, lazy } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { AlternarTema } from "./componentes/AlternarTema";
import { ErroDaTela } from "./componentes/ErroDaTela";
import { EsqueletoCorte, EsqueletoTela } from "./componentes/Esqueleto";
import { MarcaClipline } from "./componentes/MarcaClipline";

// Cada tela vem num pedaço próprio, baixado na primeira visita: a lista de episódios não carrega o corte.
const Configuracoes = lazy(() => import("./telas/Configuracoes").then((m) => ({ default: m.Configuracoes })));
const Corte = lazy(() => import("./telas/Corte").then((m) => ({ default: m.Corte })));
const Entrada = lazy(() => import("./telas/Entrada").then((m) => ({ default: m.Entrada })));
const Episodio = lazy(() => import("./telas/Episodio").then((m) => ({ default: m.Episodio })));
const Episodios = lazy(() => import("./telas/Episodios").then((m) => ({ default: m.Episodios })));

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
          <div className="topo-acoes">
            <AlternarTema />
            {naEntrada ? null : (
              <NavLink to="/configuracoes" className="topo-link">
                Configurações
              </NavLink>
            )}
          </div>
        </div>
      </header>
      <ErroDaTela key={pathname}>
        {/* Enquanto o código da tela chega, o esqueleto dela. */}
        <Suspense fallback={largo ? <EsqueletoCorte /> : <EsqueletoTela />}>
          <Rotas />
        </Suspense>
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
