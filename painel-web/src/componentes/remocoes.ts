import { useEffect, useState } from "react";
import { caminhoCorte, pedir } from "../api";

/** Um ponto do corte.mp4 onde a limpeza tirou alguma coisa (pausa, hesitação, repetição). */
export interface Remocao {
  /** No tempo do corte.mp4, em segundos. */
  tempo: number;
  /** Quanto foi tirado, em segundos. */
  duracao: number;
  /** "pausa", "hesitação", "repetição", "hesitação e repetição"... ou "trecho removido". */
  motivo: string;
  /** As palavras tiradas, se houver. */
  texto: string;
  /** Onde começa o trecho tirado, no tempo do episódio. */
  episodio: number;
}

export interface ListaRemocoes {
  remocoes: Remocao[];
  removido: number;
  avisos: string[];
}

export const lerRemocoes = (ep: string, n: number | string) =>
  pedir<ListaRemocoes>(`${caminhoCorte(ep, n)}/remocoes`);

/** As remoções do corte; lê de novo quando muda a versão do vídeo. Sem resposta, fica sem remoções. */
export function useRemocoes(ep: string | undefined, n: number | string | undefined, versao?: string | null) {
  const [lista, setLista] = useState<ListaRemocoes | null>(null);
  useEffect(() => {
    setLista(null);
    if (!ep || n === undefined || n === "") return;
    let vivo = true;
    lerRemocoes(ep, n)
      .then((dados) => vivo && setLista(dados))
      .catch(() => {
        /* as marcas são um apoio: sem elas, a linha mostra só as imagens */
      });
    return () => {
      vivo = false;
    };
  }, [ep, n, versao]);
  return lista;
}

/** "0,4 s", "1,2 s", "12 s". */
export function segundosTexto(segundos: number): string {
  const arredondado = segundos >= 10 ? Math.round(segundos) : Math.round(segundos * 10) / 10;
  return `${String(arredondado).replace(".", ",")} s`;
}

/** "Hesitação: “hum”", "Pausa", "Trecho removido". */
export function descreverRemocao(r: Remocao): string {
  const motivo = r.motivo.charAt(0).toUpperCase() + r.motivo.slice(1);
  return r.texto ? `${motivo}: “${r.texto}”` : motivo;
}

/** Pausa tirada é cinza na linha; fala tirada (hesitação, repetição, trecho) é âmbar. */
export const ehPausa = (r: Remocao) => r.motivo === "pausa";
