import { defineConfig } from "@playwright/test";

// O Python do .venv do projeto (Windows ou Linux/macOS); ESTEIRA_PYTHON troca, por exemplo na CI.
const python =
  process.env.ESTEIRA_PYTHON ?? (process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  testMatch: "*.spec.ts",
  timeout: 30_000,
  workers: 1, // os testes dividem o mesmo servidor e o mesmo episódio falso
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8766",
    // PLAYWRIGHT_CHROMIUM: um Chrome já instalado, quando não dá para baixar o do Playwright.
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {},
  },
  webServer: {
    cwd: "..",
    command:
      `node painel-web/e2e/preparar.mjs && "${python}" -m esteira painel --cortes painel-web/e2e/.cortes --porta 8766`,
    url: "http://127.0.0.1:8766",
    env: {
      ESTEIRA_PAINEL_MONTAGEM_FALSA: "1",
      ESTEIRA_PAINEL_PASTA_MUSICAS: "painel-web/e2e/.musicas",
      ESTEIRA_PAINEL_IMAGEM_FALSA: "1",
    },
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
