import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { dialogoAberto, haDialogo, responderDialogo, textoDoDialogo, tituloDoDialogo } from "../testes/dialogo";
import { Aprovacao } from "./Aprovacao";
import { ProvedorConfirmacao } from "./Confirmacao";

const BASE = "/api/episodios/Ep%201/cortes/2";
const CONFIRMA =
  "O corte.mp4 vai para video-final/ como corte-aprovado.mp4 e passa a ser o vídeo que o agendar publica.";

function resposta(corpo: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }),
  );
}

let desatualizada: boolean;
let postAprovar: () => Promise<Response>;
let posts: string[];

beforeEach(() => {
  desatualizada = false;
  posts = [];
  postAprovar = () => resposta({ estado: "aprovado", motivo: null });
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (url === BASE && !init?.method) return resposta({ montagem_desatualizada: desatualizada });
      if (url === `${BASE}/aprovar` && init?.method === "POST") {
        posts.push(String(init.body));
        return postAprovar();
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

const APROVAR = { estado: "aprovar" as const, motivo: null };
const comConfirmacao = { wrapper: ProvedorConfirmacao };

describe("Aprovacao", () => {
  it("Aprovar este vídeo confirma, chama a API e avisa a tela", async () => {
    const aoMudar = vi.fn();
    render(<Aprovacao ep="Ep 1" n={2} aprovacao={APROVAR} montando={false} aoMudar={aoMudar} />, comConfirmacao);
    fireEvent.click(screen.getByRole("button", { name: "Aprovar este vídeo" }));
    await esperar();
    expect(tituloDoDialogo()).toBe("Aprovar este corte?");
    expect(textoDoDialogo()).toContain(CONFIRMA);
    expect(textoDoDialogo()).not.toContain("As imagens mudaram");
    expect(posts).toEqual([]);
    responderDialogo(true);
    await esperar();
    expect(posts).toEqual([JSON.stringify({ confirmado: true })]);
    expect(aoMudar).toHaveBeenCalledTimes(1);
  });

  it("a confirmação começa pelo aviso quando a montagem está desatualizada", async () => {
    desatualizada = true;
    render(<Aprovacao ep="Ep 1" n={2} aprovacao={APROVAR} montando={false} aoMudar={vi.fn()} />, comConfirmacao);
    fireEvent.click(screen.getByRole("button", { name: "Aprovar este vídeo" }));
    await esperar();
    const texto = textoDoDialogo();
    expect(texto).toContain("As imagens mudaram desde a última montagem.");
    expect(texto.indexOf("As imagens mudaram")).toBeLessThan(texto.indexOf(CONFIRMA));
  });

  it("cancelar a confirmação não aprova e devolve o botão", async () => {
    const aoMudar = vi.fn();
    render(<Aprovacao ep="Ep 1" n={2} aprovacao={APROVAR} montando={false} aoMudar={aoMudar} />, comConfirmacao);
    const botao = screen.getByRole("button", { name: "Aprovar este vídeo" }) as HTMLButtonElement;
    fireEvent.click(botao);
    await esperar();
    expect(dialogoAberto()).toBeTruthy();
    expect(botao.disabled).toBe(true);
    responderDialogo(false);
    await esperar();
    expect(haDialogo()).toBe(false);
    expect(botao.disabled).toBe(false);
    expect(posts).toEqual([]);
    expect(aoMudar).not.toHaveBeenCalled();
  });

  it("Aprovar de novo, Aprovado e bloqueado mostram o texto certo", () => {
    const { rerender } = render(
      <Aprovacao ep="Ep 1" n={2} aprovacao={{ estado: "aprovar de novo", motivo: null }} montando={false} aoMudar={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Aprovar de novo" })).toBeTruthy();
    rerender(<Aprovacao ep="Ep 1" n={2} aprovacao={{ estado: "aprovado", motivo: null }} montando={false} aoMudar={vi.fn()} />);
    expect(screen.getByText("Aprovado")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
    rerender(
      <Aprovacao
        ep="Ep 1"
        n={2}
        aprovacao={{ estado: "bloqueado", motivo: "corte não montado" }}
        montando={false}
        aoMudar={vi.fn()}
      />,
    );
    expect(screen.getByText("corte não montado")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("fica desabilitado enquanto o corte é montado", () => {
    render(<Aprovacao ep="Ep 1" n={2} aprovacao={APROVAR} montando={true} aoMudar={vi.fn()} />);
    expect((screen.getByRole("button", { name: "Aprovar este vídeo" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("mostra o motivo quando o servidor recusa", async () => {
    postAprovar = () => resposta({ detail: "video-final/ já tem um vídeo seu (Corte 1.mp4)." }, 409);
    render(<Aprovacao ep="Ep 1" n={2} aprovacao={APROVAR} montando={false} aoMudar={vi.fn()} />, comConfirmacao);
    fireEvent.click(screen.getByRole("button", { name: "Aprovar este vídeo" }));
    await esperar();
    responderDialogo(true);
    await esperar();
    expect(screen.getByRole("alert").textContent).toBe("video-final/ já tem um vídeo seu (Corte 1.mp4).");
  });
});
