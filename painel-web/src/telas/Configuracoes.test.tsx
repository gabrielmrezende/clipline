import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";
import { Configuracoes } from "./Configuracoes";

function resposta(corpo: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }),
  );
}

const CONFIG = () => ({
  provedor: "openai",
  provedores: {
    openai: { modelo: "gpt-image-1", qualidade: "low", preco_usd: 0.05 },
    google: { modelo: "imagen-4", qualidade: "standard", preco_usd: 0.04 },
  },
  chaves: { openai: true, google: false },
});

let puts: any[];
let getResp: () => Promise<Response>;
let putResp: (corpo: any) => Promise<Response>;

beforeEach(() => {
  puts = [];
  getResp = () => resposta(CONFIG());
  putResp = (corpo) => resposta({ ...CONFIG(), ...corpo });
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (url !== "/api/configuracoes/imagens") return resposta({ detail: "?" }, 404);
      if (init?.method === "PUT") {
        const corpo = JSON.parse(String(init.body));
        puts.push(corpo);
        return putResp(corpo);
      }
      return getResp();
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function montar() {
  const r = render(
    <MemoryRouter>
      <Configuracoes />
    </MemoryRouter>,
  );
  await act(async () => {});
  return r;
}

describe("Configuracoes", () => {
  it("mostra Conectado ou o comando conforme as chaves", async () => {
    await montar();
    expect(screen.getByText("Conectado")).toBeTruthy();
    expect(screen.getByText("Rode python -m esteira imagens conectar google")).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "Provedor" })).toHaveProperty("value", "openai");
    expect(screen.getByLabelText("Modelo (openai)")).toHaveProperty("value", "gpt-image-1");
    expect(screen.getByLabelText("Preço por imagem em US$ (google)")).toHaveProperty("value", "0.04");
  });

  it("nenhum campo pede a chave", async () => {
    const { container } = await montar();
    expect(container.querySelector('input[type="password"]')).toBeNull();
    expect(screen.queryByLabelText(/chave/i)).toBeNull();
  });

  it("Salvar manda o PUT com o corpo certo e confirma", async () => {
    await montar();
    fireEvent.change(screen.getByRole("combobox", { name: "Provedor" }), { target: { value: "google" } });
    fireEvent.change(screen.getByLabelText("Modelo (google)"), { target: { value: "imagen-5" } });
    fireEvent.change(screen.getByLabelText("Qualidade (google)"), { target: { value: "high" } });
    fireEvent.change(screen.getByLabelText("Preço por imagem em US$ (google)"), { target: { value: "0.06" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await act(async () => {});
    expect(puts).toEqual([
      {
        provedor: "google",
        provedores: {
          openai: { modelo: "gpt-image-1", qualidade: "low", preco_usd: 0.05 },
          google: { modelo: "imagen-5", qualidade: "high", preco_usd: 0.06 },
        },
      },
    ]);
    expect(screen.getByText("Configurações salvas.")).toBeTruthy();
  });

  it("mostra o detail do 422 do PUT", async () => {
    putResp = () => resposta({ detail: "Preço fora do limite." }, 422);
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await act(async () => {});
    expect(screen.getByRole("alert").textContent).toBe("Preço fora do limite.");
    expect(screen.queryByText("Configurações salvas.")).toBeNull();
  });

  it("preço vazio ou negativo é bloqueado antes do PUT", async () => {
    await montar();
    const preco = screen.getByLabelText("Preço por imagem em US$ (openai)");
    fireEvent.change(preco, { target: { value: "-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await act(async () => {});
    expect(puts).toEqual([]);
    expect(screen.getByRole("alert").textContent).toContain("preço");
    fireEvent.change(preco, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await act(async () => {});
    expect(puts).toEqual([]);
    expect(screen.getByRole("alert").textContent).toContain("preço");
  });

  it("se o GET falha, mostra a mensagem sem derrubar a tela", async () => {
    getResp = () => resposta({ detail: "Provedor desconhecido: xyz." }, 422);
    await montar();
    expect(screen.getByRole("alert").textContent).toBe("Provedor desconhecido: xyz.");
    expect(screen.getByRole("heading", { name: "Configurações" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "← Episódios" })).toBeTruthy();
  });
});
