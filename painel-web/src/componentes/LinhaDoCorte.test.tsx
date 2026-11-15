import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import type { Momento } from "../api";
import { LinhaDoCorte } from "./LinhaDoCorte";

function momento(extra: Partial<Momento>): Momento {
  return {
    chave: "m",
    inicio: 0,
    fim: 4,
    fala: "Fala",
    tipo: "foto",
    nome: "n",
    busca: "",
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

/** Um <video> de 100 s, como o navegador deixa depois de ler os metadados. */
function videoDe(segundos: number): HTMLVideoElement {
  const video = document.createElement("video");
  Object.defineProperty(video, "duration", { value: segundos, configurable: true });
  return video;
}

const MOMENTOS = [
  momento({ chave: "a", inicio: 10, fim: 14, tipo: "foto", no_video: "a-1.jpg" }),
  momento({ chave: "b", inicio: 50, fim: 55, inicio_tela: 52, fim_tela: 57, tipo: "ia", no_video: null }),
  momento({ chave: "c", inicio: 70, fim: 74, descartar: true }),
  momento({ chave: "d", inicio: 80, fim: 84, inicio_tela: null }),
];

describe("LinhaDoCorte", () => {
  it("sem a duração do vídeo não desenha nada", () => {
    const { container } = render(<LinhaDoCorte video={null} momentos={MOMENTOS} irPara={vi.fn()} />);
    expect(container.innerHTML).toBe("");
  });

  it("marca os trechos na posição do tempo de tela, sem os descartados", () => {
    render(<LinhaDoCorte video={videoDe(100)} momentos={MOMENTOS} irPara={vi.fn()} />);
    const foto = screen.getByRole("button", { name: "Imagem em 0:10: foto" });
    const ia = screen.getByRole("button", { name: "Imagem em 0:52: imagem de IA, fora do vídeo" });
    expect(foto.style.left).toBe("10%");
    expect(foto.style.width).toBe("4%");
    expect(ia.style.left).toBe("52%");
    expect(ia.className).toContain("fora");
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(screen.getByText("1:40")).toBeTruthy();
  });

  it("clicar num trecho leva o player ao início dele", () => {
    const irPara = vi.fn();
    render(<LinhaDoCorte video={videoDe(100)} momentos={MOMENTOS} irPara={irPara} />);
    fireEvent.click(screen.getByRole("button", { name: /0:52/ }));
    expect(irPara).toHaveBeenCalledWith(52);
  });

  it("acende o trecho em que o player está", () => {
    const video = videoDe(100);
    render(<LinhaDoCorte video={video} momentos={MOMENTOS} irPara={vi.fn()} />);
    act(() => {
      video.currentTime = 11;
      video.dispatchEvent(new Event("timeupdate"));
    });
    expect(screen.getByRole("button", { name: /0:10/ }).className).toContain("agora");
    expect(screen.getByRole("button", { name: /0:52/ }).className).not.toContain("agora");
  });
});

describe("LinhaDoCorte com as remoções da limpeza", () => {
  const REMOCOES = {
    remocoes: [
      { tempo: 12.4, duracao: 0.62, motivo: "pausa", texto: "", episodio: 112.4 },
      { tempo: 30, duracao: 0.4, motivo: "hesitação e repetição", texto: "hum o", episodio: 131 },
      { tempo: 1, duracao: 1.3, motivo: "trecho removido", texto: "", episodio: 100 },
      { tempo: 140, duracao: 1, motivo: "pausa", texto: "", episodio: 250 },
    ],
    removido: 3.32,
    avisos: [],
  };
  let urls: string[];

  function servir(corpo: unknown, status = 200) {
    urls = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        urls.push(url);
        return Promise.resolve(
          new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }),
        );
      }),
    );
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("marca cada remoção no tempo do corte, mesmo sem imagens, e ignora o que passa do fim", async () => {
    servir(REMOCOES);
    const { container } = render(
      <LinhaDoCorte video={videoDe(100)} momentos={[]} irPara={vi.fn()} ep="Ep 1" n={2} />,
    );
    await waitFor(() => expect(container.querySelectorAll(".linha-remocao")).toHaveLength(3));
    expect(urls).toEqual(["/api/episodios/Ep%201/cortes/2/remocoes"]);
    const marcas = Array.from(container.querySelectorAll<HTMLElement>(".linha-remocao"));
    expect(marcas.map((m) => m.style.left)).toEqual(["12.4%", "30%", "1%"]);
    expect(marcas.map((m) => m.classList.contains("pausa"))).toEqual([true, false, false]);
    expect(marcas.every((m) => m.getAttribute("aria-hidden") === "true")).toBe(true);
    const legenda = container.querySelector(".legenda-linha") as HTMLElement;
    expect(within(legenda).queryByText("imagem")).toBeNull();
    expect(within(legenda).getByText("fala tirada")).toBeTruthy();
    expect(within(legenda).getByText("pausa tirada")).toBeTruthy();
  });

  it("a lista das remoções leva o player um pouco antes da emenda", async () => {
    servir(REMOCOES);
    const irPara = vi.fn();
    render(<LinhaDoCorte video={videoDe(100)} momentos={MOMENTOS} irPara={irPara} ep="Ep 1" n={2} />);
    const resumo = await screen.findByText("O que a limpeza tirou: 3 trechos, 2,3 s");
    expect(resumo.tagName).toBe("SUMMARY");
    fireEvent.click(screen.getByRole("button", { name: /Hesitação e repetição: “hum o”/ }));
    expect(irPara).toHaveBeenCalledWith(28);
    fireEvent.click(screen.getByRole("button", { name: "0:01: Trecho removido, 1,3 s" }));
    expect(irPara).toHaveBeenLastCalledWith(0);
    expect(screen.getByRole("button", { name: "0:12: Pausa, 0,6 s" }).title).toBe("Ouvir a partir de 0:10");
  });

  it("sem resposta do painel, fica só com as imagens", async () => {
    servir({ detail: "?" }, 404);
    const { container } = render(
      <LinhaDoCorte video={videoDe(100)} momentos={MOMENTOS} irPara={vi.fn()} ep="Ep 1" n={2} />,
    );
    await waitFor(() => expect(urls).toHaveLength(1));
    await act(async () => {});
    expect(container.querySelector(".linha-remocao")).toBeNull();
    expect(container.querySelector(".remocoes")).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("sem ep e n não pede nada; com aviso, mostra o aviso na lista", async () => {
    servir({ ...REMOCOES, avisos: ["sem edicoes.md: os motivos das remoções não aparecem"] });
    const { rerender } = render(<LinhaDoCorte video={videoDe(100)} momentos={MOMENTOS} irPara={vi.fn()} />);
    await act(async () => {});
    expect(urls).toEqual([]);
    rerender(<LinhaDoCorte video={videoDe(100)} momentos={MOMENTOS} irPara={vi.fn()} ep="Ep 1" n={2} versao="1" />);
    expect(await screen.findByText(/sem edicoes.md/)).toBeTruthy();
    rerender(<LinhaDoCorte video={videoDe(100)} momentos={MOMENTOS} irPara={vi.fn()} ep="Ep 1" n={2} versao="2" />);
    await waitFor(() => expect(urls).toHaveLength(2));
  });
});
