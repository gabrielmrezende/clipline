import { Route, Routes } from "react-router-dom";
import { Configuracoes } from "./telas/Configuracoes";
import { Corte } from "./telas/Corte";
import { Entrada } from "./telas/Entrada";
import { Episodio } from "./telas/Episodio";
import { Episodios } from "./telas/Episodios";

export function App() {
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
