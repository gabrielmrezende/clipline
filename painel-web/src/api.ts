export interface Resumo {
  nome: string;
  total: number;
  prontos: number;
  proxima_data: string | null;
  aviso: string | null;
}

export type SeloValor =
  | "erro"
  | "com alerta"
  | "sem vídeo final"
  | "vídeo final desatualizado"
  | "pronto";

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
  video_final_desatualizado: boolean;
  montando: boolean;
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

async function buscar(caminho: string, init?: RequestInit): Promise<Response> {
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
  return resposta;
}

export async function pedir<T>(caminho: string, init?: RequestInit): Promise<T> {
  const resposta = await buscar(caminho, init);
  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

export async function pedirBlob(caminho: string, init?: RequestInit): Promise<Blob> {
  return (await buscar(caminho, init)).blob();
}

export function enviarJson<T>(caminho: string, metodo: string, corpo: unknown): Promise<T> {
  return pedir<T>(caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
}

export interface FaixaEpisodio {
  arquivo: string;
  titulo: string;
  clima: string;
  duracao: number;
  motivo: string;
}

export interface FaixaBiblioteca {
  arquivo: string;
  titulo: string;
  duracao: number;
}

export interface ListaMusicas {
  do_episodio: FaixaEpisodio[];
  biblioteca: Record<string, FaixaBiblioteca[]>;
  avisos: string[];
}

export interface MusicaResumo {
  arquivo: string;
  titulo: string;
  volume_db: number;
}

export type EstadoPedido = "na fila" | "montando" | "pronto" | "erro";

export interface Pedido {
  id: string;
  episodio: string;
  numero: number;
  arquivo: string;
  volume_db: number;
  estado: EstadoPedido;
  mensagem: string;
  avisos: string[];
  anterior: MusicaResumo | null;
  /** Segundos desde 1970 (time.time() do painel). */
  criado: number;
  terminado: number | null;
  /** "musica", "fotos" ou "ia". */
  tipo?: string;
  cortes?: number[];
  progresso?: string;
}

export interface MusicaDoCorte {
  atual: MusicaResumo | null;
  anterior: MusicaResumo | null;
  pedido: Pedido | null;
}

export interface Candidata {
  titulo: string | null;
  miniatura: string;
  autor: string | null;
  licenca: string | null;
  pagina: string | null;
  largura: number | null;
  altura: number | null;
}

export interface VersaoIa {
  arquivo: string;
  versao: number | null;
  provedor: string;
  data: string;
}

export interface Momento {
  chave: string;
  inicio: number;
  fim: number;
  fala: string;
  tipo: "foto" | "ia" | "noticia" | string;
  nome: string;
  busca: string;
  titulo: string;
  veiculo: string;
  data: string;
  prompt: string;
  aprovado: boolean;
  descartar: boolean;
  motivo: string;
  candidatas: Candidata[];
  escolhas: number[];
  fotos_prontas: string[];
  ia: VersaoIa[];
  pessoa_citada: string | null;
}

export interface ListaMomentos {
  versao: string;
  momentos: Momento[];
  /** Glossário ilegível: o painel não aprova nem gera, e a pessoa citada fica desconhecida. */
  aviso_glossario?: string | null;
}

export interface RespostaMomento {
  momento: Momento;
  versao: string;
}

export interface AlteracaoMomento {
  tipo?: string;
  escolhas?: number[];
  prompt?: string;
  aprovado?: boolean;
  descartar?: boolean;
}

export interface ResumoFotos {
  fotos: number;
  megabytes: number;
  origem: string;
  avisos: string[];
}

export interface ItemIa {
  corte: number;
  chave: string;
}

export interface OrcamentoIa {
  imagens: number;
  provedor: string;
  modelo: string;
  custo_usd: number;
  /** As imagens contadas: o POST de gerar manda exatamente esta lista, a que o dono confirmou. */
  itens: ItemIa[];
}

export interface ConfigImagens {
  provedor: string;
  provedores: Record<string, { modelo?: string; qualidade?: string; preco_usd?: number }>;
  chaves: Record<string, boolean>;
}

/** Texto do detail do 409 do PUT quando o Claude regravou o pedidos.json. */
export const PEDIDOS_MUDOU = "O pedidos.json mudou desde que você abriu.";

export const urlImagem = (ep: string, n: number | string, arquivo: string): string =>
  `${caminhoCorte(ep, n)}/imagens/${encodeURIComponent(arquivo)}`;

const caminhoMomento = (ep: string, n: number | string, chave: string): string =>
  `${caminhoCorte(ep, n)}/momentos/${encodeURIComponent(chave)}`;

export const lerMomentos = (ep: string, n: number | string) =>
  pedir<ListaMomentos>(`${caminhoCorte(ep, n)}/momentos`);

export const alterarMomento = (
  ep: string,
  n: number | string,
  chave: string,
  versao: string,
  alteracao: AlteracaoMomento,
) => enviarJson<RespostaMomento>(caminhoMomento(ep, n, chave), "PUT", { versao, ...alteracao });

export const buscarOutras = (ep: string, n: number | string, chave: string, versao: string, busca: string) =>
  enviarJson<RespostaMomento>(`${caminhoMomento(ep, n, chave)}/buscar`, "POST", { versao, busca });

/** Corpo dos POSTs que baixam ou custam: sem JSON, o servidor recusa (uma página qualquer não dispara o pedido). */
const CONFIRMADO = { confirmado: true };

export const resumoDeFotos = (ep: string, n: number | string) =>
  pedir<ResumoFotos>(`${caminhoCorte(ep, n)}/fotos/resumo`);

export const baixarFotos = (ep: string, n: number | string) =>
  enviarJson<Pedido>(`${caminhoCorte(ep, n)}/fotos`, "POST", CONFIRMADO);

export const orcamentoDeIa = (ep: string, n: number | string) =>
  pedir<OrcamentoIa>(`${caminhoCorte(ep, n)}/ia/orcamento`);

export const gerarImagensIa = (ep: string, n: number | string, itens: ItemIa[]) =>
  enviarJson<Pedido>(`${caminhoCorte(ep, n)}/ia`, "POST", { itens });

export const gerarDeNovoIa = (ep: string, n: number | string, chave: string) =>
  enviarJson<Pedido>(`${caminhoMomento(ep, n, chave)}/ia`, "POST", CONFIRMADO);

export const configuracaoDeImagens = () => pedir<ConfigImagens>("/api/configuracoes/imagens");

export const resumoDeFotosDoEpisodio = (ep: string) => pedir<ResumoFotos>(`${caminhoEpisodio(ep)}/fotos/resumo`);

export const baixarFotosDoEpisodio = (ep: string) =>
  enviarJson<Pedido>(`${caminhoEpisodio(ep)}/fotos`, "POST", CONFIRMADO);

export const orcamentoDeIaDoEpisodio = (ep: string) => pedir<OrcamentoIa>(`${caminhoEpisodio(ep)}/ia/orcamento`);

export const gerarImagensIaDoEpisodio = (ep: string, itens: ItemIa[]) =>
  enviarJson<Pedido>(`${caminhoEpisodio(ep)}/ia`, "POST", { itens });

export const gravarConfiguracaoDeImagens = (provedor: string, provedores: ConfigImagens["provedores"]) =>
  enviarJson<ConfigImagens>("/api/configuracoes/imagens", "PUT", { provedor, provedores });

export const listarTarefas = () => pedir<Pedido[]>("/api/tarefas");

export const consultarTarefa = (id: string) => pedir<Pedido>(`/api/tarefas/${encodeURIComponent(id)}`);

export function plural(n: number, singular: string, pluralTexto: string): string {
  return `${n} ${n === 1 ? singular : pluralTexto}`;
}

/** 12,3 MB (vírgula decimal, uma casa). */
export function formatarMb(mb: number): string {
  return `${mb.toFixed(1).replace(".", ",")} MB`;
}

/** ~US$ 0,10 (vírgula decimal, duas casas). */
export function formatarDolar(usd: number): string {
  return `~US$ ${usd.toFixed(2).replace(".", ",")}`;
}

export function tempoTexto(segundos: number): string {
  const total = Math.max(0, Math.floor(segundos));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
