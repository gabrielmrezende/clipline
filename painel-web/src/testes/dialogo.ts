// Ajudas dos testes para a confirmação do painel (o <dialog> do ProvedorConfirmacao).
import { fireEvent, screen, within } from "@testing-library/react";

export const dialogoAberto = (): HTMLElement => screen.getByRole("alertdialog");

export const haDialogo = (): boolean => screen.queryByRole("alertdialog") !== null;

/** Todo o texto do diálogo aberto (título, resumo, itens e custo). */
export const textoDoDialogo = (): string => dialogoAberto().textContent ?? "";

export const tituloDoDialogo = (): string =>
  document.getElementById(dialogoAberto().getAttribute("aria-labelledby") ?? "")?.textContent ?? "";

export const botaoConfirmarDoDialogo = (): HTMLButtonElement =>
  dialogoAberto().querySelector<HTMLButtonElement>(".dialogo-confirmar")!;

/** Clica em confirmar (true) ou em Cancelar (false) no diálogo aberto. */
export function responderDialogo(sim: boolean) {
  const dialogo = dialogoAberto();
  fireEvent.click(sim ? botaoConfirmarDoDialogo() : within(dialogo).getByRole("button", { name: "Cancelar" }));
}
