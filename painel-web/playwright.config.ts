import { defineConfig } from "@playwright/test";

// O Python do .venv do projeto (Windows ou Linux/macOS); ESTEIRA_PYTHON troca, por exemplo na CI.
const python =
  process.env.ESTEIRA_PYTHON ?? (process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
// ESTEIRA_E2E_PORTA: outra porta para o painel de teste, para rodar duas cópias do repositório ao mesmo tempo.
const porta = Number(process.env.ESTEIRA_E2E_PORTA || 8766);
if (!Number.isInteger(porta) || porta < 1 || porta > 65535) {
  throw new Error(`ESTEIRA_E2E_PORTA inválida: ${process.env.ESTEIRA_E2E_PORTA}. Use um número de 1 a 65535.`);
}
const endereco = `http://127.0.0.1:${porta}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "*.spec.ts",
  timeout: 30_000,
  workers: 1, // os testes dividem o mesmo servidor e o mesmo episódio falso
  reporter: "list",
  use: {
    baseURL: endereco,
    // PLAYWRIGHT_CHROMIUM: um Chrome já instalado, quando não dá para baixar o do Playwright.
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {},
  },
  webServer: {
    cwd: "..",
    command:
      `node painel-web/e2e/preparar.mjs && "${python}" -m esteira painel --cortes painel-web/e2e/.cortes --porta ${porta}`,
    url: endereco,
    env: {
      ESTEIRA_PAINEL_MONTAGEM_FALSA: "1",
      ESTEIRA_PAINEL_PASTA_MUSICAS: "painel-web/e2e/.musicas",
      ESTEIRA_PAINEL_IMAGEM_FALSA: "1",
    },
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
