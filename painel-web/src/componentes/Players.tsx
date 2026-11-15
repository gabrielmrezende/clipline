import "./monitor.css";
import { CSSProperties, MutableRefObject, Ref, useCallback, useEffect, useId, useRef, useState } from "react";
import { caminhoCorte } from "../api";
import { REDES, Rede, areasDaRede } from "./areasSeguras";
import { Dialogo } from "./Dialogo";

interface Props {
  ep: string;
  n: number | string;
  videoFinal: string[];
  /** Dá acesso ao <video> (tempo atual para a prévia da música). */
  videoRef?: Ref<HTMLVideoElement>;
  /** Muda quando o corte.mp4 foi refeito, para o navegador não usar o cache. */
  versao?: string | null;
  /** Há troca de música em andamento: o <video> do corte sai da tela para soltar o arquivo. */
  montando?: boolean;
}

export const VELOCIDADES = [0.5, 0.75, 1, 1.25, 1.5, 2];
/** Um quadro a 30 fps. */
export const QUADRO = 1 / 30;
const SALTO_CURTO = 5;
const SALTO_LONGO = 10;
const DURACAO_AVISO_MS = 900;
const CHAVE_AREAS = "clipline.player.areas";

export type Acao =
  | { tipo: "alternar" }
  | { tipo: "pular"; segundos: number }
  | { tipo: "quadro"; passos: number }
  | { tipo: "velocidade"; passo: number }
  | { tipo: "inicio" }
  | { tipo: "fim" }
  | { tipo: "areas" }
  | { tipo: "ajuda" };

const TECLAS: Record<string, Acao> = {
  " ": { tipo: "alternar" },
  k: { tipo: "alternar" },
  j: { tipo: "pular", segundos: -SALTO_LONGO },
  l: { tipo: "pular", segundos: SALTO_LONGO },
  ArrowLeft: { tipo: "pular", segundos: -SALTO_CURTO },
  ArrowRight: { tipo: "pular", segundos: SALTO_CURTO },
  ",": { tipo: "quadro", passos: -1 },
  ".": { tipo: "quadro", passos: 1 },
  "<": { tipo: "velocidade", passo: -1 },
  ">": { tipo: "velocidade", passo: 1 },
  Home: { tipo: "inicio" },
  End: { tipo: "fim" },
  a: { tipo: "areas" },
  "?": { tipo: "ajuda" },
};

/** A ajuda do "?": a mesma tabela que os atalhos usam, na ordem em que aparece. */
const AJUDA: { teclas: string[]; texto: string }[] = [
  { teclas: ["Espaço", "K"], texto: "Tocar ou pausar" },
  { teclas: ["J", "L"], texto: "Voltar ou avançar 10 s" },
  { teclas: ["←", "→"], texto: "Voltar ou avançar 5 s" },
  { teclas: [",", "."], texto: "Quadro anterior ou seguinte (pausa)" },
  { teclas: ["<", ">"], texto: "Mais devagar ou mais rápido (0,5x a 2x)" },
  { teclas: ["Home", "End"], texto: "Começo ou fim do vídeo" },
  { teclas: ["A"], texto: "Trocar as áreas da rede (TikTok, Shorts, Reels)" },
  { teclas: ["?"], texto: "Abrir esta ajuda" },
];

/** O nome falado das teclas de símbolo: com a pontuação no padrão, o leitor de tela pula "," e ".". */
const NOME_DA_TECLA: Record<string, string> = {
  "←": "seta para a esquerda",
  "→": "seta para a direita",
  ",": "vírgula",
  ".": "ponto",
  "<": "menor que",
  ">": "maior que",
  "?": "interrogação",
};

const INTERATIVOS = "button, a[href], summary, [role='button'], [role='tab'], [role='radio'], [role='checkbox']";
const COM_SETAS = "[role='tab'], [role='radio'], [role='slider'], [role='listbox'], [role='menuitem'], [role='option']";

/** O que a tecla faz no player, ou null quando ela é de outro lugar (um campo, um botão, um diálogo). */
export function acaoDaTecla(e: KeyboardEvent): Acao | null {
  if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return null;
  const chave = e.key.length === 1 && e.key !== " " ? e.key.toLowerCase() : e.key;
  const acao = TECLAS[chave] ?? TECLAS[e.key];
  if (!acao) return null;
  const alvo = e.target instanceof Element ? e.target : null;
  if (alvo) {
    if (alvo.closest("input, textarea, select, [contenteditable=''], [contenteditable='true']")) return null;
    if (alvo.closest("dialog")) return null;
    // Espaço num botão é clicar nele; as setas e o espaço do <video> com foco são do próprio player nativo.
    if (e.key === " " && (alvo.closest(INTERATIVOS) || alvo instanceof HTMLMediaElement)) return null;
    if (e.key.startsWith("Arrow") && (alvo.closest(COM_SETAS) || alvo instanceof HTMLMediaElement)) return null;
  }
  if (document.querySelector("dialog[open]")) return null; // uma confirmação aberta: nada muda atrás dela
  return acao;
}

