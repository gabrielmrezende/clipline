import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { BlocoMusica } from "./BlocoMusica";

const LISTA = {
  do_episodio: [
    {
      arquivo: "leve/Sunshine A.mp3",
      titulo: "Sunshine A",
      clima: "leve",
      duracao: 120,
      motivo: "combina com o tema",
    },
  ],
  biblioteca: {
    leve: [
      { arquivo: "leve/Sunshine A.mp3", titulo: "Sunshine A", duracao: 120 },
      { arquivo: "leve/Brisa.mp3", titulo: "Brisa", duracao: 90 },
    ],
    tenso: [{ arquivo: "tenso/Sombra.mp3", titulo: "Sombra", duracao: 100 }],
  },
  avisos: [],
};

function pedido(extra: object = {}) {
  return {
    id: "t1",
    episodio: "Ep 1",
    numero: 2,
    arquivo: "leve/Brisa.mp3",
    volume_db: -26,
    estado: "na fila",
    mensagem: "",
    avisos: [],
    anterior: null,
    criado: "x",
    terminado: null,
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
let musicaDoCorte: any;
let tarefas: any[];
let respostaPost: () => Promise<Response>;
let respostaPrevia: () => Promise<Response>;
let tempo = 0;
let play: ReturnType<typeof vi.fn>;
let pause: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  chamadas = [];
  tempo = 0;
  musicaDoCorte = { atual: null, anterior: null, pedido: null };
  tarefas = [];
  respostaPost = () => resposta(pedido(), 202);
  respostaPrevia = () => Promise.resolve(new Response(new Blob(["x"]), { status: 200 }));
  play = vi.fn(() => Promise.resolve());
  pause = vi.fn();
  HTMLMediaElement.prototype.play = play as any;
  HTMLMediaElement.prototype.pause = pause as any;
  (URL as any).createObjectURL = vi.fn(() => "blob:previa");
  (URL as any).revokeObjectURL = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      chamadas.push({ url, metodo, corpo: init?.body ? JSON.parse(String(init.body)) : null });
      if (url.endsWith("/musicas")) return resposta(LISTA);
      if (url.endsWith("/musica/previa")) return respostaPrevia();
      if (url.endsWith("/musica") && metodo === "POST") return respostaPost();
      if (url.endsWith("/musica")) return resposta(musicaDoCorte);
      if (url.startsWith("/api/tarefas/"))
        return resposta(tarefas.length > 1 ? tarefas.shift() : tarefas[0]);
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

interface PropsTeste {
  videoFinal?: string[];
  aoTerminar?: () => void;
  soltarVideo?: () => void;
  aoMudarAndamento?: (ativo: boolean) => void;
}

async function montar(props: PropsTeste = {}) {
  const aoTerminar = props.aoTerminar ?? vi.fn();
  const r = render(
    <BlocoMusica
      ep="Ep 1"
      n={2}
      videoFinal={props.videoFinal ?? []}
      tempoDoPlayer={() => tempo}
      aoTerminar={aoTerminar}
      soltarVideo={props.soltarVideo}
      aoMudarAndamento={props.aoMudarAndamento}
    />,
  );
  await avancar(0);
  return { ...r, aoTerminar };
}

const escolher = (titulo: string) =>
  fireEvent.click(screen.getAllByRole("button", { name: `Escolher ${titulo}` })[0]);

const botaoMontar = () => screen.getByRole("button", { name: "Montar com esta música" });

describe("BlocoMusica", () => {
  it("mostra Do episódio com o motivo, antes de Biblioteca", async () => {
    await montar();
    const doEp = screen.getByText("Do episódio");
    const biblio = screen.getByText("Biblioteca");
    expect(screen.getByText(/combina com o tema/)).toBeTruthy();
    expect(doEp.compareDocumentPosition(biblio) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("mostra a música atual com o volume e a anterior", async () => {
    musicaDoCorte = {
      atual: { arquivo: "leve/Brisa.mp3", titulo: "Brisa", volume_db: -24 },
      anterior: { arquivo: "x/y.mp3", titulo: "Velha", volume_db: -20 },
      pedido: null,
    };
    await montar();
    expect(screen.getByText("Brisa · -24 dB")).toBeTruthy();
    expect(screen.getByText("Música anterior: Velha, volume -20 dB")).toBeTruthy();
    expect((screen.getByLabelText(/Volume/) as HTMLInputElement).value).toBe("-24");
  });

  it("tocar uma faixa e depois outra deixa um só áudio tocando", async () => {
    const { container } = await montar();
    fireEvent.click(screen.getAllByRole("button", { name: "Ouvir Sunshine A" })[0]);
    const audio = () => container.querySelector("audio")!;
    expect(container.querySelectorAll("audio")).toHaveLength(1);
    expect(audio().getAttribute("src")).toBe("/api/musicas/leve/Sunshine%20A.mp3");
    expect(play).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getAllByRole("button", { name: "Ouvir Brisa" })[0]);
    expect(container.querySelectorAll("audio")).toHaveLength(1);
    expect(audio().getAttribute("src")).toBe("/api/musicas/leve/Brisa.mp3");
    expect(pause).toHaveBeenCalled();
    expect(play).toHaveBeenCalledTimes(2);
  });

  it("o volume vai de -30 a -18 e mostra o valor em dB", async () => {
    await montar();
    const barra = screen.getByLabelText(/Volume/) as HTMLInputElement;
    expect(barra.min).toBe("-30");
    expect(barra.max).toBe("-18");
    expect(barra.step).toBe("1");
    expect(screen.getByText("-26 dB")).toBeTruthy();
    expect(screen.getByText("mais baixa")).toBeTruthy();
    expect(screen.getByText("mais alta")).toBeTruthy();
    fireEvent.change(barra, { target: { value: "-20" } });
    expect(screen.getByText("-20 dB")).toBeTruthy();
  });

  it("a prévia manda o tempo do player e mostra a partir de", async () => {
    const { container } = await montar();
    escolher("Brisa");
    tempo = 42;
    fireEvent.click(screen.getByRole("button", { name: "Ouvir prévia (15 s)" }));
    await avancar(0);
    const c = chamadas.find((x) => x.url.endsWith("/musica/previa"))!;
    expect(c.metodo).toBe("POST");
    expect(c.corpo).toEqual({ arquivo: "leve/Brisa.mp3", volume_db: -26, inicio: 42 });
    expect(screen.getByText(/a partir de 0:42/)).toBeTruthy();
    expect(container.querySelector("audio")!.getAttribute("src")).toBe("blob:previa");
    expect(play).toHaveBeenCalled();
  });

  it("mostra o motivo quando a prévia falha", async () => {
    respostaPrevia = () => resposta({ detail: "Não consegui gerar a prévia: ffmpeg" }, 422);
    await montar();
    escolher("Brisa");
    fireEvent.click(screen.getByRole("button", { name: "Ouvir prévia (15 s)" }));
    await avancar(0);
    expect(screen.getByText("Não consegui gerar a prévia: ffmpeg")).toBeTruthy();
  });

  it("com vídeo final pede confirmação com o texto da spec", async () => {
    const texto =
      "Este corte já tem vídeo final. O vídeo final não muda; você vai precisar refazer no CapCut. Montar mesmo assim?";
    const confirmar = vi.fn(() => false);
    vi.stubGlobal("confirm", confirmar);
    await montar({ videoFinal: ["a.mp4"] });
    escolher("Brisa");
    fireEvent.click(botaoMontar());
    await avancar(0);
    expect(confirmar).toHaveBeenCalledWith(texto);
    expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(0);
    confirmar.mockReturnValue(true);
    fireEvent.click(botaoMontar());
    await avancar(0);
    expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(1);
  });

  it("acompanha o pedido até pronto e chama aoTerminar uma vez", async () => {
    tarefas = [
      pedido({ estado: "montando" }),
      pedido({ estado: "pronto", avisos: ["crédito não atualizado: x"], terminado: "t" }),
    ];
    const { aoTerminar } = await montar();
    escolher("Brisa");
    fireEvent.click(botaoMontar());
    await avancar(0);
    const post = chamadas.find((c) => c.metodo === "POST" && c.url.endsWith("/musica"))!;
    expect(post.corpo).toEqual({ arquivo: "leve/Brisa.mp3", volume_db: -26 });
    expect(screen.getByText("Na fila")).toBeTruthy();
    expect((botaoMontar() as HTMLButtonElement).disabled).toBe(true);
    await avancar(2000);
    expect(screen.getByText("Montando…")).toBeTruthy();
    expect(aoTerminar).not.toHaveBeenCalled();
    await avancar(2000);
    expect(screen.getByText("Pronto: o corte.mp4 foi atualizado.")).toBeTruthy();
    expect(screen.getByText(/crédito não atualizado: x/)).toBeTruthy();
    expect(aoTerminar).toHaveBeenCalledTimes(1);
    const antes = chamadas.length;
    await avancar(6000);
    expect(chamadas.filter((c) => c.url.startsWith("/api/tarefas/"))).toHaveLength(2);
    expect(chamadas.length).toBe(antes);
    expect(aoTerminar).toHaveBeenCalledTimes(1);
  });

  it("retoma o acompanhamento de um pedido ativo ao abrir", async () => {
    musicaDoCorte = { atual: null, anterior: null, pedido: pedido({ estado: "montando" }) };
    tarefas = [pedido({ estado: "montando" })];
    await montar();
    expect(screen.getByText("Montando…")).toBeTruthy();
    expect((botaoMontar() as HTMLButtonElement).disabled).toBe(true);
    await avancar(2000);
    expect(chamadas.some((c) => c.url === "/api/tarefas/t1")).toBe(true);
  });

  it("mostra o erro e Tentar de novo reenvia o mesmo pedido", async () => {
    tarefas = [pedido({ estado: "erro", mensagem: "ffmpeg quebrou", volume_db: -22 })];
    await montar();
    escolher("Brisa");
    fireEvent.change(screen.getByLabelText(/Volume/), { target: { value: "-22" } });
    fireEvent.click(botaoMontar());
    await avancar(0);
    await avancar(2000);
    expect(screen.getByText("Erro: ffmpeg quebrou")).toBeTruthy();
    respostaPost = () => resposta(pedido({ volume_db: -22 }), 202);
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    await avancar(0);
    const posts = chamadas.filter((c) => c.metodo === "POST");
    expect(posts).toHaveLength(2);
    expect(posts[1].corpo).toEqual({ arquivo: "leve/Brisa.mp3", volume_db: -22 });
  });

  it("solta o vídeo do corte antes do POST e avisa o andamento", async () => {
    const postsAoSoltar: number[] = [];
    const soltarVideo = vi.fn(() => {
      postsAoSoltar.push(chamadas.filter((c) => c.metodo === "POST").length);
    });
    const aoMudarAndamento = vi.fn();
    tarefas = [pedido({ estado: "montando" }), pedido({ estado: "pronto", terminado: 2 })];
    await montar({ soltarVideo, aoMudarAndamento });
    expect(aoMudarAndamento).toHaveBeenLastCalledWith(false);
    escolher("Brisa");
    fireEvent.click(botaoMontar());
    expect(soltarVideo).toHaveBeenCalledTimes(1);
    expect(postsAoSoltar).toEqual([0]);
    expect(chamadas.filter((c) => c.metodo === "POST")).toHaveLength(1);
    await avancar(0);
    expect(aoMudarAndamento).toHaveBeenLastCalledWith(true);
    await avancar(2000);
    expect(aoMudarAndamento).toHaveBeenLastCalledWith(true);
    await avancar(2000);
    expect(screen.getByText("Pronto: o corte.mp4 foi atualizado.")).toBeTruthy();
    expect(aoMudarAndamento).toHaveBeenLastCalledWith(false);
  });

  it("POST recusado devolve o vídeo do corte", async () => {
    respostaPost = () => resposta({ detail: "Este corte já está sendo montado." }, 409);
    const aoMudarAndamento = vi.fn();
    await montar({ soltarVideo: vi.fn(), aoMudarAndamento });
    escolher("Brisa");
    fireEvent.click(botaoMontar());
    await avancar(0);
    expect(screen.getByText("Este corte já está sendo montado.")).toBeTruthy();
    expect(aoMudarAndamento).toHaveBeenLastCalledWith(false);
  });

  it("cancelar a confirmação não solta o vídeo", async () => {
    vi.stubGlobal("confirm", vi.fn(() => false));
    const soltarVideo = vi.fn();
    await montar({ videoFinal: ["a.mp4"], soltarVideo });
    escolher("Brisa");
    fireEvent.click(botaoMontar());
    await avancar(0);
    expect(soltarVideo).not.toHaveBeenCalled();
  });

  it("mostra o detail do 409", async () => {
    respostaPost = () => resposta({ detail: "Este corte já está sendo montado." }, 409);
    await montar();
    escolher("Brisa");
    fireEvent.click(botaoMontar());
    await avancar(0);
    expect(screen.getByText("Este corte já está sendo montado.")).toBeTruthy();
  });
});
