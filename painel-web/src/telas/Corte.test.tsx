import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";
import { Corte } from "./Corte";

const BASE = "/api/episodios/Ep%201/cortes/2";

function bloco(extra: object = {}) {
  return {
    numero: 2,
    titulo: "Segundo",
    pasta: "02-segundo",
    clima: "leve",
    instagram: false,
    redes: ["youtube", "tiktok"],
    data: "",
    musica: "Velha",
    antes: "",
    depois: "",
    alertas: [],
    video_final: [],
    tem_guia: false,
    erro: null,
    avisos_post: [],
    video_final_desatualizado: false,
    montando: false,
    selo: "sem vídeo final",
    ...extra,
  };
}

function pedido(extra: object = {}) {
  return {
    id: "t1",
    episodio: "Ep 1",
    numero: 2,
    arquivo: "leve/Brisa.mp3",
    volume_db: -26,
    estado: "montando",
    mensagem: "",
    avisos: [],
    anterior: null,
    criado: 1,
    terminado: null,
    ...extra,
  };
}

const POST = {
  campos: { youtube_titulo: "T", youtube_descricao: "D", instagram: "I", tiktok: "K" },
  somente_leitura: {},
  credito: null,
  redes: ["youtube", "tiktok"],
  versao: "v1",
  avisos: [],
  erro: null,
};

const LISTA = {
  do_episodio: [],
  biblioteca: { leve: [{ arquivo: "leve/Brisa.mp3", titulo: "Brisa", duracao: 90 }] },
  avisos: [],
};

function resposta(corpo: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }),
  );
}

let detalhes: any[];
let musicaDoCorte: any;
let tarefas: any[];
let urls: string[];

beforeEach(() => {
  vi.useFakeTimers();
  urls = [];
  detalhes = [{ bloco: bloco(), guia: null, imagens: [] }];
  musicaDoCorte = { atual: { arquivo: "leve/Velha.mp3", titulo: "Velha", volume_db: -26 }, anterior: null, pedido: null };
  tarefas = [];
  HTMLMediaElement.prototype.pause = vi.fn();
  HTMLMediaElement.prototype.load = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      urls.push(`${metodo} ${url}`);
      if (url === BASE) return resposta(detalhes.length > 1 ? detalhes.shift() : detalhes[0]);
      if (url.endsWith("/musicas")) return resposta(LISTA);
      if (url.endsWith("/musica") && metodo === "POST") return resposta(pedido({ estado: "na fila" }), 202);
      if (url.endsWith("/musica")) return resposta(musicaDoCorte);
      if (url.endsWith("/post")) return resposta(POST);
      if (url.startsWith("/api/tarefas/")) return resposta(tarefas.length > 1 ? tarefas.shift() : tarefas[0]);
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

async function abrir() {
  const r = render(
    <MemoryRouter initialEntries={["/episodios/Ep%201/cortes/2"]}>
      <Routes>
        <Route path="/episodios/:ep/cortes/:n" element={<Corte />} />
      </Routes>
    </MemoryRouter>,
  );
  await avancar(0);
  await avancar(0);
  return r;
}

describe("Corte", () => {
  it("com pedido ativo, não há <video> do corte e aparece Montando o corte…", async () => {
    musicaDoCorte = { ...musicaDoCorte, pedido: pedido() };
    tarefas = [pedido()];
    const { container } = await abrir();
    expect(container.querySelector("video")).toBeNull();
    expect(screen.getByText("Montando o corte…")).toBeTruthy();
  });

  it("Montar descarrega o vídeo do corte antes do POST e o tira da tela", async () => {
    tarefas = [pedido()];
    const { container } = await abrir();
    const video = container.querySelector("video")!;
    expect(video.getAttribute("src")).toBe(`${BASE}/video`);
    fireEvent.click(screen.getByRole("button", { name: "Escolher Brisa" }));
    fireEvent.click(screen.getByRole("button", { name: "Montar com esta música" }));
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
    expect(HTMLMediaElement.prototype.load).toHaveBeenCalled();
    expect(video.hasAttribute("src")).toBe(false);
    await avancar(0);
    expect(container.querySelector("video")).toBeNull();
    expect(screen.getByText("Montando o corte…")).toBeTruthy();
  });
});
