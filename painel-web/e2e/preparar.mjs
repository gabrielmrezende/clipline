// Cria o episódio falso usado pelo teste de fumaça em e2e/.cortes/.
import { copyFileSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const aqui = dirname(fileURLToPath(import.meta.url));
const raiz = join(aqui, ".cortes");
const post = join(aqui, "..", "..", "tests", "dados_post_corte1.md");
const credito = "Música: Ice Flow — Kevin MacLeod (incompetech.com), licença CC BY 4.0.";

const gravar = (caminho, dados) => writeFileSync(caminho, JSON.stringify(dados, null, 2), "utf-8");

rmSync(raiz, { recursive: true, force: true });
const episodio = join(raiz, "Entre Assuntos 99 - Convidado (teste)");
mkdirSync(join(episodio, "transcricao"), { recursive: true });

const palavras = Array.from({ length: 30 }, (_, i) => ({ texto: `p${i}`, inicio: i - 0.4, fim: i + 0.4 }));
gravar(join(episodio, "transcricao", "palavras.json"), palavras);

const cortes = [
  { numero: 1, titulo: "Um", inicio: 10, fim: 20, clima: "tenso", instagram: false, data: "" },
  { numero: 2, titulo: "Dois", inicio: 20, fim: 28, clima: "tenso", instagram: false, data: "" },
];
gravar(join(episodio, "aprovados.json"), { cortes });

for (const corte of cortes) {
  const pasta = join(episodio, `${String(corte.numero).padStart(2, "0")}-${corte.titulo.toLowerCase()}`);
  mkdirSync(join(pasta, "trabalho"), { recursive: true });
  if (corte.numero === 1) writeFileSync(join(pasta, "corte.mp4"), "");
  gravar(join(pasta, "trabalho", "registro.json"), { resultado: "ok", alertas: [] });
  gravar(join(pasta, "trabalho", "montagem.json"), {
    faixas: [[corte.inicio, corte.fim]],
    planos: [],
    legenda: [],
    musica: { arquivo: "m.mp3", volume_db: -26.0, titulo: "", credito },
    encerramento: true,
    versao: 1,
  });
  copyFileSync(post, join(pasta, "post.md"));
}
