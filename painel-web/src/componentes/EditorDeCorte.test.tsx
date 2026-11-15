import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { responderDialogo, textoDoDialogo, tituloDoDialogo } from "../testes/dialogo";
import { ProvedorConfirmacao } from "./Confirmacao";
import { EditorDeCorte, opcoesDaConfirmacao } from "./EditorDeCorte";

const BASE = "/api/episodios/Ep%201/cortes/2";

const PALAVRAS = Array.from({ length: 10 }, (_, i) => ({
  texto: `w${i}.`,
  inicio: i,
  fim: i + 0.9,
  voz: i < 5 ? "SPEAKER_00" : "SPEAKER_01",
  falante: i < 5 ? "SPEAKER_00 (Gabriel)" : "SPEAKER_01",
  pode_iniciar: true,
  pode_terminar: true,
}));

function trecho(extra: object = {}) {
  return {
    versao: "V1",
    inicio: 2,
    fim: 6.9,
    duracao_episodio: 100,
    minima: 3,
    maxima: 6,
    de: 0,
    ate: 10,
    palavras: PALAVRAS,
    outros: [{ numero: 3, titulo: "Três", inicio: 8, fim: 9.9 }],
    preparado: true,
    montado: true,
    problemas: [],
    pedido: null,
    ...extra,
  };
}

function conferencia(inicio: number, fim: number, extra: object = {}) {
  return {
    inicio,
    fim,
    duracao: Math.round((fim - inicio) * 1000) / 1000,
    mudou: true,
    problemas: [],
    avisos: ["O trecho novo sobrepõe o corte 3 (Três) em 1,0 s."],
    resumo: ["O corte é preparado e montado de novo (leva cerca de 1 minuto)."],
    perdas: ["Momento de imagem fora do trecho novo (fica descartado): 0:01 Ministro."],
    ...extra,
  };
}

