import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { EditorLegenda } from "./EditorLegenda";

const BASE = "/api/episodios/Ep%201/cortes/2";

function resposta(corpo: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }));
}

let puts: Record<string, unknown>[];

beforeEach(() => {
  puts = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (url === `${BASE}/legenda` && !init?.method) {
        return resposta({
          versao: "V1",
          max_caracteres: 40,
          telas: [
            { indice: 0, inicio: 0, fim: 1, linhas: ["olá Brazil"] },
            { indice: 1, inicio: 1, fim: 2, linhas: ["tudo bem"] },
          ],
        });
      }
      if (url === `${BASE}/legenda` && init?.method === "PUT") {
        puts.push(JSON.parse(String(init.body)));
        return resposta({ versao: "V2", remontar: true });
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
  for (let i = 0; i < 4; i += 1) {
    await act(async () => {
      await Promise.resolve();
    });
  }
}

function montar() {
  const props = {
    irPara: vi.fn(),
    soltarVideo: vi.fn(),
    aoMudarAndamento: vi.fn(),
    aoTerminarMontagem: vi.fn(),
  };
  render(<EditorLegenda ep="Ep 1" n={2} montandoNaTela={false} {...props} />);
  return props;
}

describe("EditorLegenda", () => {
  it("salva só as telas mudadas e oferece montar", async () => {
    montar();
    await esperar();
    fireEvent.click(screen.getByRole("button", { name: "Editar o texto (2 telas)" }));
    fireEvent.change(screen.getByLabelText("Tela 1, 0:00"), { target: { value: "olá Brasil" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar 1 tela" }));
    await esperar();
    expect(puts).toEqual([{ versao: "V1", telas: [{ indice: 0, linhas: ["olá Brasil"] }] }]);
    expect(screen.getByRole("button", { name: "Montar com a legenda nova" })).toBeTruthy();
  });

  it("avisa linha longa e volta ao original sem contar como mudança", async () => {
    montar();
    await esperar();
    fireEvent.click(screen.getByRole("button", { name: "Editar o texto (2 telas)" }));
    const campo = screen.getByLabelText("Tela 2, 0:01");
    fireEvent.change(campo, { target: { value: "x".repeat(41) } });
    expect(campo.getAttribute("aria-invalid")).toBe("true");
    fireEvent.change(campo, { target: { value: "tudo bem" } });
    expect(screen.queryByRole("button", { name: /Salvar/ })).toBeNull();
  });

  it("o tempo leva o player até a tela", async () => {
    const props = montar();
    await esperar();
    fireEvent.click(screen.getByRole("button", { name: "Editar o texto (2 telas)" }));
    fireEvent.click(screen.getByRole("button", { name: "Ir para 0:01" }));
    expect(props.irPara).toHaveBeenCalledWith(1);
  });
});
