import type { SeloValor } from "../api";

const MAPA: Record<SeloValor, { icone: string; classe: string }> = {
  erro: { icone: "✕", classe: "selo-erro" },
  "com alerta": { icone: "⚠", classe: "selo-alerta" },
  "sem vídeo final": { icone: "○", classe: "selo-cinza" },
  "vídeo final desatualizado": { icone: "↻", classe: "selo-alerta" },
  pronto: { icone: "✓", classe: "selo-pronto" },
};

export function Selo({ valor }: { valor: SeloValor }) {
  const { icone, classe } = MAPA[valor];
  return (
    <span className={`selo ${classe}`}>
      <span aria-hidden="true">{icone}</span> <span>{valor}</span>
    </span>
  );
}
