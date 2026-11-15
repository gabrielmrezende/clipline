// Onde a interface de cada rede cobre o vídeo vertical (1080x1920), para ver se a legenda ou uma imagem some
// atrás dos botões. São medidas APROXIMADAS, tiradas dos guias públicos de áreas seguras (2025-2026) e das
// telas dos apps; cada rede muda a interface de tempos em tempos e os guias de anúncio pedem margens maiores.
// Servem para revisar, não como regra fixa: em caso de dúvida, confira no app.

export type Rede = "tiktok" | "shorts" | "reels";

export const REDES: { id: Rede; nome: string }[] = [
  { id: "tiktok", nome: "TikTok" },
  { id: "shorts", nome: "Shorts" },
  { id: "reels", nome: "Reels" },
];

/** Margens em pixels de um quadro 1080x1920. A coluna da direita (curtir, comentar...) começa em `colunaDe`. */
interface Margens {
  topo: number;
  base: number;
  direita: number;
  esquerda: number;
  colunaDe: number;
}

const LARGURA = 1080;
const ALTURA = 1920;

const MARGENS: Record<Rede, Margens> = {
  tiktok: { topo: 130, base: 480, direita: 150, esquerda: 40, colunaDe: 760 },
  shorts: { topo: 120, base: 420, direita: 192, esquerda: 48, colunaDe: 780 },
  reels: { topo: 220, base: 420, direita: 130, esquerda: 40, colunaDe: 860 },
};

/** Um retângulo em porcentagem da tela (0 a 100). */
export interface Retangulo {
  x: number;
  y: number;
  largura: number;
  altura: number;
}

export interface AreasDaRede {
  /** Faixas cobertas pela interface da rede, com o que fica ali. */
  cobertas: (Retangulo & { rotulo: string })[];
  /** O retângulo livre: o que fica fora dele pode ser coberto. */
  livre: Retangulo;
}

const px = (valor: number, total: number) => Math.round((valor / total) * 10000) / 100;

export function areasDaRede(rede: Rede): AreasDaRede {
  const m = MARGENS[rede];
  const baseDe = ALTURA - m.base;
  return {
    cobertas: [
      { rotulo: "abas e busca", x: 0, y: 0, largura: 100, altura: px(m.topo, ALTURA) },
      {
        rotulo: "botões",
        x: px(LARGURA - m.direita, LARGURA),
        y: px(m.colunaDe, ALTURA),
        largura: px(m.direita, LARGURA),
        altura: px(baseDe - m.colunaDe, ALTURA),
      },
      { rotulo: "nome, texto e música", x: 0, y: px(baseDe, ALTURA), largura: 100, altura: px(m.base, ALTURA) },
    ],
    livre: {
      x: px(m.esquerda, LARGURA),
      y: px(m.topo, ALTURA),
      largura: px(LARGURA - m.esquerda - m.direita, LARGURA),
      altura: px(baseDe - m.topo, ALTURA),
    },
  };
}
