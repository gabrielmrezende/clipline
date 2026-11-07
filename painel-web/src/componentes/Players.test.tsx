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
});