export const formatarVelocidade = (v: number) => `${String(v).replace(".", ",")}x`;

function lerAreas(): Rede | "" {
  try {
    const valor = localStorage.getItem(CHAVE_AREAS) ?? "";
    return REDES.some((r) => r.id === valor) ? (valor as Rede) : "";
  } catch {
    return "";
  }
}

function gravarAreas(valor: Rede | "") {
  try {
    if (valor) localStorage.setItem(CHAVE_AREAS, valor);
    else localStorage.removeItem(CHAVE_AREAS);
  } catch {
    /* sem armazenamento (janela anônima): a escolha vale só nesta tela */
  }
}

function atribuir<T>(ref: Ref<T> | undefined, valor: T | null) {
  if (typeof ref === "function") ref(valor);
  else if (ref) (ref as MutableRefObject<T | null>).current = valor;
}

function SobreposicaoAreas({ rede }: { rede: Rede }) {
  const { cobertas, livre } = areasDaRede(rede);
  const nome = REDES.find((r) => r.id === rede)?.nome ?? rede;
  const pos = (r: { x: number; y: number; largura: number; altura: number }) =>
    ({ left: `${r.x}%`, top: `${r.y}%`, width: `${r.largura}%`, height: `${r.altura}%` }) as CSSProperties;
  return (
    <div className="areas-rede" aria-hidden="true" data-rede={rede}>
      {cobertas.map((c) => (
        // A coluna dos botões é estreita: o rótulo dela corre na vertical (a tela é 9:16).
        <span
          key={c.rotulo}
          className={c.largura * 9 < c.altura * 16 ? "area-coberta em-pe" : "area-coberta"}
          style={pos(c)}
        >
          <span className="area-rotulo">{`${nome}: ${c.rotulo}`}</span>
        </span>
      ))}
      <span className="area-livre" style={pos(livre)} />
    </div>
  );
}

