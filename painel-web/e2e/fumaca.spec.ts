import { expect, test } from "@playwright/test";

const EPISODIO = "Entre Assuntos 99 - Convidado (teste)";

test("revisa um corte e salva o TikTok", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: EPISODIO }).click();

  await expect(page.getByRole("heading", { name: EPISODIO })).toBeVisible();
  await expect(page.getByRole("heading", { name: "1. Um" })).toBeVisible();
  const corte2 = page.getByRole("listitem").filter({ hasText: "2. Dois" });
  await expect(corte2.getByText("erro", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: /1\. Um/ }).click();
  const tiktok = page.getByLabel("Legenda do TikTok");
  await expect(tiktok).toBeVisible();
  const novo = "Texto novo do TikTok escrito pelo teste de fumaça. #teste";
  await tiktok.fill(novo);
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByText("Salvo.")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Legenda do TikTok")).toHaveValue(new RegExp("Texto novo do TikTok"));
});
