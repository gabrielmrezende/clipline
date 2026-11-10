import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import type { Momento, Pedido } from "../api";
import { BlocoImagens } from "./BlocoImagens";

const BASE = "/api/episodios/Ep%201/cortes/2";

function candidata(k: number) {
  return {
    titulo: `Foto ${k}`,
    miniatura: `https://upload.example/thumb/${k}/320px-Foto${k}.jpg`,
    autor: `Autor ${k}`,
    licenca: "CC BY 4.0",
    pagina: null,
    largura: 800,
    altura: 600,
  };
}

function momento(extra: Partial<Momento> = {}): Momento {
  return {
    chave: "f1",
    inicio: 12.4,
    fim: 18,
    fala: "O ministro falou sobre a lula",
    tipo: "foto",
    nome: "lula",
    busca: "lula discurso",
    titulo: "",
    veiculo: "",
    data: "",
    prompt: "",
    aprovado: false,
    descartar: false,
    motivo: "",
    candidatas: [1, 2, 3, 4].map(candidata),
    escolhas: [],
    fotos_prontas: [],
    ia: [],
    pessoa_citada: null,
    ...extra,
  };
}

const FOTO = () => momento();
const IA = () =>
  momento({
    chave: "i1",
    inicio: 75,
    fim: 80,
    fala: "Uma sala vazia",
    tipo: "ia",
    candidatas: [],
    prompt: "uma sala vazia",
    aprovado: true,
    ia: [{ arquivo: "i1-v1.png", versao: 1, provedor: "openai", data: "2026-11-08" }],
  });
const NOTICIA = () =>
  momento({
    chave: "n1",
    inicio: 40,
    tipo: "noticia",
    candidatas: [],
    titulo: "Câmara aprova o projeto",
    veiculo: "Agência X",
    fotos_prontas: ["n1.png"],
  });

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
    tipo: "fotos",
    cortes: [2],
    progresso: "",
    ...extra,
  };
}

function resposta(corpo: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }),
  );
}

interface Chamada {
  url: string;
  metodo: string;
  corpo: any;
}
let chamadas: Chamada[];
let momentos: Momento[];
let versao: number;
let resumo: any;
let orcamento: any;
let config: any;
let tarefasLista: Pedido[];
let tarefa: Pedido[];
let putExtra: (chave: string, corpo: any) => Promise<Response> | null;
let postFotos: () => Promise<Response>;
let postIa: () => Promise<Response>;
let confirmar: ReturnType<typeof vi.fn>;

function aplicar(m: Momento, c: any) {
  if (c.tipo !== undefined && c.tipo !== m.tipo) {
    m.tipo = c.tipo;
    m.aprovado = false;
  }
  if (c.escolhas !== undefined) m.escolhas = c.escolhas;
  if (c.prompt !== undefined && c.prompt !== m.prompt) {
    m.prompt = c.prompt;
    m.aprovado = false;
  }
  if (c.aprovado !== undefined) m.aprovado = c.aprovado;
  if (c.descartar !== undefined) m.descartar = c.descartar;
}

