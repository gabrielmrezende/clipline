import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, vi } from "vitest";
import { areasDaRede } from "./areasSeguras";
import { Players, QUADRO } from "./Players";

let play: ReturnType<typeof vi.fn>;
let pause: ReturnType<typeof vi.fn>;

beforeEach(() => {
  play = vi.fn(() => Promise.resolve());
  pause = vi.fn();
  HTMLMediaElement.prototype.play = play as any;
  HTMLMediaElement.prototype.pause = pause as any;
  try {
    localStorage.clear();
  } catch {
    /* sem armazenamento */
  }
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** O <video> como o navegador deixa depois dos metadados: 60 s, parado no tempo pedido. */
function prepararVideo(container: HTMLElement, { duracao = 60, tempo = 10, parado = true } = {}) {
  const video = container.querySelector("video")!;
  Object.defineProperty(video, "duration", { value: duracao, configurable: true });
  Object.defineProperty(video, "paused", { value: parado, configurable: true });
  video.currentTime = tempo;
  return video;
}

const tecla = (key: string, alvo: Element | Document = document.body, extra: object = {}) =>
  fireEvent.keyDown(alvo, { key, ...extra });

describe("Players", () => {
  it("mostra o corte e um botão por vídeo final e troca o src", async () => {
    const { container } = render(<Players ep="Ep 1" n={2} videoFinal={["A.mp4", "b.MOV"]} />);
    const escolha = within(container.querySelector(".botoes-video") as HTMLElement);
    expect(escolha.getAllByRole("button")).toHaveLength(3);
    const video = () => container.querySelector("video")!;
    expect(video().getAttribute("src")).toBe("/api/episodios/Ep%201/cortes/2/video");
    expect(video().hasAttribute("controls")).toBe(true);
    expect(video().getAttribute("preload")).toBe("metadata");
    await userEvent.click(screen.getByRole("button", { name: "b.MOV" }));
    expect(video().getAttribute("src")).toBe("/api/episodios/Ep%201/cortes/2/video-final/b.MOV");
  });

  it("montando: sem <video> do corte e com Montando o corte…", async () => {
    const { container, rerender } = render(
      <Players ep="Ep 1" n={2} videoFinal={["A.mp4"]} montando />,
    );
    expect(container.querySelector("video")).toBeNull();
    expect(screen.getByText("Montando o corte…")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "A.mp4" }));
    expect(container.querySelector("video")!.getAttribute("src")).toBe(
      "/api/episodios/Ep%201/cortes/2/video-final/A.mp4",
    );
    await userEvent.click(screen.getByRole("button", { name: "Corte" }));
    expect(container.querySelector("video")).toBeNull();
    rerender(<Players ep="Ep 1" n={2} videoFinal={["A.mp4"]} montando={false} versao="9" />);
    expect(container.querySelector("video")!.getAttribute("src")).toBe(
      "/api/episodios/Ep%201/cortes/2/video?v=9",
    );
    expect(screen.queryByText("Montando o corte…")).toBeNull();
  });

  it("repassa o <video> para o ref da tela", () => {
    const ref = { current: null as HTMLVideoElement | null };
    const { container } = render(<Players ep="Ep 1" n={2} videoFinal={[]} videoRef={ref} />);
    expect(ref.current).toBe(container.querySelector("video"));
  });

  describe("atalhos", () => {
    it("espaço e K tocam e pausam", () => {
      const { container } = render(<Players ep="Ep 1" n={2} videoFinal={[]} />);
      const video = prepararVideo(container, { parado: true });
      tecla(" ");
      expect(play).toHaveBeenCalledTimes(1);
      Object.defineProperty(video, "paused", { value: false, configurable: true });
      tecla("k");
      expect(pause).toHaveBeenCalledTimes(1);
    });

    it("J e L pulam 10 s; ← e → pulam 5 s, sem passar do começo nem do fim", () => {
      const { container } = render(<Players ep="Ep 1" n={2} videoFinal={[]} />);
      const video = prepararVideo(container, { duracao: 60, tempo: 10 });
      tecla("l");
      expect(video.currentTime).toBe(20);
      tecla("ArrowLeft");
      expect(video.currentTime).toBe(15);
      tecla("J");
      expect(video.currentTime).toBe(5);
      tecla("j");
      expect(video.currentTime).toBe(0);
      tecla("End");
      expect(video.currentTime).toBe(60);
      tecla("ArrowRight");
      expect(video.currentTime).toBe(60);
      tecla("Home");
      expect(video.currentTime).toBe(0);
    });

    it("vírgula e ponto andam um quadro (1/30 s) e pausam", () => {
      const { container } = render(<Players ep="Ep 1" n={2} videoFinal={[]} />);
      const video = prepararVideo(container, { tempo: 1 });
      tecla(".");
      expect(video.currentTime).toBeCloseTo(1 + QUADRO, 5);
      tecla(",");
      tecla(",");
      expect(video.currentTime).toBeCloseTo(1 - QUADRO, 5);
      expect(pause).toHaveBeenCalledTimes(3);
      expect(screen.getByText("−1 quadro")).toBeTruthy();
    });

    it("< e > mudam a velocidade de 0,5x a 2x, e o seletor também", () => {
      const { container } = render(<Players ep="Ep 1" n={2} videoFinal={[]} />);
      const video = prepararVideo(container);
      const seletor = screen.getByLabelText("Velocidade") as HTMLSelectElement;
      expect(seletor.value).toBe("1");
      tecla(">");
      expect(video.playbackRate).toBe(1.25);
      expect(screen.getByText("Velocidade 1,25x")).toBeTruthy();
      for (let i = 0; i < 5; i += 1) tecla(">");
      expect(video.playbackRate).toBe(2);
      fireEvent.change(seletor, { target: { value: "0.5" } });
      expect(video.playbackRate).toBe(0.5);
      tecla("<");
      expect(video.playbackRate).toBe(0.5);
      expect(Array.from(seletor.options).map((o) => o.textContent)).toEqual([
        "0,5x",
        "0,75x",
        "1x",
        "1,25x",
        "1,5x",
        "2x",
      ]);
    });

    it("não disparam com o foco num campo de texto, num seletor ou com Ctrl", () => {
      const { container } = render(
        <>
          <textarea aria-label="Texto" />
          <input aria-label="Busca" />
          <Players ep="Ep 1" n={2} videoFinal={[]} />
        </>,
      );
      const video = prepararVideo(container, { tempo: 10 });
      tecla("k", screen.getByLabelText("Texto"));
      tecla(" ", screen.getByLabelText("Texto"));
      tecla("l", screen.getByLabelText("Busca"));
      tecla("ArrowRight", screen.getByLabelText("Velocidade"));
      tecla("l", document.body, { ctrlKey: true });
      expect(play).not.toHaveBeenCalled();
      expect(video.currentTime).toBe(10);
    });

    it("espaço num botão é clicar nele, não tocar o vídeo", () => {
      const { container } = render(<Players ep="Ep 1" n={2} videoFinal={["A.mp4"]} />);
      prepararVideo(container);
      tecla(" ", screen.getByRole("button", { name: "A.mp4" }));
      expect(play).not.toHaveBeenCalled();
      tecla("k", screen.getByRole("button", { name: "A.mp4" }));
      expect(play).toHaveBeenCalledTimes(1);
    });

    it("com um diálogo aberto, nada muda atrás dele", () => {
      const { container } = render(
        <>
          <dialog open>Confirmar?</dialog>
          <Players ep="Ep 1" n={2} videoFinal={[]} />
        </>,
      );
      const video = prepararVideo(container, { tempo: 10 });
      tecla("l");
      tecla("k");
      expect(video.currentTime).toBe(10);
      expect(play).not.toHaveBeenCalled();
    });

    it("? abre a ajuda dos atalhos; Esc fecha e o foco volta", () => {
      render(<Players ep="Ep 1" n={2} videoFinal={[]} />);
      const botao = screen.getByRole("button", { name: "Atalhos do teclado" });
      botao.focus();
      tecla("?", botao);
      const ajuda = screen.getByRole("dialog", { name: "Atalhos do player" });
      expect(within(ajuda).getByText("Quadro anterior ou seguinte (pausa)")).toBeTruthy();
      expect(within(ajuda).getAllByText(/./, { selector: "kbd" }).length).toBeGreaterThan(8);
      fireEvent.keyDown(document.activeElement!, { key: "Escape" });
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(document.activeElement).toBe(botao);
      fireEvent.click(botao);
      expect(screen.getByRole("dialog", { name: "Atalhos do player" })).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });

  describe("áreas das redes", () => {
    it("o seletor liga a sobreposição da rede e lembra a escolha", () => {
      const { container, unmount } = render(<Players ep="Ep 1" n={2} videoFinal={[]} />);
      expect(container.querySelector(".areas-rede")).toBeNull();
      fireEvent.change(screen.getByLabelText("Áreas da rede"), { target: { value: "tiktok" } });
      const camada = container.querySelector(".areas-rede") as HTMLElement;
      expect(camada.getAttribute("data-rede")).toBe("tiktok");
      expect(camada.getAttribute("aria-hidden")).toBe("true");
      expect(camada.querySelectorAll(".area-coberta")).toHaveLength(3);
      expect(screen.getByText(/Áreas aproximadas/)).toBeTruthy();
      unmount();
      const outro = render(<Players ep="Ep 1" n={2} videoFinal={[]} />);
      expect(outro.container.querySelector(".areas-rede")?.getAttribute("data-rede")).toBe("tiktok");
    });

    it("A troca a rede em sequência e volta a desligar", () => {
      const { container } = render(<Players ep="Ep 1" n={2} videoFinal={[]} />);
      const rede = () => container.querySelector(".areas-rede")?.getAttribute("data-rede") ?? "";
      tecla("a");
      expect(rede()).toBe("tiktok");
      tecla("a");
      expect(rede()).toBe("shorts");
      tecla("A");
      expect(rede()).toBe("reels");
      tecla("a");
      expect(rede()).toBe("");
      expect(screen.getByText("Áreas desligadas")).toBeTruthy();
    });

    it("o aviso do atalho some depois de um instante", () => {
      vi.useFakeTimers();
      try {
        render(<Players ep="Ep 1" n={2} videoFinal={[]} />);
        tecla("a");
        expect(screen.getByText("Áreas do TikTok")).toBeTruthy();
        act(() => {
          vi.advanceTimersByTime(1000);
        });
        expect(screen.queryByText("Áreas do TikTok")).toBeNull();
      } finally {
        vi.useRealTimers();
      }
    });

    it("as faixas cobertas ficam dentro da tela e o retângulo livre entre elas", () => {
      for (const rede of ["tiktok", "shorts", "reels"] as const) {
        const { cobertas, livre } = areasDaRede(rede);
        for (const c of cobertas) {
          expect(c.x).toBeGreaterThanOrEqual(0);
          expect(c.y).toBeGreaterThanOrEqual(0);
          expect(c.x + c.largura).toBeLessThanOrEqual(100.01);
          expect(c.y + c.altura).toBeLessThanOrEqual(100.01);
        }
        const [topo, coluna, base] = cobertas;
        expect(livre.y).toBe(topo.altura);
        expect(livre.y + livre.altura).toBeCloseTo(base.y, 1);
        expect(livre.x + livre.largura).toBeCloseTo(coluna.x, 1);
      }
    });
  });
});
