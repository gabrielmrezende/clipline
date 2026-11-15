import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import type { Pedido } from "../api";
import { AndamentoPedido, frase, paraRetomar } from "./imagensComum";

function pedido(extra: Partial<Pedido> = {}): Pedido {
  return {
    id: "t1",
    episodio: "Ep 1",
    numero: 2,
    arquivo: "",
    volume_db: 0,
    estado: "na fila",
    mensagem: "",
    avisos: [],
    anterior: null,
    criado: 1,
    terminado: null,
    tipo: "ia",
    cortes: [2],
    progresso: "",
    ...extra,
  };
}

let chamadas: { url: string; metodo: string; corpo: unknown }[];
let respostaCancelar: () => Promise<Response>;

const json = (corpo: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }));

beforeEach(() => {
  chamadas = [];
  respostaCancelar = () => json(pedido({ estado: "cancelado", mensagem: "cancelado antes de começar" }));
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      chamadas.push({ url, metodo: init?.method ?? "GET", corpo: init?.body ? JSON.parse(String(init.body)) : null });
      return respostaCancelar();
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function clicar(nome: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: nome }));
  });
}

describe("AndamentoPedido", () => {
  it("na fila: Cancelar o pedido manda o pedido confirmado e mostra o resultado", async () => {
    const aoMudar = vi.fn();
    render(<AndamentoPedido pedido={pedido()} aoMudar={aoMudar} />);
    expect(screen.getByText("Na fila")).toBeTruthy();
    await clicar("Cancelar o pedido");
    expect(chamadas).toEqual([{ url: "/api/tarefas/t1/cancelar", metodo: "POST", corpo: { confirmado: true } }]);
    expect(aoMudar).toHaveBeenCalledWith(expect.objectContaining({ estado: "cancelado" }));
  });

  it("cancelado mostra a mensagem como frase", () => {
    render(<AndamentoPedido pedido={pedido({ estado: "cancelado", mensagem: "cancelado antes de começar" })} />);
    expect(screen.getByText("Cancelado antes de começar.")).toBeTruthy();
  });

  it("interrompido: Tentar de novo segue o caminho do botão e Descartar cancela", async () => {
    const aoTentarDeNovo = vi.fn();
    const aoMudar = vi.fn();
    render(
      <AndamentoPedido
        pedido={pedido({ estado: "interrompido", mensagem: "o painel foi fechado antes de montar este pedido" })}
        aoMudar={aoMudar}
        aoTentarDeNovo={aoTentarDeNovo}
      />,
    );
    expect(screen.getByText("Interrompido: o painel foi fechado antes de montar este pedido.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(aoTentarDeNovo).toHaveBeenCalledTimes(1);
    expect(chamadas).toEqual([]);
    await clicar("Descartar o pedido");
    expect(chamadas.map((c) => c.url)).toEqual(["/api/tarefas/t1/cancelar"]);
    expect(aoMudar).toHaveBeenCalled();
  });

  it("IA gerando pode parar antes da próxima imagem; parando, o botão some", async () => {
    const { rerender } = render(
      <AndamentoPedido pedido={pedido({ estado: "montando", progresso: "Gerando 1 de 3…" })} aoMudar={vi.fn()} />,
    );
    expect(screen.getByText("Gerando 1 de 3…")).toBeTruthy();
    await clicar("Parar antes da próxima imagem");
    rerender(<AndamentoPedido pedido={pedido({ estado: "montando", cancelando: true })} aoMudar={vi.fn()} />);
    expect(screen.getByText("Parando antes da próxima imagem…")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("fotos, montagem e publicação não param no meio: sem botão enquanto andam", () => {
    for (const tipo of ["fotos", "montar", "publicar"]) {
      const { unmount } = render(<AndamentoPedido pedido={pedido({ estado: "montando", tipo })} aoMudar={vi.fn()} />);
      expect(screen.queryByRole("button")).toBeNull();
      unmount();
    }
  });

  it("sem aoMudar não há botão de cancelar", () => {
    render(<AndamentoPedido pedido={pedido()} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("a recusa do servidor aparece no bloco", async () => {
    respostaCancelar = () => json({ detail: "Este pedido já terminou." }, 409);
    const aoMudar = vi.fn();
    render(<AndamentoPedido pedido={pedido()} aoMudar={aoMudar} />);
    await clicar("Cancelar o pedido");
    expect(screen.getByRole("alert").textContent).toBe("Este pedido já terminou.");
    expect(aoMudar).not.toHaveBeenCalled();
  });
});

describe("paraRetomar", () => {
  it("o que anda; senão o último, se foi interrompido", () => {
    const andando = pedido({ id: "a", estado: "montando" });
    const interrompido = pedido({ id: "i", estado: "interrompido" });
    const pronto = pedido({ id: "p", estado: "pronto" });
    expect(paraRetomar([interrompido, andando])?.id).toBe("a");
    expect(paraRetomar([interrompido, pronto])?.id).toBe("i");
    expect(paraRetomar([pronto, interrompido])).toBeUndefined(); // o dono já seguiu em frente
    expect(paraRetomar([pedido({ estado: "cancelado" })])).toBeUndefined();
    expect(paraRetomar([])).toBeUndefined();
  });
});

describe("frase", () => {
  it("primeira letra maiúscula e ponto no fim", () => {
    expect(frase("cancelado antes de começar")).toBe("Cancelado antes de começar.");
    expect(frase("Já tem ponto.")).toBe("Já tem ponto.");
    expect(frase("")).toBe("");
  });
});
