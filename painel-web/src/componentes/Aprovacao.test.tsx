import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { Aprovacao } from "./Aprovacao";

const BASE = "/api/episodios/Ep%201/cortes/2";
const CONFIRMA =
  "Aprovar este corte? O corte.mp4 vai para video-final/ como corte-aprovado.mp4 e passa a ser o vídeo que o agendar publica.";

function resposta(corpo: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }),
  );
}

let desatualizada: boolean;
let postAprovar: () => Promise<Response>;
let confirmar: ReturnType<typeof vi.fn>;
let posts: string[];

beforeEach(() => {
  desatualizada = false;
  posts = [];
  postAprovar = () => resposta({ estado: "aprovado", motivo: null });
  confirmar = vi.fn(() => true);
  vi.stubGlobal("confirm", confirmar);
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

describe("Aprovacao", () => {
  it("Aprovar este vídeo confirma, chama a API e avisa a tela", async () => {
    const aoMudar = vi.fn();
    render(<Aprovacao ep="Ep 1" n={2} aprovacao={APROVAR} montando={false} aoMudar={aoMudar} />);
    fireEvent.click(screen.getByRole("button", { name: "Aprovar este vídeo" }));
    await esperar();
    expect(confirmar).toHaveBeenCalledWith(CONFIRMA);
    expect(posts).toEqual([JSON.stringify({ confirmado: true })]);
    expect(aoMudar).toHaveBeenCalledTimes(1);
  });

  it("a confirmação começa pelo aviso quando a montagem está desatualizada", async () => {
    desatualizada = true;
    render(<Aprovacao ep="Ep 1" n={2} aprovacao={APROVAR} montando={false} aoMudar={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Aprovar este vídeo" }));
    await esperar();
    expect(confirmar).toHaveBeenCalledWith(`As imagens mudaram desde a última montagem.\n${CONFIRMA}`);
  });

  it("com confirm falso não aprova", async () => {
    confirmar.mockReturnValue(false);
    const aoMudar = vi.fn();
    render(<Aprovacao ep="Ep 1" n={2} aprovacao={APROVAR} montando={false} aoMudar={aoMudar} />);
    fireEvent.click(screen.getByRole("button", { name: "Aprovar este vídeo" }));
    await esperar();
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
    render(<Aprovacao ep="Ep 1" n={2} aprovacao={APROVAR} montando={false} aoMudar={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Aprovar este vídeo" }));
    await esperar();
    expect(screen.getByRole("alert").textContent).toBe("video-final/ já tem um vídeo seu (Corte 1.mp4).");
  });
});
