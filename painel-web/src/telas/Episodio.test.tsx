import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";
import { Episodio } from "./Episodio";

function bloco(numero: number, extra: object = {}) {
  return {
    numero,
    titulo: `Corte ${numero}`,
    pasta: `0${numero}-corte`,
    clima: "leve",
    instagram: false,
    redes: ["youtube"],
    data: "",
    musica: null,
    antes: "",
    depois: "",
    alertas: [],
    video_final: [],
    tem_guia: false,
    erro: null,
    avisos_post: [],
    video_final_desatualizado: false,
    montando: false,
    selo: "pronto",
    ...extra,
  };
}

beforeEach(() => {
  const detalhe = {
    resumo: { nome: "Ep 1", total: 2, prontos: 1, proxima_data: null, aviso: null },
    cortes: [bloco(1, { montando: true, selo: "erro", erro: "corte não montado" }), bloco(2)],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(detalhe), { status: 200, headers: { "Content-Type": "application/json" } }),
      ),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Episodio", () => {
  it("cartão com montando mostra montando… no lugar do selo", async () => {
    render(
      <MemoryRouter initialEntries={["/episodios/Ep%201"]}>
        <Routes>
          <Route path="/episodios/:ep" element={<Episodio />} />
        </Routes>
      </MemoryRouter>,
    );
    await act(async () => {});
    const [primeiro, segundo] = screen.getAllByRole("listitem");
    expect(primeiro.textContent).toContain("montando…");
    expect(primeiro.textContent).not.toContain("erro");
    expect(segundo.textContent).toContain("pronto");
    expect(segundo.textContent).not.toContain("montando…");
  });
});
