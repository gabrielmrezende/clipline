import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { BlocoPublicacao, paraCampo } from "./BlocoPublicacao";

const BASE = "/api/episodios/Ep%201/cortes/2";

function resposta(corpo: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }));
}

let posts: { url: string; corpo: Record<string, unknown> }[];
let resumoStatus: number;

beforeEach(() => {
  posts = [];
  resumoStatus = 200;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (url === `${BASE}/publicacao` && !init?.method) {
        return resposta({ itens: [], redes: ["youtube", "tiktok"], data: "2026-11-08 18:00", modos: {} });
      }
      const corpo = init?.body ? JSON.parse(String(init.body)) : {};
      posts.push({ url, corpo });
      if (url === `${BASE}/publicacao/resumo`) {
        return resumoStatus === 200
          ? resposta({ resumo: "Corte 2: Título\nData: domingo", marca: "M1", ia: false })
          : resposta({ detail: "Não dá para agendar ainda.", problemas: ["video-final/ sem vídeo"] }, 422);
      }
      if (url === `${BASE}/publicacao`) {
        return resposta({ id: "t1", estado: "na fila", mensagem: "", avisos: [], tipo: "publicar" }, 202);
      }
      return resposta({ detail: "?" }, 404);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function esperar() {
  for (let i = 0; i < 5; i += 1) {
    await act(async () => {
      await Promise.resolve();
    });
  }
}

describe("BlocoPublicacao", () => {
  it("converte a data do aprovados.json para o campo", () => {
    expect(paraCampo("2026-11-08 18:00")).toBe("2026-11-08T18:00");
    expect(paraCampo("amanhã")).toBe("");
  });

  it("mostra o resumo e só confirma com a marca dele", async () => {
    render(<BlocoPublicacao ep="Ep 1" n={2} />);
    await esperar();
    expect((screen.getByLabelText("Data e hora (Brasília)") as HTMLInputElement).value).toBe("2026-11-08T18:00");
    expect((screen.getByLabelText("YouTube") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Instagram") as HTMLInputElement).checked).toBe(false);
    expect(screen.queryByRole("button", { name: "Confirmar o agendamento" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Ver o resumo" }));
    await esperar();
    expect(screen.getByLabelText("Resumo da publicação").textContent).toContain("Corte 2: Título");
    fireEvent.click(screen.getByRole("button", { name: "Confirmar o agendamento" }));
    await esperar();
    const confirmacao = posts.find((p) => p.url === `${BASE}/publicacao`);
    expect(confirmacao?.corpo).toEqual({ data: "2026-11-08T18:00", redes: ["youtube", "tiktok"], marca: "M1", confirmado: true });
    expect(screen.getByRole("status").textContent).toContain("Na fila");
  });

  it("lista o que falta quando o agendar recusa", async () => {
    resumoStatus = 422;
    render(<BlocoPublicacao ep="Ep 1" n={2} />);
    await esperar();
    fireEvent.click(screen.getByRole("button", { name: "Ver o resumo" }));
    await esperar();
    expect(screen.getByRole("list", { name: "O que falta para agendar" }).textContent).toContain("video-final/ sem vídeo");
    expect(screen.queryByRole("button", { name: "Confirmar o agendamento" })).toBeNull();
  });

  it("mudar a rede esconde o resumo antigo", async () => {
    render(<BlocoPublicacao ep="Ep 1" n={2} />);
    await esperar();
    fireEvent.click(screen.getByRole("button", { name: "Ver o resumo" }));
    await esperar();
    fireEvent.click(screen.getByLabelText("Instagram"));
    expect(screen.queryByRole("button", { name: "Confirmar o agendamento" })).toBeNull();
  });
});
