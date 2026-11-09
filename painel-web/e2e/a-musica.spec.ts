import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

// Roda antes da fumaça: a fumaça reescreve o TikTok do corte 1 e tiraria o crédito do texto.
const EPISODIO = "Entre Assuntos 99 - Convidado (teste)";
const NOVA = "Pyro Flow";

interface Faixa {
  titulo: string;
  credito: string;
}

test("troca a música do corte 1 e atualiza o crédito do post", async ({ page }) => {
  const catalogo: Faixa[] = JSON.parse(readFileSync(join(process.cwd(), "e2e", ".musicas", "catalogo.json"), "utf-8"));
  const creditoNovo = catalogo.find((f) => f.titulo === NOVA)!.credito;
  const creditoAntigo = catalogo.find((f) => f.titulo === "Ice Flow")!.credito;

  await page.goto("/");
  await page.getByRole("link", { name: EPISODIO }).click();
  await page.getByRole("link", { name: /1\. Um/ }).click();

  await expect(page.getByRole("heading", { name: "Do episódio" })).toBeVisible();
  await page.getByRole("button", { name: `Escolher ${NOVA}` }).click();
  await page.getByRole("button", { name: "Montar com esta música" }).click();
  await expect(page.getByText("Pronto: o corte.mp4 foi atualizado.")).toBeVisible({ timeout: 15_000 });

  const tiktok = page.getByLabel("Legenda do TikTok");
  await expect.poll(() => tiktok.inputValue(), { timeout: 10_000 }).toContain(creditoNovo);
  expect(await tiktok.inputValue()).not.toContain(creditoAntigo);
});
