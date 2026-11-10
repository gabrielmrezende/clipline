import { expect, test } from "@playwright/test";

const EPISODIO = "Entre Assuntos 99 - Convidado (teste)";

test("aprova um momento de IA, gera a imagem e mostra a miniatura", async ({ page }) => {
  // Nada deve sair para a internet: a IA é falsa e as candidatas de foto são imagens embutidas.
  const externas: string[] = [];
  page.on("request", (r) => {
    const url = r.url();
    if (!url.startsWith("http://127.0.0.1") && !url.startsWith("data:")) externas.push(url);
  });

  await page.goto("/");
  await page.getByRole("link", { name: EPISODIO }).click();
  await page.getByRole("link", { name: /3\. Tres/ }).click();
  await expect(page.getByRole("heading", { name: "Imagens" })).toBeVisible();

  await page.getByLabel("Aprovado").check();
  const gerar = page.getByRole("button", { name: /^Gerar as aprovadas/ });
  await expect(gerar).toBeEnabled();
  await expect(gerar).toContainText("1 imagem");

  page.once("dialog", (d) => d.accept());
  await gerar.click();

  await expect(page.getByRole("status").filter({ hasText: /^Pronto/ })).toBeVisible({ timeout: 20_000 });

  const miniatura = page.locator('img[src$="-ia-1.jpg"]');
  await expect(miniatura).toBeVisible();
  await expect
    .poll(() => miniatura.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);

  expect(externas).toEqual([]);
});