beforeEach(() => {
  vi.useFakeTimers();
  chamadas = [];
  momentos = [FOTO(), IA(), NOTICIA()];
  versao = 1;
  resumo = { fotos: 2, megabytes: 1.54, origem: "Wikimedia Commons", avisos: ["tamanho desconhecido: f1-2.jpg"] };
  orcamento = { imagens: 2, provedor: "openai", modelo: "gpt-image-1", custo_usd: 0.1 };
  config = {
    provedor: "openai",
    provedores: { openai: { modelo: "gpt-image-1", qualidade: "low", preco_usd: 0.05 } },
    chaves: { openai: true },
  };
  tarefasLista = [];
  tarefa = [pedido({ estado: "montando", progresso: "Baixando 1 de 2" })];
  putExtra = () => null;
  postFotos = () => resposta(pedido(), 202);
  postIa = () => resposta(pedido({ tipo: "ia" }), 202);
  confirmar = vi.fn(() => true);
  vi.stubGlobal("confirm", confirmar);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      chamadas.push({ url, metodo, corpo: init?.body ? JSON.parse(String(init.body)) : null });
      const corpo = init?.body ? JSON.parse(String(init.body)) : null;
      if (url === `${BASE}/momentos`) return resposta({ versao: `v${versao}`, momentos });
      const mom = url.match(/\/momentos\/([^/]+)$/);
      if (mom && metodo === "PUT") {
        const extra = putExtra(decodeURIComponent(mom[1]), corpo);
        if (extra) return extra;
        const m = momentos.find((x) => x.chave === decodeURIComponent(mom[1]))!;
        aplicar(m, corpo);
        versao += 1;
        return resposta({ momento: m, versao: `v${versao}` });
      }
      if (url.endsWith("/fotos/resumo")) return resposta(resumo);
      if (url.endsWith("/ia/orcamento")) return resposta(orcamento);
      if (url === "/api/configuracoes/imagens") return resposta(config);
      if (url === "/api/tarefas") return resposta(tarefasLista);
      if (url.startsWith("/api/tarefas/"))
        return resposta(tarefa.length > 1 ? tarefa.shift() : tarefa[0]);
      if (url === `${BASE}/fotos` && metodo === "POST") return postFotos();
      if (url === `${BASE}/ia` && metodo === "POST") return postIa();
      if (url.endsWith("/ia") && metodo === "POST") return postIa();
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

async function montar(irPara = vi.fn()) {
  const r = render(<BlocoImagens ep="Ep 1" n={2} irPara={irPara} />);
  await avancar(0);
  await avancar(0);
  return { ...r, irPara };
}

const candidataBtn = (k: number) => screen.getByRole("button", { name: new RegExp(`^Candidata ${k}\\b`) });
const puts = () => chamadas.filter((c) => c.metodo === "PUT");
const botaoFotos = () => screen.getByRole("button", { name: /^Baixar as fotos escolhidas/ });
const botaoIa = () => screen.getByRole("button", { name: /^Gerar as aprovadas/ });

describe("BlocoImagens", () => {
  it("lista um cartão por momento em ordem de tempo, com tempo e fala", async () => {
    momentos = [IA(), NOTICIA(), FOTO()];
    await montar();
    const tempos = screen.getAllByTestId("tempo-momento").map((e) => e.textContent);
    expect(tempos).toEqual(["0:12", "0:40", "1:15"]);
    expect(screen.getAllByText("O ministro falou sobre a lula").length).toBeGreaterThan(0);
  });

  it("o botão ▶ chama irPara com o início do momento", async () => {
    const { irPara } = await montar();
    fireEvent.click(screen.getByRole("button", { name: "Ir para 1:15" }));
    expect(irPara).toHaveBeenCalledWith(75);
  });

  it("escolhas na ordem 3, 1 numeram 1 e 2, e clicar de novo tira a escolha", async () => {
    await montar();
    fireEvent.click(candidataBtn(3));
    await avancar(0);
    fireEvent.click(candidataBtn(1));
    await avancar(0);
    expect(puts().map((c) => c.corpo)).toEqual([
      { versao: "v1", escolhas: [3] },
      { versao: "v2", escolhas: [3, 1] },
    ]);
    expect(within(candidataBtn(3)).getByText("1")).toBeTruthy();
    expect(within(candidataBtn(1)).getByText("2")).toBeTruthy();
    fireEvent.click(candidataBtn(3));
    await avancar(0);
    expect(puts()[2].corpo).toEqual({ versao: "v3", escolhas: [1] });
    expect(within(candidataBtn(1)).getByText("1")).toBeTruthy();
  });

  it("cliques seguidos, sem esperar a resposta, mandam versões em sequência", async () => {
    await montar();
    fireEvent.click(candidataBtn(2));
    fireEvent.click(candidataBtn(4));
    await avancar(0);
    await avancar(0);
    expect(puts().map((c) => c.corpo)).toEqual([
      { versao: "v1", escolhas: [2] },
      { versao: "v2", escolhas: [2, 4] },
    ]);
  });

  it("com 3 escolhidas, as outras candidatas ficam desabilitadas", async () => {
    momentos = [momento({ escolhas: [1, 2, 3] })];
    await montar();
    expect((candidataBtn(4) as HTMLButtonElement).disabled).toBe(true);
    expect((candidataBtn(3) as HTMLButtonElement).disabled).toBe(false);
  });

  it("mostra a miniatura, o autor e a licença, e Pronta na posição baixada", async () => {
    momentos = [momento({ escolhas: [2], fotos_prontas: ["f1-1.jpg"] })];
    const { container } = await montar();
    const img = container.querySelector("img[loading=lazy]") as HTMLImageElement;
    expect(img.getAttribute("src")).toBe("https://upload.example/thumb/1/320px-Foto1.jpg");
    expect(screen.getByText(/Autor 1/)).toBeTruthy();
    expect(screen.getAllByText(/CC BY 4.0/).length).toBe(4);
    expect(screen.getAllByText("Pronta")).toHaveLength(1);
  });

  it("Buscar outras vem preenchido e manda a busca nova", async () => {
    momentos = [momento()];
    await montar();
    const campo = screen.getByLabelText("Buscar outras") as HTMLInputElement;
    expect(campo.value).toBe("lula discurso");
    fireEvent.change(campo, { target: { value: "lula posse" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await avancar(0);
    const c = chamadas.find((x) => x.url.endsWith("/momentos/f1/buscar"))!;
    expect(c.metodo).toBe("POST");
    expect(c.corpo).toEqual({ busca: "lula posse" });
  });

  it("editar o prompt desmarca Aprovado na hora e grava ao sair do campo", async () => {
    momentos = [IA()];
    await montar();
    const aprovado = screen.getByLabelText("Aprovado") as HTMLInputElement;
    expect(aprovado.checked).toBe(true);
    const prompt = screen.getByLabelText("Prompt") as HTMLTextAreaElement;
    fireEvent.change(prompt, { target: { value: "uma sala cheia" } });
    expect(aprovado.checked).toBe(false);
    fireEvent.blur(prompt);
    await avancar(0);
    expect(puts().map((c) => c.corpo)).toEqual([{ versao: "v1", prompt: "uma sala cheia" }]);
    expect((screen.getByLabelText("Aprovado") as HTMLInputElement).checked).toBe(false);
  });

  it("marcar Aprovado manda aprovado: true", async () => {
    momentos = [momento({ ...IA(), aprovado: false })];
    await montar();
    fireEvent.click(screen.getByLabelText("Aprovado"));
    await avancar(0);
    expect(puts().map((c) => c.corpo)).toEqual([{ versao: "v1", aprovado: true }]);
  });

  it("com pessoa citada, mostra o aviso e desabilita Aprovado", async () => {
    momentos = [momento({ ...IA(), aprovado: false, pessoa_citada: "Lula" })];
    await montar();
    expect(screen.getByText("Cita pessoa real (Lula): não pode gerar")).toBeTruthy();
    expect((screen.getByLabelText("Aprovado") as HTMLInputElement).disabled).toBe(true);
  });

  it("mostra as versões geradas com provedor e data", async () => {
    momentos = [IA()];
    const { container } = await montar();
    expect(screen.getByText(/openai/)).toBeTruthy();
    expect(screen.getByText(/2026-11-08/)).toBeTruthy();
    const img = container.querySelector(`img[src="${BASE}/imagens/i1-v1.png"]`);
    expect(img).toBeTruthy();
  });

  it("notícia mostra título, veículo e imagem pronta, sem trocar de tipo", async () => {
    momentos = [NOTICIA()];
    const { container } = await montar();
    expect(screen.getByText("Câmara aprova o projeto")).toBeTruthy();
    expect(screen.getByText(/Agência X/)).toBeTruthy();
    expect(container.querySelector(`img[src="${BASE}/imagens/n1.png"]`)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Trocar para/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Descartar" })).toBeTruthy();
  });

  it("Trocar para IA manda tipo; Descartar e Restaurar mandam descartar", async () => {
    momentos = [FOTO()];
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Trocar para IA" }));
    await avancar(0);
    expect(puts()[0].corpo).toEqual({ versao: "v1", tipo: "ia" });
    expect(screen.getByRole("button", { name: "Trocar para foto" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Descartar" }));
    await avancar(0);
    expect(puts()[1].corpo).toEqual({ versao: "v2", descartar: true });
    fireEvent.click(screen.getByRole("button", { name: "Restaurar" }));
    await avancar(0);
    expect(puts()[2].corpo).toEqual({ versao: "v3", descartar: false });
  });

  it("um 409 no PUT recarrega os momentos e avisa", async () => {
    let primeira = true;
    putExtra = () => {
      if (!primeira) return null;
      primeira = false;
      momentos = [momento({ escolhas: [4] })];
      versao = 7;
      return resposta({ detail: "O pedidos.json mudou desde que você abriu.", versao_atual: "v7" }, 409);
    };
    await montar();
    fireEvent.click(candidataBtn(1));
    await avancar(0);
    await avancar(0);
    expect(screen.getByText("O pedidos.json mudou desde que você abriu.")).toBeTruthy();
    expect(within(candidataBtn(4)).getByText("1")).toBeTruthy();
    expect(within(candidataBtn(1)).queryByText("1")).toBeNull();
    fireEvent.click(candidataBtn(2));
    await avancar(0);
    expect(puts()[1].corpo).toEqual({ versao: "v7", escolhas: [4, 2] });
  });

  it("um 422 no PUT mostra o detail perto do cartão", async () => {
    putExtra = () => resposta({ detail: "Escolha fora da faixa." }, 422);
    await montar();
    fireEvent.click(candidataBtn(1));
    await avancar(0);
    await avancar(0);
    expect(screen.getByText("Escolha fora da faixa.")).toBeTruthy();
  });

  it("o rótulo de Baixar usa o resumo e Gerar usa o orçamento", async () => {
    await montar();
    expect(botaoFotos().textContent).toBe("Baixar as fotos escolhidas (2 fotos, 1,5 MB)");
    expect(botaoIa().textContent).toBe("Gerar as aprovadas (2 imagens, ~US$ 0,10)");
  });

  it("usa singular com 1 foto e 1 imagem", async () => {
    resumo = { ...resumo, fotos: 1 };
    orcamento = { ...orcamento, imagens: 1, custo_usd: 0.05 };
    await montar();
    expect(botaoFotos().textContent).toBe("Baixar as fotos escolhidas (1 foto, 1,5 MB)");
    expect(botaoIa().textContent).toBe("Gerar as aprovadas (1 imagem, ~US$ 0,05)");
  });

  it("recarrega o resumo e o orçamento, com espera curta, depois de uma mudança", async () => {
    await montar();
    const antes = chamadas.filter((c) => c.url.endsWith("/fotos/resumo")).length;
    resumo = { ...resumo, fotos: 3 };
    fireEvent.click(candidataBtn(1));
    fireEvent.click(candidataBtn(2));
    await avancar(0);
    await avancar(0);
    expect(chamadas.filter((c) => c.url.endsWith("/fotos/resumo")).length).toBe(antes);
    await avancar(1000);
    expect(chamadas.filter((c) => c.url.endsWith("/fotos/resumo")).length).toBe(antes + 1);
    expect(botaoFotos().textContent).toBe("Baixar as fotos escolhidas (3 fotos, 1,5 MB)");
  });

  it("Baixar confirma com o resumo e a frase de substituição, e envia", async () => {
    await montar();
    fireEvent.click(botaoFotos());
    await avancar(0);
    await avancar(0);
    const texto = String(confirmar.mock.calls[0][0]);
    expect(texto).toContain("2 fotos");
    expect(texto).toContain("1,5 MB");
    expect(texto).toContain("Wikimedia Commons");
    expect(texto).toContain("tamanho desconhecido: f1-2.jpg");
    expect(texto).toContain("As fotos baixadas antes neste corte serão substituídas.");
    expect(chamadas.filter((c) => c.metodo === "POST" && c.url === `${BASE}/fotos`)).toHaveLength(1);
  });

  it("Baixar com confirm falso não envia nada", async () => {
    confirmar.mockReturnValue(false);
    await montar();
    fireEvent.click(botaoFotos());
    await avancar(0);
    await avancar(0);
    expect(confirmar).toHaveBeenCalled();
    expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(0);
  });

  it("Gerar as aprovadas confirma com o orçamento; com confirm falso, nada é enviado", async () => {
    confirmar.mockReturnValue(false);
    await montar();
    fireEvent.click(botaoIa());
    await avancar(0);
    await avancar(0);
    const texto = String(confirmar.mock.calls[0][0]);
    expect(texto).toContain("2 imagens");
    expect(texto).toContain("openai");
    expect(texto).toContain("gpt-image-1");
    expect(texto).toContain("~US$ 0,10");
    expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(0);
    confirmar.mockReturnValue(true);
    fireEvent.click(botaoIa());
    await avancar(0);
    await avancar(0);
    expect(chamadas.filter((c) => c.metodo === "POST" && c.url === `${BASE}/ia`)).toHaveLength(1);
  });

  it("Gerar as aprovadas fica desabilitado com 0 imagens", async () => {
    orcamento = { ...orcamento, imagens: 0, custo_usd: 0 };
    await montar();
    expect(botaoIa().textContent).toBe("Gerar as aprovadas (0 imagens, ~US$ 0,00)");
    expect((botaoIa() as HTMLButtonElement).disabled).toBe(true);
  });

  it("Gerar de novo confirma com 1 imagem e o preço do provedor", async () => {
    momentos = [IA()];
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Gerar de novo" }));
    expect(String(confirmar.mock.calls[0][0])).toContain("1 imagem, ~US$ 0,05");
    await avancar(0);
    expect(chamadas.filter((c) => c.metodo === "POST" && c.url.endsWith("/momentos/i1/ia"))).toHaveLength(1);
  });

  it("Gerar de novo com confirm falso não envia", async () => {
    confirmar.mockReturnValue(false);
    momentos = [IA()];
    await montar();
    fireEvent.click(screen.getByRole("button", { name: "Gerar de novo" }));
    await avancar(0);
    expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(0);
  });

  it("mostra Na fila, depois o progresso, e ao terminar recarrega os momentos", async () => {
    tarefa = [
      pedido({ estado: "montando", progresso: "Baixando 1 de 2" }),
      pedido({ estado: "pronto", mensagem: "2 fotos baixadas.", avisos: ["f1-2.jpg: sem licença"] }),
    ];
    await montar();
    fireEvent.click(botaoFotos());
    await avancar(0);
    await avancar(0);
    expect(screen.getByText("Na fila")).toBeTruthy();
    expect((botaoFotos() as HTMLButtonElement).disabled).toBe(true);
    await avancar(2000);
    expect(screen.getByText("Baixando 1 de 2")).toBeTruthy();
    const leituras = chamadas.filter((c) => c.url === `${BASE}/momentos`).length;
    momentos = [momento({ escolhas: [1], fotos_prontas: ["f1-1.jpg"] })];
    await avancar(2000);
    expect(screen.getByText("Pronto")).toBeTruthy();
    expect(screen.getByText("2 fotos baixadas.")).toBeTruthy();
    expect(screen.getByText(/f1-2.jpg: sem licença/)).toBeTruthy();
    expect(chamadas.filter((c) => c.url === `${BASE}/momentos`).length).toBe(leituras + 1);
    expect(screen.getAllByText("Pronta")).toHaveLength(1);
    const consultas = chamadas.filter((c) => c.url.startsWith("/api/tarefas/")).length;
    await avancar(6000);
    expect(chamadas.filter((c) => c.url.startsWith("/api/tarefas/")).length).toBe(consultas);
  });

  it("mostra Baixando… enquanto o progresso está vazio", async () => {
    tarefa = [pedido({ estado: "montando", progresso: "" })];
    await montar();
    fireEvent.click(botaoFotos());
    await avancar(0);
    await avancar(0);
    await avancar(2000);
    expect(screen.getByText("Baixando…")).toBeTruthy();
  });

  it("mostra o erro do pedido e não repete sozinho", async () => {
    tarefa = [pedido({ estado: "erro", mensagem: "Wikimedia fora do ar" })];
    await montar();
    fireEvent.click(botaoFotos());
    await avancar(0);
    await avancar(0);
    await avancar(2000);
    expect(screen.getByText("Erro: Wikimedia fora do ar")).toBeTruthy();
    await avancar(10000);
    expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(1);
  });

  it("o 409 de fotos em andamento mostra o detail do servidor", async () => {
    postFotos = () => resposta({ detail: "Já há um pedido de fotos em andamento para este corte." }, 409);
    await montar();
    fireEvent.click(botaoFotos());
    await avancar(0);
    await avancar(0);
    expect(screen.getByText("Já há um pedido de fotos em andamento para este corte.")).toBeTruthy();
  });

  it("retoma o acompanhamento de um pedido ativo de IA deste corte ao abrir", async () => {
    tarefasLista = [
      pedido({ id: "outro", cortes: [5], estado: "montando" }),
      pedido({ id: "t9", tipo: "ia", cortes: [2], estado: "montando", progresso: "Gerando 1 de 2" }),
    ];
    tarefa = [pedido({ id: "t9", tipo: "ia", estado: "montando", progresso: "Gerando 1 de 2" })];
    await montar();
    expect(screen.getByText("Gerando 1 de 2")).toBeTruthy();
    expect((botaoIa() as HTMLButtonElement).disabled).toBe(true);
    await avancar(2000);
    expect(chamadas.some((c) => c.url === "/api/tarefas/t9")).toBe(true);
  });

  it("sem momentos, avisa a tela e não desenha nada", async () => {
    momentos = [];
    const aoCarregar = vi.fn();
    const { container } = render(<BlocoImagens ep="Ep 1" n={2} irPara={vi.fn()} aoCarregar={aoCarregar} />);
    await avancar(0);
    await avancar(0);
    expect(aoCarregar).toHaveBeenLastCalledWith(false);
    expect(container.textContent).toBe("");
  });

  it("com erro de leitura, mostra a mensagem e avisa a tela que não há momentos", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => resposta({ detail: "pedidos.json ilegível: x" }, 422)),
    );
    const aoCarregar = vi.fn();
    render(<BlocoImagens ep="Ep 1" n={2} irPara={vi.fn()} aoCarregar={aoCarregar} />);
    await avancar(0);
    await avancar(0);
    expect(screen.getByText("pedidos.json ilegível: x")).toBeTruthy();
    expect(aoCarregar).toHaveBeenLastCalledWith(false);
  });

  it("com momentos, avisa a tela com true", async () => {
    const aoCarregar = vi.fn();
    render(<BlocoImagens ep="Ep 1" n={2} irPara={vi.fn()} aoCarregar={aoCarregar} />);
    await avancar(0);
    await avancar(0);
    expect(aoCarregar).toHaveBeenLastCalledWith(true);
  });
});
