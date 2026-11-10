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

  it("a aba Imagens só consulta o resumo de fotos quando é aberta", async () => {
    const abrir = async (url: string) => {
      const { unmount } = render(
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/episodios/:ep" element={<Episodio />} />
          </Routes>
        </MemoryRouter>,
      );
      await act(async () => {});
      await act(async () => {});
      unmount();
    };
    const base = (fetch as unknown as ReturnType<typeof vi.fn>).getMockImplementation()!;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const vazio = (c: unknown) =>
          Promise.resolve(new Response(JSON.stringify(c), { status: 200, headers: { "Content-Type": "application/json" } }));
        if (url.endsWith("/fotos/resumo")) return vazio({ fotos: 0, megabytes: 0, origem: "Wikimedia", avisos: [] });
        if (url.endsWith("/ia/orcamento")) return vazio({ imagens: 0, provedor: "openai", modelo: "m", custo_usd: 0 });
        if (url.endsWith("/momentos")) return vazio({ versao: "v1", momentos: [] });
        if (url === "/api/tarefas") return vazio([]);
        return base(url, init);
      }),
    );
    const consultou = () =>
      (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.some((c) => String(c[0]).endsWith("/fotos/resumo"));
    await abrir("/episodios/Ep%201");
    expect(consultou()).toBe(false);
    await abrir("/episodios/Ep%201?aba=imagens");
    expect(consultou()).toBe(true);
  });
});