export function Players({ ep, n, videoFinal, videoRef, versao, montando = false }: Props) {
  const [atual, setAtual] = useState<string | null>(null);
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const [velocidade, setVelocidade] = useState(1);
  const [areas, setAreas] = useState<Rede | "">(lerAreas);
  const [ajuda, setAjuda] = useState(false);
  const [aviso, setAviso] = useState({ texto: "", vez: 0 });
  const origemAjuda = useRef<Element | null>(null);
  const id = useId();
  const base = caminhoCorte(ep, n);
  const escolhido = atual !== null && videoFinal.includes(atual) ? atual : null;
  const src =
    escolhido === null
      ? `${base}/video${versao ? `?v=${encodeURIComponent(versao)}` : ""}`
      : `${base}/video-final/${encodeURIComponent(escolhido)}`;

  const refDoVideo = useCallback(
    (el: HTMLVideoElement | null) => {
      setVideo(el);
      atribuir(videoRef, el);
    },
    [videoRef],
  );

  // A velocidade vale para o vídeo da vez: trocar de vídeo (ou recarregar o corte) não volta a 1x.
  useEffect(() => {
    if (!video) return;
    const aplicar = () => {
      video.defaultPlaybackRate = velocidade;
      video.playbackRate = velocidade;
    };
    aplicar();
    video.addEventListener("loadedmetadata", aplicar);
    return () => video.removeEventListener("loadedmetadata", aplicar);
  }, [video, velocidade]);

  useEffect(() => {
    if (!aviso.texto) return;
    const t = setTimeout(() => setAviso((a) => (a.vez === aviso.vez ? { ...a, texto: "" } : a)), DURACAO_AVISO_MS);
    return () => clearTimeout(t);
  }, [aviso]);

  const avisar = useCallback((texto: string) => setAviso((a) => ({ texto, vez: a.vez + 1 })), []);

  const mudarVelocidade = useCallback(
    (v: number) => {
      setVelocidade(v);
      avisar(`Velocidade ${formatarVelocidade(v)}`);
    },
    [avisar],
  );

  const mudarAreas = useCallback(
    (valor: Rede | "") => {
      setAreas(valor);
      gravarAreas(valor);
      avisar(valor ? `Áreas do ${REDES.find((r) => r.id === valor)?.nome}` : "Áreas desligadas");
    },
    [avisar],
  );

  const abrirAjuda = useCallback(() => {
    origemAjuda.current = document.activeElement;
    setAjuda(true);
  }, []);

  const estado = useRef({ video, velocidade, areas, mudarVelocidade, mudarAreas, abrirAjuda, avisar });
  estado.current = { video, velocidade, areas, mudarVelocidade, mudarAreas, abrirAjuda, avisar };

  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      const acao = acaoDaTecla(e);
      if (!acao) return;
      const s = estado.current;
      if (acao.tipo === "ajuda") {
        e.preventDefault();
        s.abrirAjuda();
        return;
      }
      if (acao.tipo === "areas") {
        e.preventDefault();
        const ordem: (Rede | "")[] = ["", ...REDES.map((r) => r.id)];
        s.mudarAreas(ordem[(ordem.indexOf(s.areas) + 1) % ordem.length]);
        return;
      }
      if (acao.tipo === "velocidade") {
        e.preventDefault();
        const i = VELOCIDADES.indexOf(s.velocidade);
        const novo = VELOCIDADES[Math.min(VELOCIDADES.length - 1, Math.max(0, i + acao.passo))];
        if (novo !== s.velocidade) s.mudarVelocidade(novo);
        return;
      }
      const v = s.video;
      if (!v) return; // montando: não há vídeo do corte na tela
      e.preventDefault();
      const duracao = Number.isFinite(v.duration) ? v.duration : Infinity;
      const ir = (t: number) => {
        v.currentTime = Math.min(duracao, Math.max(0, t));
      };
      switch (acao.tipo) {
        case "alternar":
          if (v.paused) {
            const tocando = v.play();
            if (tocando && typeof tocando.catch === "function") tocando.catch(() => {});
          } else {
            v.pause();
          }
          break;
        case "pular":
          ir(v.currentTime + acao.segundos);
          s.avisar(`${acao.segundos > 0 ? "+" : "−"}${Math.abs(acao.segundos)} s`);
          break;
        case "quadro":
          v.pause();
          ir(v.currentTime + acao.passos * QUADRO);
          s.avisar(`${acao.passos > 0 ? "+" : "−"}1 quadro`);
          break;
        case "inicio":
          ir(0);
          break;
        case "fim":
          ir(duracao);
          break;
      }
    }
    document.addEventListener("keydown", aoTeclar);
    return () => document.removeEventListener("keydown", aoTeclar);
  }, []);

  const semVideo = montando && escolhido === null;

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
      <div className="tela">
        {semVideo ? (
          <p role="status" className="montando-corte">
            Montando o corte…
          </p>
        ) : (
          <video
            key={src}
            ref={refDoVideo}
            src={src}
            controls
            playsInline
            preload="metadata"
            aria-keyshortcuts="Space K J L ArrowLeft ArrowRight , . < > Home End A ?"
          />
        )}
        {areas && !semVideo ? <SobreposicaoAreas rede={areas} /> : null}
        <p className={aviso.texto ? "aviso-player visivel" : "aviso-player"} role="status" aria-live="polite">
          {aviso.texto}
        </p>
      </div>
      <div className="barra-player">
        <label className="controle-player">
          <span>Velocidade</span>
          <select value={velocidade} onChange={(e) => mudarVelocidade(Number(e.target.value))}>
            {VELOCIDADES.map((v) => (
              <option key={v} value={v}>
                {formatarVelocidade(v)}
              </option>
            ))}
          </select>
        </label>
        <label className="controle-player">
          <span>Áreas da rede</span>
          <select value={areas} onChange={(e) => mudarAreas(e.target.value as Rede | "")}>
            <option value="">Desligadas</option>
            {REDES.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nome}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="botao-atalhos"
          aria-label="Atalhos do teclado"
          aria-keyshortcuts="?"
          title="Atalhos do teclado (?)"
          onClick={abrirAjuda}
        >
          ?
        </button>
      </div>
      {areas ? <p className="nota-areas">Áreas aproximadas: a interface de cada rede muda; confira no app.</p> : null}
      {ajuda ? (
        <Dialogo
          tituloId={`${id}-ajuda`}
          aoFechar={() => setAjuda(false)}
          origem={origemAjuda.current}
          className="dialogo-ajuda"
        >
          <div className="dialogo-cabeca">
            <h2 id={`${id}-ajuda`} className="dialogo-titulo">
              Atalhos do player
            </h2>
            <button type="button" className="discreto" onClick={() => setAjuda(false)}>
              Fechar
            </button>
          </div>
          <dl className="atalhos">
            {AJUDA.map((a) => (
              <div key={a.texto} className="atalho">
                <dt>
                  {a.teclas.map((t) => (
                    <kbd key={t}>
                      {NOME_DA_TECLA[t] ? (
                        <>
                          <span aria-hidden="true">{t}</span>
                          <span className="so-leitor">{NOME_DA_TECLA[t]}</span>
                        </>
                      ) : (
                        t
                      )}
                    </kbd>
                  ))}
                </dt>
                <dd>{a.texto}</dd>
              </div>
            ))}
          </dl>
          <p className="suave-bloco">Os atalhos não valem enquanto você digita num campo.</p>
        </Dialogo>
      ) : null}
    </section>
  );
}
