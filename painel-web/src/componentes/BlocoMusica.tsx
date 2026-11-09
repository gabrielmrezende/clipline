import { useCallback, useEffect, useRef, useState } from "react";
import {
  ErroApi,
  ListaMusicas,
  MusicaDoCorte,
  Pedido,
  caminhoCorte,
  caminhoEpisodio,
  enviarJson,
  pedir,
  pedirBlob,
} from "../api";

interface Props {
  ep: string;
  n: number | string;
  videoFinal: string[];
  tempoDoPlayer: () => number;
  aoTerminar: () => void;
}

const VOLUME_PADRAO = -26;
const ESPERA_MS = 2000;
const CONFIRMACAO =
  "Este corte já tem vídeo final. O vídeo final não muda; você vai precisar refazer no CapCut. Montar mesmo assim?";

function mensagem(x: unknown): string {
  return x instanceof ErroApi ? x.detail : "Erro inesperado.";
}

function tempoTexto(segundos: number): string {
  const total = Math.max(0, Math.floor(segundos));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function srcDaFaixa(arquivo: string): string {
  const i = arquivo.indexOf("/");
  const clima = i < 0 ? "" : arquivo.slice(0, i);
  const nome = i < 0 ? arquivo : arquivo.slice(i + 1);
  return `/api/musicas/${encodeURIComponent(clima)}/${encodeURIComponent(nome)}`;
}

const ativo = (p: Pedido | null) => p !== null && (p.estado === "na fila" || p.estado === "montando");

interface FaixaLinha {
  arquivo: string;
  titulo: string;
  motivo?: string;
}

export function BlocoMusica({ ep, n, videoFinal, tempoDoPlayer, aoTerminar }: Props) {
  const base = caminhoCorte(ep, n);
  const [lista, setLista] = useState<ListaMusicas | null>(null);
  const [musica, setMusica] = useState<MusicaDoCorte | null>(null);
  const [erroLeitura, setErroLeitura] = useState<string | null>(null);
  const [escolhida, setEscolhida] = useState<string | null>(null);
  const [volumeEscolhido, setVolumeEscolhido] = useState<number | null>(null);
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [tick, setTick] = useState(0);
  const [erroPedido, setErroPedido] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [tocando, setTocando] = useState<string | null>(null);
  const [srcAudio, setSrcAudio] = useState<string | null>(null);
  const [previaInicio, setPreviaInicio] = useState<number | null>(null);
  const [gerandoPrevia, setGerandoPrevia] = useState(false);
  const [erroPrevia, setErroPrevia] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const urlPrevia = useRef<string | null>(null);
  const terminados = useRef<Set<string>>(new Set());
  const aoTerminarRef = useRef(aoTerminar);
  aoTerminarRef.current = aoTerminar;

  const atual = musica?.atual ?? null;
  const arquivoEscolhido = escolhida ?? atual?.arquivo ?? null;
  const volume = volumeEscolhido ?? atual?.volume_db ?? VOLUME_PADRAO;
  const ocupado = ativo(pedido) || enviando;

  const lerMusicaDoCorte = useCallback(async () => {
    try {
      const dados = await pedir<MusicaDoCorte>(`${base}/musica`);
      setMusica(dados);
      return dados;
    } catch (x) {
      setErroLeitura(mensagem(x));
      return null;
    }
  }, [base]);

  useEffect(() => {
    let vivo = true;
    setLista(null);
    setMusica(null);
    setErroLeitura(null);
    setPedido(null);
    pedir<ListaMusicas>(`${caminhoEpisodio(ep)}/musicas`)
      .then((d) => vivo && setLista(d))
      .catch((x) => vivo && setErroLeitura(mensagem(x)));
    void lerMusicaDoCorte().then((d) => {
      if (vivo && d && ativo(d.pedido)) setPedido(d.pedido);
    });
    return () => {
      vivo = false;
    };
  }, [ep, lerMusicaDoCorte]);

  useEffect(
    () => () => {
      if (urlPrevia.current) URL.revokeObjectURL(urlPrevia.current);
    },
    [],
  );

  // Consulta o pedido a cada 2 s até ele terminar.
  useEffect(() => {
    if (!pedido) return;
    if (!ativo(pedido)) {
      if (pedido.estado === "pronto" && !terminados.current.has(pedido.id)) {
        terminados.current.add(pedido.id);
        void lerMusicaDoCorte();
        aoTerminarRef.current();
      }
      return;
    }
    let vivo = true;
    const id = setTimeout(() => {
      pedir<Pedido>(`/api/tarefas/${encodeURIComponent(pedido.id)}`)
        .then((novo) => vivo && setPedido(novo))
        .catch(() => vivo && setTick((t) => t + 1));
    }, ESPERA_MS);
    return () => {
      vivo = false;
      clearTimeout(id);
    };
  }, [pedido, tick, lerMusicaDoCorte]);

  function tocar(src: string, chave: string) {
    const el = audio.current;
    if (!el) return;
    el.pause();
    setSrcAudio(src);
    setTocando(chave);
    el.src = src;
    const p = el.play();
    if (p && typeof p.catch === "function") p.catch(() => setTocando(null));
  }

  function alternarFaixa(arquivo: string) {
    if (tocando === arquivo) {
      audio.current?.pause();
      setTocando(null);
      return;
    }
    tocar(srcDaFaixa(arquivo), arquivo);
  }

  async function ouvirPrevia() {
    if (!arquivoEscolhido) return;
    const inicio = tempoDoPlayer();
    setGerandoPrevia(true);
    setErroPrevia(null);
    setPreviaInicio(inicio);
    try {
      const blob = await pedirBlob(`${base}/musica/previa`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ arquivo: arquivoEscolhido, volume_db: volume, inicio }),
      });
      if (urlPrevia.current) URL.revokeObjectURL(urlPrevia.current);
      urlPrevia.current = URL.createObjectURL(blob);
      tocar(urlPrevia.current, "previa");
    } catch (x) {
      setErroPrevia(mensagem(x));
    } finally {
      setGerandoPrevia(false);
    }
  }

  async function enviar(arquivo: string, volume_db: number) {
    setEnviando(true);
    setErroPedido(null);
    try {
      const novo = await enviarJson<Pedido>(`${base}/musica`, "POST", { arquivo, volume_db });
      setPedido(novo);
    } catch (x) {
      setErroPedido(mensagem(x));
    } finally {
      setEnviando(false);
    }
  }

  function montarComEsta() {
    if (!arquivoEscolhido) return;
    if (videoFinal.length > 0 && !window.confirm(CONFIRMACAO)) return;
    void enviar(arquivoEscolhido, volume);
  }

  function linha(f: FaixaLinha, chave: string) {
    const toca = tocando === f.arquivo;
    return (
      <li key={chave} className="faixa">
        <button
          type="button"
          className="faixa-tocar"
          aria-label={`${toca ? "Parar" : "Ouvir"} ${f.titulo}`}
          onClick={() => alternarFaixa(f.arquivo)}
        >
          {toca ? "⏸" : "▶"}
        </button>
        <span className="faixa-nome">
          {f.titulo}
          {f.motivo ? <span className="suave"> · {f.motivo}</span> : null}
        </span>
        <button
          type="button"
          aria-label={`Escolher ${f.titulo}`}
          aria-pressed={arquivoEscolhido === f.arquivo}
          disabled={ocupado}
          onClick={() => setEscolhida(f.arquivo)}
        >
          Escolher
        </button>
      </li>
    );
  }

  const tituloEscolhido =
    lista &&
    (lista.do_episodio.find((f) => f.arquivo === arquivoEscolhido)?.titulo ??
      Object.values(lista.biblioteca)
        .flat()
        .find((f) => f.arquivo === arquivoEscolhido)?.titulo);
  const anterior = musica?.anterior ?? null;
  const textoEstado: Record<Pedido["estado"], string> = {
    "na fila": "Na fila",
    montando: "Montando…",
    pronto: "Pronto: o corte.mp4 foi atualizado.",
    erro: pedido ? `Erro: ${pedido.mensagem}` : "",
  };

  return (
    <section aria-labelledby="titulo-musica" className="bloco-musica">
      <h2 id="titulo-musica">Música</h2>
      {erroLeitura ? (
        <p role="alert" className="mensagem-erro">
          {erroLeitura}
        </p>
      ) : null}
      <p>
        <strong>Agora:</strong>{" "}
        <span>{atual ? `${atual.titulo} · ${atual.volume_db} dB` : "Sem música"}</span>
      </p>
      {anterior ? (
        <p className="suave">{`Música anterior: ${anterior.titulo}, volume ${anterior.volume_db} dB`}</p>
      ) : null}
      {lista && lista.avisos.length > 0 ? (
        <ul className="alertas">
          {lista.avisos.map((a, i) => (
            <li key={i} className="aviso">
              ⚠ {a}
            </li>
          ))}
        </ul>
      ) : null}
      {lista ? (
        <>
          {lista.do_episodio.length > 0 ? (
            <div>
              <h3>Do episódio</h3>
              <ul className="faixas">{lista.do_episodio.map((f) => linha(f, `ep-${f.arquivo}`))}</ul>
            </div>
          ) : null}
          <div>
            <h3>Biblioteca</h3>
            {Object.entries(lista.biblioteca)
              .filter(([, faixas]) => faixas.length > 0)
              .map(([clima, faixas]) => (
                <details key={clima} className="clima">
                  <summary>{clima}</summary>
                  <ul className="faixas">{faixas.map((f) => linha(f, `bib-${f.arquivo}`))}</ul>
                </details>
              ))}
          </div>
        </>
      ) : erroLeitura ? null : (
        <p>Carregando as músicas…</p>
      )}
      <audio ref={audio} controls hidden={srcAudio === null} onEnded={() => setTocando(null)} />
      {tituloEscolhido ? (
        <p>
          Escolhida: <strong>{tituloEscolhido}</strong>
        </p>
      ) : null}
      <div className="campo">
        <label htmlFor="volume-musica">Volume</label>
        <div className="volume">
          <span className="suave">mais baixa</span>
          <input
            id="volume-musica"
            type="range"
            min={-30}
            max={-18}
            step={1}
            value={volume}
            disabled={ocupado}
            onChange={(e) => setVolumeEscolhido(Number(e.target.value))}
          />
          <span className="suave">mais alta</span>
        </div>
        <output htmlFor="volume-musica">{`${volume} dB`}</output>
      </div>
      <div className="acoes-musica">
        <button
          type="button"
          disabled={!arquivoEscolhido || ocupado || gerandoPrevia}
          onClick={() => void ouvirPrevia()}
        >
          Ouvir prévia (15 s)
        </button>
        {previaInicio !== null ? (
          <span className="suave" role="status">
            {gerandoPrevia ? "Gerando a prévia, a partir de " : "Prévia a partir de "}
            {tempoTexto(previaInicio)}
          </span>
        ) : null}
      </div>
      {erroPrevia ? (
        <p role="alert" className="mensagem-erro">
          {erroPrevia}
        </p>
      ) : null}
      <div className="acoes-musica">
        <button type="button" disabled={!arquivoEscolhido || ocupado} onClick={montarComEsta}>
          Montar com esta música
        </button>
      </div>
      {erroPedido ? (
        <p role="alert" className="mensagem-erro">
          {erroPedido}
        </p>
      ) : null}
      {pedido ? (
        <div className="andamento" role="status">
          <p className={pedido.estado === "erro" ? "mensagem-erro" : undefined}>
            {textoEstado[pedido.estado]}
          </p>
          {pedido.estado === "erro" ? (
            <button
              type="button"
              disabled={enviando}
              onClick={() => void enviar(pedido.arquivo, pedido.volume_db)}
            >
              Tentar de novo
            </button>
          ) : null}
          {pedido.avisos.length > 0 ? (
            <ul className="alertas">
              {pedido.avisos.map((a, i) => (
                <li key={i} className="aviso">
                  ⚠ {a}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
