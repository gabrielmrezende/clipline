import { act, render, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, vi } from "vitest";
import type { Pedido } from "./api";
import {
  ESPERA_CONSULTA_MS,
  ESPERA_PRIMEIRO_EVENTO_MS,
  REABRIR_EVENTOS_MS,
  URL_EVENTOS,
  reiniciarTarefas,
  useAcompanharPedido,
  useTarefas,
} from "./useTarefas";

/** EventSource de mentira: o teste decide quando abre, manda uma lista ou dá erro. */
class FonteFalsa {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static criadas: FonteFalsa[] = [];
  url: string;
  readyState = FonteFalsa.CONNECTING;
  onerror: (() => void) | null = null;
  ouvintes: Record<string, ((e: MessageEvent) => void)[]> = {};

  constructor(url: string) {
    this.url = url;
    FonteFalsa.criadas.push(this);
  }

  addEventListener(tipo: string, f: (e: MessageEvent) => void) {
    (this.ouvintes[tipo] ??= []).push(f);
  }

  close() {
    this.readyState = FonteFalsa.CLOSED;
  }

  /** O servidor manda a lista da fila. */
  lista(pedidos: Pedido[]) {
    this.readyState = FonteFalsa.OPEN;
    const evento = new MessageEvent("tarefas", { data: JSON.stringify(pedidos) });
    act(() => (this.ouvintes.tarefas ?? []).forEach((f) => f(evento)));
  }

  /** Erro: `desistiu` (401, 404…) fecha; senão o navegador tenta reconectar. */
  erro(desistiu = false) {
    this.readyState = desistiu ? FonteFalsa.CLOSED : FonteFalsa.CONNECTING;
    act(() => this.onerror?.());
  }
}

const abertas = () => FonteFalsa.criadas.filter((f) => f.readyState !== FonteFalsa.CLOSED);
const ultima = () => FonteFalsa.criadas[FonteFalsa.criadas.length - 1];

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
    tipo: "ia",
    cortes: [2],
    progresso: "",
    ...extra,
  };
}

let consultas: string[];
let respostaConsulta: () => Promise<Response>;

const json = (corpo: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }));

beforeEach(() => {
  vi.useFakeTimers();
  reiniciarTarefas();
  FonteFalsa.criadas = [];
  consultas = [];
  respostaConsulta = () => json(pedido({ estado: "montando" }));
  vi.stubGlobal("EventSource", FonteFalsa);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      consultas.push(url);
      return respostaConsulta();
    }),
  );
});

