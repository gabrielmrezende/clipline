import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, vi } from "vitest";
import { Episodios } from "../telas/Episodios";
import { EsqueletoCartoes, EsqueletoCorte, EsqueletoEpisodios, EsqueletoLinhas, EsqueletoTela } from "./Esqueleto";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Esqueletos", () => {
  it.each([
    ["linhas", <EsqueletoLinhas key="l" rotulo="Carregando o post…" linhas={4} />, "Carregando o post…"],
    ["episódios", <EsqueletoEpisodios key="e" />, "Carregando os episódios…"],
    ["cartões", <EsqueletoCartoes key="c" />, "Carregando os cortes…"],
    ["corte", <EsqueletoCorte key="k" />, "Carregando o corte…"],
    ["tela", <EsqueletoTela key="t" />, "Carregando…"],
  ])("%s: o leitor de tela ouve o rótulo e as formas ficam fora da árvore", (_nome, elemento, rotulo) => {
    const { container } = render(elemento);
    expect(screen.getByRole("status").textContent).toBe(rotulo);
    const formas = container.querySelector(".esqueleto-formas") as HTMLElement;
    expect(formas.getAttribute("aria-hidden")).toBe("true");
    expect(formas.querySelectorAll(".osso").length).toBeGreaterThan(0);
  });

  it("linhas: quantas pedir", () => {
    const { container } = render(<EsqueletoLinhas rotulo="x" linhas={5} />);
    expect(container.querySelectorAll(".osso")).toHaveLength(5);
  });

  it("corte: mostra o voltar enquanto carrega", () => {
    render(<EsqueletoCorte voltar={<a href="/episodios/Ep">← Ep</a>} />);
    expect(screen.getByRole("link", { name: "← Ep" })).toBeTruthy();
    expect(screen.getByRole("main").getAttribute("aria-busy")).toBe("true");
  });

  it("a lista de episódios mostra o esqueleto até a resposta chegar", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(
      <MemoryRouter>
        <Episodios />
      </MemoryRouter>,
    );
    expect(screen.getByRole("status").textContent).toBe("Carregando os episódios…");
    expect(screen.queryByText("Carregando…")).toBeNull();
  });
});
