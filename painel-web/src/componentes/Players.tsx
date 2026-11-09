import { RefObject, useState } from "react";
import { caminhoCorte } from "../api";

interface Props {
  ep: string;
  n: number | string;
  videoFinal: string[];
  /** Dá acesso ao <video> (tempo atual para a prévia da música). */
  videoRef?: RefObject<HTMLVideoElement>;
  /** Muda quando o corte.mp4 foi refeito, para o navegador não usar o cache. */
  versao?: string | null;
}

export function Players({ ep, n, videoFinal, videoRef, versao }: Props) {
  const [atual, setAtual] = useState<string | null>(null);
  const base = caminhoCorte(ep, n);
  const escolhido = atual !== null && videoFinal.includes(atual) ? atual : null;
  const src =
    escolhido === null
      ? `${base}/video${versao ? `?v=${encodeURIComponent(versao)}` : ""}`
      : `${base}/video-final/${encodeURIComponent(escolhido)}`;
  return (
    <section aria-label="Vídeos" className="players">
      <div className="botoes-video">
        <button type="button" aria-pressed={escolhido === null} onClick={() => setAtual(null)}>
          Corte
        </button>
        {videoFinal.map((arquivo) => (
          <button
            key={arquivo}
            type="button"
            aria-pressed={escolhido === arquivo}
            onClick={() => setAtual(arquivo)}
          >
            {arquivo}
          </button>
        ))}
      </div>
      <video key={src} ref={videoRef} src={src} controls playsInline preload="metadata" />
    </section>
  );
}
