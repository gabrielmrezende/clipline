import { CSSProperties, MouseEvent, useEffect, useRef, useState } from "react";
import { Momento, tempoTexto } from "../api";

interface Props {
  /** O <video> do corte na tela agora (ele é trocado quando muda o vídeo ou durante a montagem). */
  video: HTMLVideoElement | null;
  momentos: Momento[];
  /** Põe o player no tempo (em segundos) e dá play. */
  irPara: (segundos: number) => void;
}

interface Trecho {
  chave: string;
  inicio: number;
  fim: number;
  tipo: string;
  fala: string;
  noVideo: boolean;
}

const TIPO: Record<string, string> = { foto: "foto", ia: "imagem de IA", noticia: "notícia" };

/** Os momentos que aparecem na tela, com o tempo depois do ajuste; os descartados ficam de fora. */
function trechos(momentos: Momento[]): Trecho[] {
  return momentos
    .filter((m) => !m.descartar && m.inicio_tela !== null)
    .map((m) => {
      const inicio = m.inicio_tela ?? m.inicio;
      const fim = Math.max(m.fim_tela ?? m.fim, inicio + 0.5);
      return { chave: m.chave, inicio, fim, tipo: m.tipo, fala: m.fala, noVideo: Boolean(m.no_video) };
    });
}

/**
 * A linha do corte: uma régua com o tempo do vídeo, os trechos onde entram as imagens e a cabeça
 * de leitura acompanhando o player. Clicar num trecho (ou na régua) leva o player até lá.
 */
export function LinhaDoCorte({ video, momentos, irPara }: Props) {
  const [duracao, setDuracao] = useState(0);
  const [agora, setAgora] = useState<string | null>(null);
  const cabeca = useRef<HTMLDivElement>(null);
  const lista = trechos(momentos);
  const listaRef = useRef(lista);
  listaRef.current = lista;
  const duracaoRef = useRef(0);

  useEffect(() => {
    if (!video) return;
    let quadro = 0;
    let ultimo: string | null = null;

    function medirDuracao() {
      const d = video && Number.isFinite(video.duration) ? video.duration : 0;
      if (d > 0 && d !== duracaoRef.current) {
        duracaoRef.current = d;
        setDuracao(d);
      }
    }
    function posicionar() {
      const d = duracaoRef.current;
      if (!video || d <= 0) return;
      const t = video.currentTime;
      cabeca.current?.style.setProperty("--pos", String(Math.min(1, Math.max(0, t / d))));
      const dentro = listaRef.current.find((x) => t >= x.inicio && t < x.fim)?.chave ?? null;
      if (dentro !== ultimo) {
        ultimo = dentro;
        setAgora(dentro);
      }
    }
    // Tocando: acompanha quadro a quadro; parado: só nos eventos do player.
    function andar() {
      posicionar();
      quadro = requestAnimationFrame(andar);
    }
    function tocar() {
      cancelAnimationFrame(quadro);
      quadro = requestAnimationFrame(andar);
    }
    function parar() {
      cancelAnimationFrame(quadro);
      posicionar();
    }
    function carregou() {
      medirDuracao();
      posicionar();
    }

    carregou();
    video.addEventListener("loadedmetadata", carregou);
    video.addEventListener("durationchange", carregou);
    video.addEventListener("timeupdate", posicionar);
    video.addEventListener("seeked", posicionar);
    video.addEventListener("play", tocar);
    video.addEventListener("pause", parar);
    video.addEventListener("ended", parar);
    if (!video.paused) tocar();
    return () => {
      cancelAnimationFrame(quadro);
      video.removeEventListener("loadedmetadata", carregou);
      video.removeEventListener("durationchange", carregou);
      video.removeEventListener("timeupdate", posicionar);
      video.removeEventListener("seeked", posicionar);
      video.removeEventListener("play", tocar);
      video.removeEventListener("pause", parar);
      video.removeEventListener("ended", parar);
    };
  }, [video]);

  if (duracao <= 0 || lista.length === 0) return null;

  function clicarNaRegua(e: MouseEvent<HTMLDivElement>) {
    const caixa = e.currentTarget.getBoundingClientRect();
    if (caixa.width <= 0) return;
    irPara(((e.clientX - caixa.left) / caixa.width) * duracao);
  }

  const passo = `${Math.max(1, (10 / duracao) * 100)}%`;

  return (
    <div className="linha-do-corte">
      <div className="linha-trilho" style={{ "--passo": passo } as CSSProperties} onClick={clicarNaRegua}>
        {lista.map((x, i) => (
          <button
            key={x.chave}
            type="button"
            className={["linha-trecho", x.noVideo ? "" : "fora", agora === x.chave ? "agora" : ""]
              .filter(Boolean)
              .join(" ")}
            style={
              {
                left: `${(x.inicio / duracao) * 100}%`,
                width: `${((x.fim - x.inicio) / duracao) * 100}%`,
                "--i": i,
              } as CSSProperties
            }
            aria-label={`Imagem em ${tempoTexto(x.inicio)}: ${TIPO[x.tipo] ?? x.tipo}${x.noVideo ? "" : ", fora do vídeo"}`}
            title={x.fala}
            onClick={(e) => {
              e.stopPropagation();
              irPara(x.inicio);
            }}
          />
        ))}
        <div className="linha-cabeca" ref={cabeca} aria-hidden="true" />
      </div>
      <div className="linha-tempos" aria-hidden="true">
        <span>0:00</span>
        <span>{tempoTexto(duracao)}</span>
      </div>
    </div>
  );
}
