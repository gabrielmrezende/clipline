import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { ErroDaTela } from "./ErroDaTela";

function Quebra(): JSX.Element {
  throw new Error("quebrou");
}

it("mostra a mensagem e o botão de recarregar no lugar da tela quebrada", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  render(
    <ErroDaTela>
      <Quebra />
    </ErroDaTela>,
  );
  expect(screen.getByRole("alert").textContent).toBe("quebrou");
  expect(screen.getByRole("button", { name: "Recarregar" })).toBeTruthy();
});
