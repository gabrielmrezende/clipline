import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";
import type { Bloco, Momento, Pedido } from "../api";
import { ImagensDoEpisodio } from "./ImagensDoEpisodio";

function momento(extra: Partial<Momento> = {}): Momento {
  return {
    chave: "f1", inicio: 1, fim: 2, fala: "", tipo: "foto", nome: "", busca: "", titulo: "", veiculo: "",
    data: "", prompt: "", aprovado: false, descartar: false, motivo: "", candidatas: [], escolhas: [],
    fotos_prontas: [], ia: [], pessoa_citada: null, ...extra,
  };
}

function corte(numero: number): Bloco {
  return { numero, titulo: `Corte ${numero}` } as Bloco;
}

function pedido(extra: Partial<Pedido> = {}): Pedido {
  return {
    id: "t1", episodio: "Ep 1", numero: 0, arquivo: "", volume_db: 0, estado: "na fila", mensagem: "",
    avisos: [], anterior: null, criado: 1, terminado: null, tipo: "fotos", cortes: [1, 2], progresso: "", ...extra,
  };
}

function resposta(corpo: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }),
  );
}

const EP = "/api/episodios/Ep%201";
let porCorte: Record<number, () => Promise<Response>>;
let resumo: any;
let orcamento: any;
let tarefasLista: Pedido[];
let tarefa: Pedido[];
let chamadas: { url: string; metodo: string }[];
let postFotos: () => Promise<Response>;
let confirmar: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  chamadas = [];
  porCorte = {
    1: () =>
      resposta({
        versao: "v1",
        momentos: [
          momento({ chave: "a", fotos_prontas: ["a.png", "a2.png"] }),
          momento({
            chave: "b",
            tipo: "ia",
            aprovado: true,
            ia: [{ arquivo: "b-v1.png", versao: 1, provedor: "openai", data: "" }],
          }),
          momento({ chave: "c", tipo: "ia", aprovado: true, ia: [] }),
          momento({ chave: "d", descartar: true, fotos_prontas: ["d.png"] }),
        ],
      }),
    2: () => resposta({ versao: "v1", momentos: [] }),
    3: () => resposta({ detail: "pedidos.json ilegível" }, 422),
  };
  resumo = { fotos: 1, megabytes: 1.54, origem: "Wikimedia Commons", avisos: ["tamanho desconhecido: a-2.jpg"] };
  orcamento = { imagens: 2, provedor: "openai", modelo: "gpt-image-1", custo_usd: 0.1 };
  tarefasLista = [];
  tarefa = [
    pedido({ estado: "montando", progresso: "Baixando 1 de 2" }),
    pedido({ estado: "pronto", mensagem: "2 fotos baixadas." }),
  ];
  postFotos = () => resposta(pedido(), 202);
  confirmar = vi.fn(() => true);
  vi.stubGlobal("confirm", confirmar);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      chamadas.push({ url, metodo });
      const m = url.match(/\/cortes\/(\d+)\/momentos$/);
      if (m) return porCorte[Number(m[1])]();
      if (url === `${EP}/fotos/resumo`) return resposta(resumo);
      if (url === `${EP}/ia/orcamento`) return resposta(orcamento);
      if (url === "/api/tarefas") return resposta(tarefasLista);
      if (url.startsWith("/api/tarefas/")) return resposta(tarefa.length > 1 ? tarefa.shift() : tarefa[0]);
      if (url === `${EP}/fotos` && metodo === "POST") return postFotos();
      return resposta({ detail: "?" }, 404);
    }),
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function avancar(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function montar(cortes = [corte(1), corte(2), corte(3)]) {
  render(
    <MemoryRouter>
      <ImagensDoEpisodio ep="Ep 1" cortes={cortes} />
    </MemoryRouter>,
  );
  await avancar(0);
  await avancar(0);
}

const linha = (n: number) => screen.getByRole("link", { name: new RegExp(`^${n}\\. `) }).closest("li")!;
const botaoFotos = () => screen.getByRole("button", { name: /^Baixar as fotos escolhidas/ });
const botaoIa = () => screen.getByRole("button", { name: /^Gerar as aprovadas/ });

describe("ImagensDoEpisodio", () => {
  it("mostra os números por corte, o corte vazio e o erro de um corte sem derrubar os outros", async () => {
    await montar();
    const l1 = linha(1);
    expect(within(l1).getByRole("link").getAttribute("href")).toBe("/episodios/Ep%201/cortes/1");
    expect(l1.textContent).toContain("3 momentos");
    expect(l1.textContent).toContain("2 fotos baixadas");
    expect(l1.textContent).toContain("2 prompts aprovados");
    expect(l1.textContent).toContain("1 imagem gerada");
    expect(linha(2).textContent).toContain("Sem momentos de imagem");
    expect(within(linha(3)).getByRole("alert").textContent).toBe("pedidos.json ilegível");
  });

  it("os botões do episódio mostram os totais e o de gerar fica desabilitado com 0 imagens", async () => {
    orcamento = { ...orcamento, imagens: 0, custo_usd: 0 };
    await montar();
    expect(botaoFotos().textContent).toBe("Baixar as fotos escolhidas (1 foto, 1,5 MB)");
    expect(botaoIa().textContent).toBe("Gerar as aprovadas (0 imagens, ~US$ 0,00)");
    expect((botaoIa() as HTMLButtonElement).disabled).toBe(true);
  });

  it("baixar confirma com o resumo do episódio, acompanha o pedido e recarrega o resumo", async () => {
    await montar();
    expect(botaoIa().textContent).toBe("Gerar as aprovadas (2 imagens, ~US$ 0,10)");
    fireEvent.click(botaoFotos());
    await avancar(0);
    expect(confirmar).toHaveBeenCalledTimes(1);
    const texto = confirmar.mock.calls[0][0] as string;
    expect(texto).toContain("Baixar 1 foto (1,5 MB) de Wikimedia Commons?");
    expect(texto).toContain("tamanho desconhecido: a-2.jpg");
    expect(texto).toContain("As fotos baixadas antes nestes cortes serão substituídas.");
    expect(chamadas.some((c) => c.url === `${EP}/fotos` && c.metodo === "POST")).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("Na fila");
    const antes = chamadas.filter((c) => c.url === `${EP}/fotos/resumo`).length;
    await avancar(2000);
    expect(screen.getByRole("status").textContent).toContain("Baixando 1 de 2");
    await avancar(2000);
    expect(screen.getByRole("status").textContent).toContain("Pronto");
    await avancar(0);
    expect(chamadas.filter((c) => c.url === `${EP}/fotos/resumo`).length).toBe(antes + 1);
  });

  it("recusar a confirmação não envia o pedido", async () => {
    confirmar.mockReturnValue(false);
    await montar();
    fireEvent.click(botaoIa());
    await avancar(0);
    expect(confirmar.mock.calls[0][0]).toBe("Gerar 2 imagens com openai (gpt-image-1), ~US$ 0,10?");
    expect(chamadas.some((c) => c.metodo === "POST")).toBe(false);
  });

  it("mostra o 409 do pedido repetido", async () => {
    postFotos = () => resposta({ detail: "Já há um pedido de fotos em andamento." }, 409);
    await montar();
    fireEvent.click(botaoFotos());
    await avancar(0);
    expect(screen.getByText("Já há um pedido de fotos em andamento.")).toBeTruthy();
  });

  it("ao abrir, retoma um pedido ativo de fotos do episódio", async () => {
    tarefasLista = [
      pedido({ id: "outro", episodio: "Ep 2", estado: "montando" }),
      pedido({ id: "t1", estado: "montando", progresso: "Baixando 1 de 2" }),
    ];
    await montar();
    expect(screen.getByRole("status").textContent).toContain("Baixando 1 de 2");
    expect((botaoFotos() as HTMLButtonElement).disabled).toBe(true);
    await avancar(2000);
    expect(chamadas.some((c) => c.url === "/api/tarefas/t1")).toBe(true);
  });
});
