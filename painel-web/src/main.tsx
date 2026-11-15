import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@fontsource-variable/schibsted-grotesk";
import { App } from "./App";
import { ProvedorConfirmacao } from "./componentes/Confirmacao";
import "./estilo.css";

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <BrowserRouter>
      <ProvedorConfirmacao>
        <App />
      </ProvedorConfirmacao>
    </BrowserRouter>
  </StrictMode>,
);
