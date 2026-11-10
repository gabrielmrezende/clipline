import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { Momento } from "../api";
import { CartaoMomento } from "./CartaoMomento";

function momento(extra: Partial<Momento> = {}): Momento {
  return {
    chave: "f1",
    inicio: 65,
    fim: 70,
    fala: "Fala do momento",
    tipo: "foto",
    nome: "lula",
    busca: "lula",
    titulo: "",
    veiculo: "",
    data: "",
    prompt: "",
    aprovado: false,
    descartar: false,
    motivo: "",
    candidatas: [],
    escolhas: [],
    fotos_prontas: [],
    ia: [],
    pessoa_citada: null,
    ...extra,
  };
}

function props(m: Momento) {
  return {
    m,
    ep: "Ep 1",
    n: 2,
    bloqueado: false,
    gerando: false,
    erro: null,
    precoIa: 0.05,
    irPara: vi.fn(),
    alterar: vi.fn(),
    buscar: vi.fn(),
    gerarDeNovo: vi.fn(),
  };
}

describe("CartaoMomento", () => {
  it("mostra tempo, fala e tipo", () => {
    render(<CartaoMomento {...props(momento())} />);
    expect(screen.getByText("1:05")).toBeTruthy();
    expect(screen.getByText("Fala do momento")).toBeTruthy();
    expect(screen.getByText("Foto")).toBeTruthy();
  });

  it("momento descartado aparece esmaecido, só com Restaurar", () => {
    const p = props(momento({ descartar: true }));
    const { container } = render(<CartaoMomento {...p} />);
    expect(container.querySelector(".momento.descartado")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Descartar" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Restaurar" }));
    expect(p.alterar).toHaveBeenCalledWith({ descartar: false }, { descartar: false });
  });

  it("mostra o erro perto do cartão", () => {
    const p = { ...props(momento()), erro: "Escreva o prompt antes de aprovar." };
    render(<CartaoMomento {...p} />);
    expect(screen.getByRole("alert").textContent).toBe("Escreva o prompt antes de aprovar.");
  });

  it("momento de IA troca para foto", () => {
    const p = props(momento({ tipo: "ia", prompt: "x" }));
    render(<CartaoMomento {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "Trocar para foto" }));
    expect(p.alterar).toHaveBeenCalledWith({ tipo: "foto" }, { tipo: "foto", aprovado: false });
  });
});
