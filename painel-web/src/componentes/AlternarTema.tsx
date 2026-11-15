import "./tema.css";
import { ReactNode, useEffect, useState } from "react";

export type Tema = "claro" | "escuro" | "sistema";

/** A mesma chave que o public/tema.js lê antes da primeira pintura. */
export const CHAVE_TEMA = "clipline.tema";

export function lerTema(): Tema {
  try {
    const salvo = window.localStorage.getItem(CHAVE_TEMA);
    return salvo === "claro" || salvo === "escuro" ? salvo : "sistema";
  } catch {
    return "sistema";
  }
}

/** Põe o tema na página e lembra a escolha; "sistema" volta a seguir o sistema operacional. */
export function aplicarTema(tema: Tema) {
  const raiz = document.documentElement;
  if (tema === "sistema") raiz.removeAttribute("data-tema");
  else raiz.setAttribute("data-tema", tema);
  try {
    if (tema === "sistema") window.localStorage.removeItem(CHAVE_TEMA);
    else window.localStorage.setItem(CHAVE_TEMA, tema);
  } catch {
    /* sem armazenamento: vale só nesta aba */
  }
}

const icone = (desenho: ReactNode) => (
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    {desenho}
  </svg>
);

const OPCOES: { tema: Tema; nome: string; desenho: ReactNode }[] = [
  {
    tema: "claro",
    nome: "Claro",
    desenho: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </>
    ),
  },
  {
    tema: "escuro",
    nome: "Escuro",
    desenho: <path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z" />,
  },
  {
    tema: "sistema",
    nome: "Do sistema",
    desenho: (
      <>
        <rect x="3" y="4" width="18" height="12" rx="2" />
        <path d="M8 20h8M12 16v4" />
      </>
    ),
  },
];

/** Claro, escuro ou do sistema. A escolha fica no navegador e vale para as outras abas do painel. */
export function AlternarTema() {
  const [tema, setTema] = useState<Tema>(lerTema);

  useEffect(() => {
    function outraAba(e: StorageEvent) {
      if (e.key !== null && e.key !== CHAVE_TEMA) return;
      const novo = lerTema();
      aplicarTema(novo);
      setTema(novo);
    }
    window.addEventListener("storage", outraAba);
    return () => window.removeEventListener("storage", outraAba);
  }, []);

  function escolher(novo: Tema) {
    aplicarTema(novo);
    setTema(novo);
  }

  return (
    <div className="alternar-tema" role="group" aria-label="Tema">
      {OPCOES.map((o) => (
        <button
          key={o.tema}
          type="button"
          aria-pressed={tema === o.tema}
          title={`Tema: ${o.nome.toLowerCase()}`}
          onClick={() => escolher(o.tema)}
        >
          {icone(o.desenho)}
          <span className="so-leitor">{o.nome}</span>
        </button>
      ))}
    </div>
  );
}
