import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Players } from "./Players";

describe("Players", () => {
  it("mostra o corte e um botão por vídeo final e troca o src", async () => {
    const { container } = render(<Players ep="Ep 1" n={2} videoFinal={["A.mp4", "b.MOV"]} />);
    expect(screen.getAllByRole("button")).toHaveLength(3);
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
});
