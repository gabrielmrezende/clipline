import { expect, test } from "@playwright/test";

const EPISODIO = "Entre Assuntos 99 - Convidado (teste)";

test("corrige o texto de uma tela da legenda", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: EPISODIO }).click();
  await page.getByRole("link", { name: /1\. Um/ }).click();

  await page.getByRole("button", { name: "Editar o texto (2 telas)" }).click();
  await page.getByLabel("Tela 1, 0:00").fill("olá Brasil");
  await page.getByRole("button", { name: "Salvar 1 tela" }).click();
  await expect(page.getByText("Legenda salva. Monte o corte para ver no vídeo.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Montar com a legenda nova" })).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Editar o texto (2 telas)" }).click();
  await expect(page.getByLabel("Tela 1, 0:00")).toHaveValue("olá Brasil");
});

test("o painel abre sem nada bloqueado pela política de conteúdo", async ({ page }) => {
  const violacoes: string[] = [];
  page.on("console", (m) => {
    if (/Content Security Policy|Refused to/i.test(m.text())) violacoes.push(m.text());
  });
  const resposta = await page.goto("/");
  expect(resposta?.headers()["content-security-policy"]).toContain("default-src 'self'");
  await page.getByRole("link", { name: EPISODIO }).click();
  await page.getByRole("link", { name: /3\. Tres/ }).click();
  await expect(page.getByRole("heading", { name: "Publicar" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Legenda" })).toBeVisible();
  expect(violacoes).toEqual([]);
});

test("uma página de outra origem não consegue chamar a API", async ({ request }) => {
  const resposta = await request.post("/api/entrar", {
    data: { codigo: "x" },
    headers: { Origin: "http://site-malicioso.example" },
  });
  expect(resposta.status()).toBe(403);
});
