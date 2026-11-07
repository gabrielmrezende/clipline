import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { EditorPost } from "./EditorPost";

const CAMPOS = {
  youtube_titulo: "Título",
  youtube_descricao: "Descrição",
  instagram: "Legenda",
  tiktok: "Tik",
};

function postOk(extra: object = {}) {
  return {
    campos: CAMPOS,
    somente_leitura: { Observações: "nota interna" },
    credito: "Crédito: fulano",
    redes: ["youtube"],
    versao: "v1",
    avisos: [],
    erro: null,
    ...extra,
  };
}

function resposta(corpo: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(corpo), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

let chamadas: { url: string; metodo: string; corpo: any }[];
let manipulador: (url: string, metodo: string) => Promise<Response>;

beforeEach(() => {
  vi.useFakeTimers();
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      chamadas.push({ url, metodo, corpo: init?.body ? JSON.parse(String(init.body)) : null });
      return manipulador(url, metodo);
    }),
  );
  manipulador = (url, metodo) => {
    if (url.endsWith("/post/conferir")) return resposta({ avisos: [] });
    if (metodo === "PUT") return resposta({ versao: "v2", avisos: [] });
    return resposta(postOk());
  };
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function montar() {
  render(<EditorPost ep="Ep 1" n={2} />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

async function avancar(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

const conferencias = () => chamadas.filter((c) => c.url.endsWith("/post/conferir"));

describe("EditorPost", () => {
  it("contador fica vermelho acima de 100", async () => {
    await montar();
    fireEvent.change(screen.getByLabelText(/Título do YouTube/), {
      target: { value: "x".repeat(101) },
    });
    const contador = screen.getByText("101/100");
    expect(contador.className).toContain("acima");
  });

  it("confere uma vez 400 ms depois de parar de digitar", async () => {
    await montar();
    const campo = screen.getByLabelText(/Instagram/);
    fireEvent.change(campo, { target: { value: "a" } });
    fireEvent.change(campo, { target: { value: "ab" } });
    fireEvent.change(campo, { target: { value: "abc" } });
    await avancar(399);
    expect(conferencias()).toHaveLength(0);
    await avancar(1);
    expect(conferencias()).toHaveLength(1);
  });

  it("conflito mantém o rascunho", async () => {
    manipulador = (url, metodo) => {
      if (metodo === "PUT")
        return resposta(
          { detail: "O post.md mudou desde que você abriu.", versao_atual: "v9" },
          409,
        );
      if (url.endsWith("/post/conferir")) return resposta({ avisos: [] });
      return resposta(postOk());
    };
    await montar();
    const campo = screen.getByLabelText(/Instagram/) as HTMLTextAreaElement;
    fireEvent.change(campo, { target: { value: "rascunho meu" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await avancar(0);
    expect(screen.getByText("O post.md mudou desde que você abriu.")).toBeTruthy();
    expect(campo.value).toBe("rascunho meu");
    expect(screen.getByRole("button", { name: "Carregar a versão nova" })).toBeTruthy();
  });

  it("post quebrado desabilita", async () => {
    manipulador = () =>
      resposta({ erro: "post.md sem seção do YouTube", versao: null, campos: null });
    await montar();
    expect(screen.getByText("post.md sem seção do YouTube")).toBeTruthy();
    for (const campo of screen.getAllByRole("textbox")) {
      expect((campo as HTMLTextAreaElement).disabled).toBe(true);
    }
    expect((screen.getByRole("button", { name: "Salvar" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("salvar envia a versão lida e usa a nova no próximo salvar", async () => {
    await montar();
    fireEvent.change(screen.getByLabelText(/Instagram/), { target: { value: "novo" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await avancar(0);
    const puts = () => chamadas.filter((c) => c.metodo === "PUT");
    expect(puts()[0].corpo.versao).toBe("v1");
    expect(puts()[0].corpo.campos.instagram).toBe("novo");
    expect(screen.getByText("Salvo.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await avancar(0);
    expect(puts()[1].corpo.versao).toBe("v2");
  });

  it("422 mostra a mensagem e mantém o rascunho", async () => {
    manipulador = (_url, metodo) => {
      if (metodo === "PUT")
        return resposta({ detail: "O título do YouTube não pode ter quebra de linha." }, 422);
      return resposta(postOk());
    };
    await montar();
    const campo = screen.getByLabelText(/Instagram/) as HTMLTextAreaElement;
    fireEvent.change(campo, { target: { value: "meu texto" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await avancar(0);
    expect(screen.getByRole("alert").textContent).toContain("quebra de linha");
    expect(campo.value).toBe("meu texto");
  });

  it("carregar a versão nova refaz o GET e troca os campos", async () => {
    let gets = 0;
    manipulador = (_url, metodo) => {
      if (metodo === "PUT")
        return resposta({ detail: "O post.md mudou desde que você abriu.", versao_atual: "v9" }, 409);
      gets += 1;
      return resposta(
        gets === 1 ? postOk() : postOk({ versao: "v9", campos: { ...CAMPOS, instagram: "do disco" } }),
      );
    };
    await montar();
    const campo = screen.getByLabelText(/Instagram/) as HTMLTextAreaElement;
    fireEvent.change(campo, { target: { value: "rascunho" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await avancar(0);
    fireEvent.click(screen.getByRole("button", { name: "Carregar a versão nova" }));
    await avancar(0);
    expect(campo.value).toBe("do disco");
    expect(screen.queryByText("O post.md mudou desde que você abriu.")).toBeNull();
  });
});
