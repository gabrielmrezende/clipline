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

  // A caixa "Aprovado" tem tamanho de caixa, na mesma linha do rótulo (não esticada pela regra dos inputs).
  const caixa = page.getByLabel("Aprovado");
  const rotulo = page.locator("label.aprovado");
  const [b, r] = [await caixa.boundingBox(), await rotulo.boundingBox()];
  expect(b && b.width).toBeLessThan(40);
  expect(b && r && Math.abs(b.y + b.height / 2 - (r.y + r.height / 2))).toBeLessThan(4);

  await caixa.check();
  const gerar = page.getByRole("button", { name: /^Gerar as aprovadas/ });
  await expect(gerar).toBeEnabled();
  await expect(gerar).toContainText("1 imagem");

  page.once("dialog", (d) => d.accept());
  const pedido = page.waitForRequest((q) => q.method() === "POST" && q.url().endsWith("/cortes/3/ia"));
  await gerar.click();
  expect((await pedido).postDataJSON()).toEqual({ itens: [{ corte: 3, chave: "0006-pais-parado" }] });

  await expect(page.getByRole("status").filter({ hasText: /^Pronto/ })).toBeVisible({ timeout: 20_000 });

  const miniatura = page.locator('img[src$="-ia-1.jpg"]');
  await expect(miniatura).toBeVisible();
  await expect
    .poll(() => miniatura.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);

  expect(externas).toEqual([]);
});
