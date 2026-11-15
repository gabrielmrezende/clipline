import { readFileSync } from "node:fs";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
import { AlternarTema, CHAVE_TEMA, aplicarTema, lerTema } from "./AlternarTema";

// O Vitest troca o CSS importado por texto vazio, então os arquivos são lidos direto do disco.
const ler = (relativo: string) => readFileSync(new URL(relativo, import.meta.url), "utf-8");
const estilo = ler("../estilo.css");
const tema = ler("./tema.css");
const script = ler("../../public/tema.js");

const raiz = () => document.documentElement;

beforeEach(() => {
  localStorage.clear();
  raiz().removeAttribute("data-tema");
});
afterEach(() => {
  localStorage.clear();
  raiz().removeAttribute("data-tema");
});

/** As declarações (cor e variáveis) do primeiro bloco depois do seletor, em ordem. */
function declaracoes(css: string, seletor: string): string[] {
  const inicio = css.indexOf(seletor);
  expect(inicio).toBeGreaterThanOrEqual(0);
  const abre = css.indexOf("{", inicio);
  const fecha = css.indexOf("}", abre);
  return css
    .slice(abre + 1, fecha)
    .split(";")
    .map((d) => d.trim().replace(/\s+/g, " "))
    .filter(Boolean);
}

describe("AlternarTema", () => {
  it("começa no do sistema e marca a escolha", () => {
    render(<AlternarTema />);
    const grupo = screen.getByRole("group", { name: "Tema" });
    expect(grupo).toBeTruthy();
    expect(screen.getByRole("button", { name: "Do sistema" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Escuro" }));
    expect(raiz().getAttribute("data-tema")).toBe("escuro");
    expect(localStorage.getItem(CHAVE_TEMA)).toBe("escuro");
    expect(screen.getByRole("button", { name: "Escuro" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Do sistema" }).getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Claro" }));
    expect(raiz().getAttribute("data-tema")).toBe("claro");
    fireEvent.click(screen.getByRole("button", { name: "Do sistema" }));
    expect(raiz().hasAttribute("data-tema")).toBe(false);
    expect(localStorage.getItem(CHAVE_TEMA)).toBeNull();
  });

  it("lê a escolha salva e ignora valor estranho", () => {
    localStorage.setItem(CHAVE_TEMA, "claro");
    expect(lerTema()).toBe("claro");
    render(<AlternarTema />);
    expect(screen.getByRole("button", { name: "Claro" }).getAttribute("aria-pressed")).toBe("true");
    localStorage.setItem(CHAVE_TEMA, "roxo");
    expect(lerTema()).toBe("sistema");
  });

  it("acompanha a escolha feita em outra aba", () => {
    render(<AlternarTema />);
    act(() => {
      localStorage.setItem(CHAVE_TEMA, "escuro");
      window.dispatchEvent(new StorageEvent("storage", { key: CHAVE_TEMA, newValue: "escuro" }));
    });
    expect(raiz().getAttribute("data-tema")).toBe("escuro");
    expect(screen.getByRole("button", { name: "Escuro" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("sem armazenamento, o tema vale só na aba", () => {
    const original = Object.getOwnPropertyDescriptor(window, "localStorage")!;
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("bloqueado");
      },
    });
    try {
      expect(lerTema()).toBe("sistema");
      aplicarTema("escuro");
      expect(raiz().getAttribute("data-tema")).toBe("escuro");
    } finally {
      Object.defineProperty(window, "localStorage", original);
    }
  });

  it("o escuro escolhido à mão tem as mesmas cores do escuro do sistema", () => {
    const doSistema = declaracoes(estilo, ':root:not([data-tema="claro"])');
    const escolhido = declaracoes(tema, ':root[data-tema="escuro"]');
    expect(doSistema.length).toBeGreaterThan(10);
    expect(escolhido).toEqual(doSistema);
  });

  it("o script de antes da pintura usa a mesma chave e os mesmos valores", () => {
    expect(script).toContain(`"${CHAVE_TEMA}"`);
    for (const valor of ["claro", "escuro"]) {
      localStorage.setItem(CHAVE_TEMA, valor);
      new Function(script)();
      expect(raiz().getAttribute("data-tema")).toBe(valor);
      raiz().removeAttribute("data-tema");
    }
    localStorage.setItem(CHAVE_TEMA, "outro");
    new Function(script)();
    expect(raiz().hasAttribute("data-tema")).toBe(false);
  });
});
