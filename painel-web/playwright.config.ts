import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "*.spec.ts",
  timeout: 30_000,
  workers: 1, // os testes dividem o mesmo servidor e o mesmo episódio falso
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:8766" },
  webServer: {
    cwd: "..",
    command:
      "node painel-web/e2e/preparar.mjs && \".venv/Scripts/python.exe\" -m esteira painel --cortes painel-web/e2e/.cortes --porta 8766",
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
