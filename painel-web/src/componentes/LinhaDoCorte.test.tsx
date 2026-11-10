import { act, fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
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
