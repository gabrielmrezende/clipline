import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "*.spec.ts",
  timeout: 30_000,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:8766" },
  webServer: {
    cwd: "..",
    command:
      "node painel-web/e2e/preparar.mjs && \".venv/Scripts/python.exe\" -m esteira painel --cortes painel-web/e2e/.cortes --porta 8766",
    url: "http://127.0.0.1:8766",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
