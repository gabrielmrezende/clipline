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

  describe("Gerar (de novo)", () => {
    const versao = (k: number) => ({ arquivo: `i1-ia-${k}.jpg`, versao: k, provedor: "openai", data: "2026-11-09" });
    const ia = (extra: Partial<Momento> = {}) =>
      momento({ chave: "i1", tipo: "ia", prompt: "uma sala vazia", aprovado: true, ...extra });
    const botao = () => screen.getByRole("button", { name: /^Gerar/ }) as HTMLButtonElement;

    it("chama-se Gerar sem versão e Gerar de novo com versão", () => {
      const { unmount } = render(<CartaoMomento {...props(ia())} />);
      expect(botao().textContent).toBe("Gerar");
      expect(botao().disabled).toBe(false);
      unmount();
      render(<CartaoMomento {...props(ia({ ia: [versao(1)] }))} />);
      expect(botao().textContent).toBe("Gerar de novo");
      expect(botao().disabled).toBe(false);
    });

    it("confirma com o preço e o rótulo do botão", () => {
      const confirmar = vi.fn(() => true);
      vi.stubGlobal("confirm", confirmar);
      const p = props(ia());
      render(<CartaoMomento {...p} />);
      fireEvent.click(botao());
      expect(confirmar).toHaveBeenCalledWith("Gerar esta imagem: 1 imagem, ~US$ 0,05?");
      expect(p.gerarDeNovo).toHaveBeenCalledTimes(1);
      vi.unstubAllGlobals();
    });

    it.each([
      ["sem aprovação", { m: ia({ aprovado: false }) }],
      ["com 3 versões", { m: ia({ ia: [versao(1), versao(2), versao(3)] }) }],
      ["durante o download de fotos", { m: ia(), bloqueado: true }],
      ["durante um pedido de IA", { m: ia(), gerando: true }],
      ["sem preço configurado", { m: ia(), precoIa: null }],
    ])("fica desabilitado %s", (_nome, extra) => {
      const { m, ...resto } = extra as { m: Momento };
      render(<CartaoMomento {...props(m)} {...resto} />);
      expect(botao().disabled).toBe(true);
    });

    it("fica desabilitado com o prompt editado e não salvo", () => {
      render(<CartaoMomento {...props(ia())} />);
      fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "outro prompt" } });
      expect(botao().disabled).toBe(true);
    });
  });

  it("momento de IA troca para foto", () => {
    const p = props(momento({ tipo: "ia", prompt: "x" }));
    render(<CartaoMomento {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "Trocar para foto" }));
    expect(p.alterar).toHaveBeenCalledWith({ tipo: "foto" }, { tipo: "foto", aprovado: false });
  });
});
