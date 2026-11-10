// Cria o episódio falso usado pelo teste de fumaça em e2e/.cortes/.
import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const aqui = dirname(fileURLToPath(import.meta.url));
const raiz = join(aqui, ".cortes");
const post = join(aqui, "..", "..", "tests", "dados_post_corte1.md");
const musicasReais = join(aqui, "..", "..", "musicas");
const musicas = join(aqui, ".musicas");
const ICE_FLOW = "tenso/Ice Flow.mp3";
const NO_EPISODIO = ["tenso/Pyro Flow.mp3", "tenso/Jerry Five.mp3"];

const gravar = (caminho, dados) => writeFileSync(caminho, JSON.stringify(dados, null, 2), "utf-8");

// Biblioteca de músicas de teste: cópia do catálogo real + mp3 vazios (o uso.json real não é tocado).
rmSync(musicas, { recursive: true, force: true });
mkdirSync(join(musicas, "tenso"), { recursive: true });
copyFileSync(join(musicasReais, "catalogo.json"), join(musicas, "catalogo.json"));
const catalogo = JSON.parse(readFileSync(join(musicas, "catalogo.json"), "utf-8"));
const iceFlow = catalogo.find((f) => f.arquivo === ICE_FLOW);
for (const arquivo of [ICE_FLOW, ...NO_EPISODIO]) {
  if (!catalogo.some((f) => f.arquivo === arquivo)) throw new Error(`faixa fora do catálogo: ${arquivo}`);
  writeFileSync(join(musicas, arquivo), "");
}
const credito = iceFlow.credito;

rmSync(raiz, { recursive: true, force: true });
const episodio = join(raiz, "Entre Assuntos 99 - Convidado (teste)");
mkdirSync(join(episodio, "transcricao"), { recursive: true });

const palavras = Array.from({ length: 30 }, (_, i) => ({ texto: `p${i}`, inicio: i - 0.4, fim: i + 0.4 }));
gravar(join(episodio, "transcricao", "palavras.json"), palavras);

// Imagem minúscula embutida: o navegador não busca nada na internet para as candidatas.
const PIXEL =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
const candidata = (i) => ({
  titulo: `File:Foto ${i}.jpg`,
  pagina: `https://commons.wikimedia.org/wiki/File:Foto_${i}.jpg`,
  miniatura: PIXEL,
  largura: 4000,
  altura: 3000,
  autor: `Autor ${i}`,
  licenca: "CC BY 4.0",
});
// Corte 3: usado só pelo teste das imagens (a música e a fumaça usam os cortes 1 e 2).
const pedidosDoCorte3 = {
  momentos: [
    {
      inicio: 6.0, fim: 9.0, fala: "o país parou", tipo: "ia", nome: "País parado",
      prompt: "Ruas vazias ao amanhecer, estilo documental", aprovado: false,
    },
    {
      inicio: 10.0, fim: 13.0, fala: "o ministro disse", tipo: "foto", nome: "Ministro",
      busca: "ministro da fazenda", candidatas: [candidata(1), candidata(2)], escolhas: [],
    },
  ],
};

const cortes = [
  { numero: 1, titulo: "Um", inicio: 10, fim: 20, clima: "tenso", instagram: false, data: "" },
  { numero: 2, titulo: "Dois", inicio: 20, fim: 28, clima: "tenso", instagram: false, data: "" },
  { numero: 3, titulo: "Tres", inicio: 5, fim: 15, clima: "tenso", instagram: false, data: "" },
];
gravar(join(episodio, "aprovados.json"), { cortes });
gravar(join(episodio, "musicas-do-episodio.json"), {
  faixas: NO_EPISODIO.map((arquivo) => ({ arquivo, motivo: "teste" })),
});

for (const corte of cortes) {
  const pasta = join(episodio, `${String(corte.numero).padStart(2, "0")}-${corte.titulo.toLowerCase()}`);
  mkdirSync(join(pasta, "trabalho"), { recursive: true });
  if (corte.numero === 1) writeFileSync(join(pasta, "corte.mp4"), "");
  gravar(join(pasta, "trabalho", "registro.json"), { resultado: "ok", alertas: [] });
  gravar(join(pasta, "trabalho", "montagem.json"), {
    faixas: [[corte.inicio, corte.fim]],
    planos: [],
    legenda: [],
    musica: { arquivo: join(musicas, ICE_FLOW), volume_db: -26.0, titulo: "Ice Flow", credito },
    encerramento: true,
    versao: 1,
  });
  copyFileSync(post, join(pasta, "post.md"));
  if (corte.numero === 3) gravar(join(pasta, "trabalho", "pedidos.json"), pedidosDoCorte3);
}