function pedido(extra: object = {}) {
  return {
    id: "t9",
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
    tipo: "trecho",
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

let trechos: any[];
let conferirExtra: object;
let tarefas: any[];
let chamadas: { metodo: string; url: string; corpo: any }[];

beforeEach(() => {
  vi.useFakeTimers();
  trechos = [trecho()];
  conferirExtra = {};
  tarefas = [];
  chamadas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpo = init?.body ? JSON.parse(String(init.body)) : null;
      chamadas.push({ metodo, url, corpo });
      if (url.startsWith(`${BASE}/trecho?`)) return resposta(trechos.length > 1 ? trechos.shift() : trechos[0]);
      if (url === `${BASE}/trecho/conferir`) return resposta(conferencia(corpo.inicio, corpo.fim, conferirExtra));
      if (url === `${BASE}/trecho` && metodo === "POST") return resposta(pedido(), 202);
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

async function avancar(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function abrir() {
  const props = { soltarVideo: vi.fn(), aoMudarAndamento: vi.fn(), aoTerminar: vi.fn() };
  render(<EditorDeCorte ep="Ep 1" n={2} montandoNaTela={false} {...props} />, { wrapper: ProvedorConfirmacao });
  await avancar();
  await avancar();
  return props;
}

const palavra = (i: number) => screen.getByRole("option", { name: `w${i}. 0:0${i},0` });
const selecionadas = () =>
  screen.getAllByRole("option").filter((o) => o.getAttribute("aria-selected") === "true").map((o) => o.textContent);
const conferidas = () => chamadas.filter((c) => c.url.endsWith("/trecho/conferir")).map((c) => c.corpo);

describe("EditorDeCorte", () => {
  it("mostra a transcrição com quem fala, o trecho de agora e a duração com os limites", async () => {
    await abrir();
    const lista = screen.getByRole("listbox", { name: "Transcrição ao redor do corte" });
    expect(within(lista).getByRole("group", { name: "SPEAKER_00 (Gabriel)" })).toBeTruthy();
    expect(within(lista).getByRole("group", { name: "SPEAKER_01" })).toBeTruthy();
    expect(selecionadas()).toEqual(["w2.", "w3.", "w4.", "w5.", "w6."]);
    expect(screen.getByText(/Duração/).textContent).toBe("Duração 4,9 s (de 3 a 6 s)");
    expect(screen.getByText(/falas de outros cortes/).textContent).toContain("corte 3 (Três)");
    expect(palavra(8).className).toContain("de-outro-corte");
    expect(palavra(2).getAttribute("tabindex")).toBe("0");
    expect(conferidas()).toEqual([]);
    expect(screen.queryByRole("button", { name: "Trocar o trecho" })).toBeNull();
  });

  it("clique marca o início, Shift+clique o fim, e cada seleção é conferida", async () => {
    await abrir();
    fireEvent.click(palavra(1));
    await avancar();
    expect(selecionadas()).toEqual(["w1.", "w2.", "w3.", "w4.", "w5.", "w6."]);
    fireEvent.click(palavra(7), { shiftKey: true });
    await avancar();
    expect(selecionadas()).toEqual(["w1.", "w2.", "w3.", "w4.", "w5.", "w6.", "w7."]);
    expect(conferidas()).toEqual([
      { inicio: 1, fim: 6.9 },
      { inicio: 1, fim: 7.9 },
    ]);
    expect(screen.getByText(/Duração/).textContent).toBe("Duração 6,9 s (de 3 a 6 s): fora do limite");
    expect(screen.getByRole("heading", { name: "O que muda" })).toBeTruthy();
    expect(screen.getByText(/0:01 Ministro/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Trocar o trecho" }) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Voltar ao trecho de agora" }));
    expect(selecionadas()).toEqual(["w2.", "w3.", "w4.", "w5.", "w6."]);
  });

  it("o modo fim troca o que o clique marca", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("radio", { name: "o fim" }));
    fireEvent.click(palavra(5));
    await avancar();
    expect(conferidas()).toEqual([{ inicio: 2, fim: 5.9 }]);
    fireEvent.click(palavra(3), { shiftKey: true });
    await avancar();
    expect(conferidas()[1]).toEqual({ inicio: 3, fim: 5.9 });
  });

  it("no teclado, as setas andam e Enter e Shift+Enter marcam", async () => {
    await abrir();
    palavra(2).focus();
    fireEvent.keyDown(palavra(2), { key: "ArrowRight" });
    expect(document.activeElement).toBe(palavra(3));
    expect(palavra(3).getAttribute("tabindex")).toBe("0");
    expect(palavra(2).getAttribute("tabindex")).toBe("-1");
    fireEvent.keyDown(palavra(3), { key: "Enter" });
    fireEvent.keyDown(palavra(3), { key: "End" });
    expect(document.activeElement).toBe(palavra(9));
    fireEvent.keyDown(palavra(9), { key: "Enter", shiftKey: true });
    await avancar();
    expect(screen.getByText(/^Início/).textContent).toBe("Início 0:03,0");
    expect(screen.getByText(/^Fim/).textContent).toBe("Fim 0:09,9");
    fireEvent.keyDown(palavra(9), { key: "Home" });
    expect(document.activeElement).toBe(palavra(0));
  });

  it("problemas do validar impedem a troca", async () => {
    conferirExtra = { problemas: ["início no meio da frase"], resumo: [], perdas: [], avisos: [] };
    await abrir();
    fireEvent.click(palavra(3));
    await avancar();
    expect(screen.getByRole("heading", { name: "Não dá para trocar" })).toBeTruthy();
    expect(screen.getByText("início no meio da frase")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Trocar o trecho" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("a confirmação diz o que muda e o que se perde; cancelar não envia nada", async () => {
    const props = await abrir();
    fireEvent.click(palavra(1));
    await avancar();
    fireEvent.click(screen.getByRole("button", { name: "Trocar o trecho" }));
    await avancar();
    expect(tituloDoDialogo()).toBe("Trocar o trecho do corte 2 para 0:01,0 a 0:06,9 (5,9 s)?");
    expect(textoDoDialogo()).toContain("Perde: Momento de imagem fora do trecho novo (fica descartado): 0:01 Ministro.");
    responderDialogo(false);
    await avancar();
    expect(chamadas.some((c) => c.url === `${BASE}/trecho`)).toBe(false);
    expect(props.soltarVideo).not.toHaveBeenCalled();
  });

  it("confirmado: solta o vídeo, manda a versão e acompanha o pedido até o fim", async () => {
    trechos = [trecho(), trecho({ inicio: 1, versao: "V2", pedido: pedido({ estado: "pronto" }) })];
    tarefas = [pedido({ estado: "montando", progresso: "Preparando o trecho novo…" }),
      pedido({ estado: "pronto", mensagem: "Trecho novo: 0:01,0 a 0:06,9 (5,9 s).", avisos: ["aviso da troca"] })];
    const props = await abrir();
    fireEvent.click(palavra(1));
    await avancar();
    fireEvent.click(screen.getByRole("button", { name: "Trocar o trecho" }));
    await avancar();
    responderDialogo(true);
    await avancar();
    expect(props.soltarVideo).toHaveBeenCalled();
    expect(props.aoMudarAndamento).toHaveBeenLastCalledWith(true);
    expect(chamadas.find((c) => c.url === `${BASE}/trecho`)?.corpo).toEqual({
      inicio: 1,
      fim: 6.9,
      versao: "V1",
      confirmado: true,
    });
    expect(screen.getByRole("status").textContent).toContain("Na fila");
    expect(screen.getByRole("listbox").getAttribute("aria-disabled")).toBe("true");
    await avancar(2000);
    expect(screen.getByRole("status").textContent).toContain("Preparando o trecho novo…");
    await avancar(2000);
    await avancar();
    expect(props.aoMudarAndamento).toHaveBeenLastCalledWith(false);
    expect(props.aoTerminar).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Trecho novo: 0:01,0 a 0:06,9 (5,9 s).")).toBeTruthy();
    expect(screen.getByText(/aviso da troca/)).toBeTruthy();
    expect(chamadas.filter((c) => c.url.startsWith(`${BASE}/trecho?`))).toHaveLength(2);
    expect(selecionadas()).toEqual(["w1.", "w2.", "w3.", "w4.", "w5.", "w6."]);
    expect(screen.queryByRole("button", { name: "Trocar o trecho" })).toBeNull();
  });

  it("corte ainda não montado: não mexe no player", async () => {
    trechos = [trecho({ montado: false, preparado: false })];
    const props = await abrir();
    fireEvent.click(palavra(1));
    await avancar();
    fireEvent.click(screen.getByRole("button", { name: "Trocar o trecho" }));
    await avancar();
    responderDialogo(true);
    await avancar();
    expect(props.soltarVideo).not.toHaveBeenCalled();
    expect(props.aoMudarAndamento).toHaveBeenLastCalledWith(true);
  });

  it("retoma a troca que já estava em andamento", async () => {
    trechos = [trecho({ pedido: pedido({ estado: "montando", progresso: "Montando o corte…" }) })];
    tarefas = [pedido({ estado: "montando", progresso: "Montando o corte…" })];
    const props = await abrir();
    expect(props.aoMudarAndamento).toHaveBeenCalledWith(true);
    expect(screen.getByRole("status").textContent).toContain("Montando o corte…");
    fireEvent.click(palavra(1));
    expect(selecionadas()).toEqual(["w2.", "w3.", "w4.", "w5.", "w6."]);
  });

  it("sem transcrição, explica sem alarde", async () => {
    vi.stubGlobal("fetch", vi.fn(() => resposta({ detail: "Transcrição não encontrada." }, 404)));
    await abrir();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Transcrição não encontrada.")).toBeTruthy();
  });

  it("mostrar mais busca uma janela maior e mantém a seleção", async () => {
    await abrir();
    fireEvent.click(palavra(1));
    await avancar();
    fireEvent.click(screen.getByRole("button", { name: "Mostrar mais 30 s depois" }));
    await avancar();
    expect(chamadas.filter((c) => c.metodo === "GET").map((c) => c.url)).toEqual([
      `${BASE}/trecho?antes=30&depois=30`,
      `${BASE}/trecho?antes=30&depois=60`,
    ]);
    expect(selecionadas()[0]).toBe("w1.");
    expect((screen.getByRole("button", { name: "Mostrar mais 30 s antes" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("opcoesDaConfirmacao", () => {
  it("lista o que muda, o que se perde e os avisos; com perda, o tom é de algo que não volta", () => {
    const opcoes = opcoesDaConfirmacao(4, conferencia(61.25, 140.5, { avisos: ["sobrepõe o corte 3"] }));
    expect(opcoes.titulo).toBe("Trocar o trecho do corte 4 para 1:01,3 a 2:20,5 (79,3 s)?");
    expect(opcoes.itens).toEqual([
      "O corte é preparado e montado de novo (leva cerca de 1 minuto).",
      "Perde: Momento de imagem fora do trecho novo (fica descartado): 0:01 Ministro.",
      "Atenção: sobrepõe o corte 3",
    ]);
    expect(opcoes.tom).toBe("irreversivel");
    expect(opcoes.aviso).toBeTruthy();
  });

  it("sem perda, a confirmação é a normal", () => {
    const opcoes = opcoesDaConfirmacao(4, conferencia(61.25, 140.5, { perdas: [], avisos: [] }));
    expect(opcoes.tom).toBe("normal");
    expect(opcoes.aviso).toBeUndefined();
  });
});
