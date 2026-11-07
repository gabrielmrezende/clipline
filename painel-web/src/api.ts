export interface Resumo {
  nome: string;
  total: number;
  prontos: number;
  proxima_data: string | null;
  aviso: string | null;
}

export type SeloValor = "erro" | "com alerta" | "sem vídeo final" | "pronto";

export interface Bloco {
  numero: number;
  titulo: string;
  pasta: string;
  clima: string;
  instagram: boolean;
  redes: string[];
  data: string;
  musica: string | null;
  antes: string;
  depois: string;
  alertas: string[];
  video_final: string[];
  tem_guia: boolean;
  erro: string | null;
  avisos_post: string[];
  selo: SeloValor;
}

export interface EpisodioDetalhe {
  resumo: Resumo;
  cortes: Bloco[];
}

export interface ItemCalendario {
  numero: number;
  titulo: string;
  data: string;
  redes: string[];
}

export interface Calendario {
  itens: ItemCalendario[];
  texto: string;
}

export interface CorteDetalhe {
  bloco: Bloco;
  guia: string | null;
  imagens: string[];
}

export interface CamposPost {
  youtube_titulo: string;
  youtube_descricao: string;
  instagram: string;
  tiktok: string;
}

export interface Post {
  campos: CamposPost | null;
  somente_leitura: Record<string, string> | null;
  credito: string | null;
  redes: string[] | null;
  versao: string | null;
  avisos: string[] | null;
  erro: string | null;
}

export class ErroApi extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ErroApi";
    this.status = status;
    this.detail = detail;
  }
}

export function caminhoEpisodio(ep: string): string {
  return `/api/episodios/${encodeURIComponent(ep)}`;
}

export function caminhoCorte(ep: string, n: number | string): string {
  return `${caminhoEpisodio(ep)}/cortes/${encodeURIComponent(String(n))}`;
}

export async function pedir<T>(caminho: string, init?: RequestInit): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(caminho, { credentials: "same-origin", ...init });
  } catch {
    throw new ErroApi(0, "Não consegui falar com o painel. Ele ainda está aberto?");
  }
  if (!resposta.ok) {
    let detail = `Erro ${resposta.status}.`;
    try {
      const corpo = await resposta.json();
      if (corpo && typeof corpo.detail === "string") detail = corpo.detail;
    } catch {
      /* corpo sem JSON */
    }
    if (resposta.status === 401 && caminho !== "/api/entrar" && location.pathname !== "/entrar") {
      location.assign("/entrar");
    }
    throw new ErroApi(resposta.status, detail);
  }
  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

export function enviarJson<T>(caminho: string, metodo: string, corpo: unknown): Promise<T> {
  return pedir<T>(caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
}
