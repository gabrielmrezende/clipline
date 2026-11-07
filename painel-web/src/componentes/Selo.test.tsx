import { render, screen } from "@testing-library/react";
import { Selo } from "./Selo";

describe("Selo", () => {
  it.each(["erro", "com alerta", "sem vídeo final", "pronto"] as const)(
    "mostra o texto %s",
    (valor) => {
      render(<Selo valor={valor} />);
      expect(screen.getByText(valor)).toBeTruthy();
    },
  );
});
