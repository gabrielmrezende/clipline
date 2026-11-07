import { caminhoEpisodio, pedir } from "./api";

describe("api", () => {
  it("codifica o nome do episódio", () => {
    expect(caminhoEpisodio("Entre Assuntos 03 - Arthur Cerqueira (teste capcut)")).toBe(
      "/api/episodios/Entre%20Assuntos%2003%20-%20Arthur%20Cerqueira%20(teste%20capcut)",
    );
  });

  it("redireciona para /entrar no 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "Entre com o código de acesso." }), { status: 401 })),
    );
    const assign = vi.fn();
    vi.stubGlobal("location", { pathname: "/", assign });
    await expect(pedir("/api/episodios")).rejects.toMatchObject({ status: 401 });
    expect(assign).toHaveBeenCalledWith("/entrar");
    vi.unstubAllGlobals();
  });
});