afterEach(() => {
  reiniciarTarefas();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function avancar(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

interface Sonda {
  pedido: Pedido | null;
  terminou: Pedido[];
  perdeu: number;
  trocar: (p: Pedido | null) => void;
}

/** Um bloco mínimo que acompanha um pedido, como os blocos do painel. */
function montarSonda(inicial: Pedido | null) {
  const sonda: Sonda = { pedido: inicial, terminou: [], perdeu: 0, trocar: () => undefined };
  function Bloco() {
    const [p, setP] = useState<Pedido | null>(inicial);
    sonda.pedido = p;
    sonda.trocar = setP;
    useAcompanharPedido(
      p,
      setP,
      (final) => sonda.terminou.push(final),
      () => (sonda.perdeu += 1),
    );
    return null;
  }
  const r = render(<Bloco />);
  return { sonda, ...r };
}

function Lista({ ligado = true }: { ligado?: boolean }) {
  const { tarefas, modo } = useTarefas(ligado);
  return <p data-testid="lista">{`${modo}:${tarefas ? tarefas.map((t) => t.estado).join(",") : "-"}`}</p>;
}

describe("useTarefas", () => {
  it("uma conexão por aba, dividida entre os blocos, fechada quando o último sai", async () => {
    const a = render(<Lista />);
    const b = render(<Lista />);
    expect(FonteFalsa.criadas).toHaveLength(1);
    expect(ultima().url).toBe(URL_EVENTOS);
    const texto = (r: typeof a) => within(r.container).getByTestId("lista").textContent;
    expect(texto(a)).toBe("consulta:-"); // até a primeira lista chegar
    ultima().lista([pedido({ estado: "montando" })]);
    expect(texto(a)).toBe("eventos:montando");
    expect(texto(b)).toBe("eventos:montando");
    a.unmount();
    expect(abertas()).toHaveLength(1);
    b.unmount();
    expect(abertas()).toHaveLength(0);
  });

  it("desligado não abre conexão", () => {
    render(<Lista ligado={false} />);
    expect(FonteFalsa.criadas).toHaveLength(0);
  });

  it("um erro só é a reconexão normal; dois seguidos voltam à consulta e os eventos voltam depois", async () => {
    const r = render(<Lista />);
    ultima().lista([]);
    ultima().erro(); // o servidor fechou a conexão depois de alguns minutos: o navegador reabre
    ultima().lista([pedido()]);
    expect(r.getByTestId("lista").textContent).toBe("eventos:na fila");
    ultima().erro();
    ultima().erro(); // o painel caiu
    expect(r.getByTestId("lista").textContent).toBe("consulta:-");
    expect(abertas()).toHaveLength(0);
    await avancar(REABRIR_EVENTOS_MS);
    expect(FonteFalsa.criadas).toHaveLength(2);
    ultima().lista([pedido({ estado: "pronto" })]);
    expect(r.getByTestId("lista").textContent).toBe("eventos:pronto");
  });

  it("sem a primeira lista em 5 s, volta à consulta", async () => {
    const r = render(<Lista />);
    await avancar(ESPERA_PRIMEIRO_EVENTO_MS);
    expect(r.getByTestId("lista").textContent).toBe("consulta:-");
    expect(abertas()).toHaveLength(0);
  });

  it("ignora o que não é uma lista", () => {
    const r = render(<Lista />);
    const evento = (data: string) => new MessageEvent("tarefas", { data });
    act(() => ultima().ouvintes.tarefas.forEach((f) => f(evento("{não é json"))));
    act(() => ultima().ouvintes.tarefas.forEach((f) => f(evento('{"a": 1}'))));
    expect(r.getByTestId("lista").textContent).toBe("consulta:-");
  });
});

describe("useAcompanharPedido", () => {
  it("pelos eventos: atualiza sem consultar e avisa o fim uma vez", async () => {
    const { sonda } = montarSonda(pedido());
    ultima().lista([pedido({ estado: "montando", progresso: "Gerando 1 de 2…" })]);
    expect(sonda.pedido?.progresso).toBe("Gerando 1 de 2…");
    await avancar(ESPERA_CONSULTA_MS * 3);
    expect(consultas).toEqual([]); // nada de consultas a cada 2 s
    ultima().lista([pedido({ estado: "pronto", mensagem: "2 imagens geradas." })]);
    expect(sonda.pedido?.estado).toBe("pronto");
    expect(sonda.terminou.map((p) => p.estado)).toEqual(["pronto"]);
    expect(abertas()).toHaveLength(0); // terminou: ninguém mais acompanha, a conexão fecha
  });

  it("o SSE falhou: volta a consultar a cada 2 s", async () => {
    const { sonda } = montarSonda(pedido());
    ultima().erro(true); // 404 ou 401: o navegador desiste
    await avancar(ESPERA_CONSULTA_MS);
    expect(consultas).toEqual(["/api/tarefas/t1"]);
    expect(sonda.pedido?.estado).toBe("montando");
    respostaConsulta = () => json(pedido({ estado: "erro", mensagem: "x" }));
    await avancar(ESPERA_CONSULTA_MS);
    expect(consultas).toHaveLength(2);
    expect(sonda.terminou.map((p) => p.estado)).toEqual(["erro"]);
    await avancar(ESPERA_CONSULTA_MS * 3);
    expect(consultas).toHaveLength(2);
  });

  it("os eventos voltam: a consulta para", async () => {
    montarSonda(pedido());
    ultima().erro(true);
    await avancar(ESPERA_CONSULTA_MS);
    expect(consultas).toHaveLength(1);
    await avancar(REABRIR_EVENTOS_MS - ESPERA_CONSULTA_MS);
    const vistas = consultas.length;
    ultima().lista([pedido({ estado: "montando" })]);
    await avancar(ESPERA_CONSULTA_MS * 3);
    expect(consultas).toHaveLength(vistas);
  });

  it("fora da lista: confere uma vez e, se o painel esqueceu (404), avisa", async () => {
    respostaConsulta = () => json({ detail: "tarefa não encontrada" }, 404);
    const { sonda } = montarSonda(pedido());
    ultima().lista([]);
    await avancar(0);
    expect(consultas).toEqual(["/api/tarefas/t1"]);
    expect(sonda.pedido).toBeNull();
    expect(sonda.perdeu).toBe(1);
  });

  it("fora da lista porque acabou de ser criado: confere e espera a próxima lista", async () => {
    respostaConsulta = () => json(pedido());
    const { sonda } = montarSonda(pedido());
    ultima().lista([]);
    await avancar(0);
    expect(consultas).toHaveLength(1);
    expect(sonda.perdeu).toBe(0);
    ultima().lista([pedido({ estado: "montando" })]);
    expect(sonda.pedido?.estado).toBe("montando");
    expect(consultas).toHaveLength(1);
  });

  it("um pedido que já chega terminado (interrompido no reinício) não chama o fim nem abre conexão", async () => {
    const { sonda } = montarSonda(pedido({ estado: "interrompido", mensagem: "o painel foi fechado" }));
    await avancar(ESPERA_CONSULTA_MS * 2);
    expect(sonda.terminou).toEqual([]);
    expect(FonteFalsa.criadas).toHaveLength(0);
    expect(consultas).toEqual([]);
  });

  it("sem EventSource no navegador: consulta a cada 2 s desde o começo", async () => {
    vi.stubGlobal("EventSource", undefined);
    const { sonda } = montarSonda(pedido());
    await avancar(ESPERA_CONSULTA_MS);
    expect(consultas).toEqual(["/api/tarefas/t1"]);
    expect(sonda.pedido?.estado).toBe("montando");
  });
});
