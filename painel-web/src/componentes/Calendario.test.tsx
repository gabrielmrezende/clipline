import { render, screen, within } from "@testing-library/react";
import { Calendario } from "./Calendario";

const itens = [
  { numero: 1, titulo: "Um", data: "2026-11-08 18:00", redes: ["youtube", "tiktok", "instagram"] },
  { numero: 2, titulo: "Dois", data: "2026-11-08 12:00", redes: ["youtube", "tiktok"] },
  { numero: 3, titulo: "Três", data: "", redes: ["youtube", "tiktok"] },
];

describe("Calendario", () => {
  it("agrupa por dia, TikTok e Shorts por horário, Instagram só quem tem", () => {
    render(<Calendario itens={itens} />);
    const dia = screen.getByRole("region", { name: "2026-11-08" });
    const tiktok = within(dia).getByTestId("linha-tiktok");
    const nums = within(tiktok).getAllByRole("listitem").map((e) => e.textContent);
    expect(nums[0]).toContain("2");
    expect(nums[1]).toContain("1");
    expect(nums).toHaveLength(2);
    const insta = within(dia).getByTestId("linha-instagram");
    const i = within(insta).getAllByRole("listitem");
    expect(i).toHaveLength(1);
    expect(i[0].textContent).toContain("1");
  });

  it("põe o corte sem data em Sem data, no fim", () => {
    render(<Calendario itens={itens} />);
    const regioes = screen.getAllByRole("region");
    expect(regioes[regioes.length - 1].getAttribute("aria-label")).toBe("Sem data");
    expect(within(regioes[regioes.length - 1]).getByText(/Três/)).toBeTruthy();
  });
});
