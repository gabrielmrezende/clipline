import { useState } from "react";
import { caminhoCorte } from "../api";

interface Props {
  ep: string;
  n: number | string;
  videoFinal: string[];
}

export function Players({ ep, n, videoFinal }: Props) {
  const [atual, setAtual] = useState<string | null>(null);
  const base = caminhoCorte(ep, n);
  const escolhido = atual !== null && videoFinal.includes(atual) ? atual : null;
  const src =
    escolhido === null ? `${base}/video` : `${base}/video-final/${encodeURIComponent(escolhido)}`;
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
      <video key={src} src={src} controls playsInline preload="metadata" />
    </section>
  );
}
