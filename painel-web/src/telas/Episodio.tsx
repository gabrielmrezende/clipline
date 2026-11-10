import { KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Bloco,
  Calendario as DadosCalendario,
  EpisodioDetalhe,
  ErroApi,
  caminhoEpisodio,
  pedir,
} from "../api";
import { Calendario } from "../componentes/Calendario";
import { ImagensDoEpisodio } from "../componentes/ImagensDoEpisodio";
import { Markdown } from "../componentes/Markdown";
import { Selo } from "../componentes/Selo";

const ABAS = [
  { id: "cortes", rotulo: "Cortes" },
  { id: "calendario", rotulo: "Calendário" },
  { id: "imagens", rotulo: "Imagens" },
  { id: "descartados", rotulo: "Descartados" },
] as const;
type AbaId = (typeof ABAS)[number]["id"];

function mensagem(x: unknown): string {
  return x instanceof ErroApi ? x.detail : "Erro inesperado.";
}

function Erro({ texto }: { texto: string }) {
  return (
    <p role="alert" className="mensagem-erro">
      {texto}
    </p>
  );
}

function Cortes({ ep, cortes }: { ep: string; cortes: Bloco[] }) {
  if (cortes.length === 0) return <p>Nenhum corte neste episódio.</p>;
  return (
    <ul className="cartoes grade">
      {cortes.map((c) => (
        <li key={c.numero} className="cartao">
          <Link to={`/episodios/${encodeURIComponent(ep)}/cortes/${c.numero}`} className="alvo">
            <h3 className="corte-titulo">
              <span className="corte-num">{c.numero}.</span> {c.titulo}
            </h3>
            <p>{c.montando ? <span className="suave">montando…</span> : <Selo valor={c.selo} />}</p>
            <p>{c.data ? `Publica em ${c.data}` : "Sem data"}</p>
            <p className="redes">{c.redes.join(", ")}</p>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function PainelCalendario({ ep }: { ep: string }) {
  const [dados, setDados] = useState<DadosCalendario | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    pedir<DadosCalendario>(`${caminhoEpisodio(ep)}/calendario`)
      .then(setDados)
      .catch((x) => setErro(mensagem(x)));
  }, [ep]);
  if (erro) return <Erro texto={erro} />;
  if (!dados) return <p>Carregando…</p>;
  return <Calendario itens={dados.itens} />;
}

function PainelDescartados({ ep }: { ep: string }) {
  const [texto, setTexto] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    pedir<{ texto: string }>(`${caminhoEpisodio(ep)}/descartados`)
      .then((d) => setTexto(d.texto))
      .catch((x) => setErro(mensagem(x)));
  }, [ep]);
  if (erro) return <Erro texto={erro} />;
  if (texto === null) return <p>Carregando…</p>;
  if (!texto.trim()) return <p>Nenhum candidato descartado.</p>;
  return <Markdown texto={texto} />;
}

export function Episodio() {
  const { ep = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const aba: AbaId = ABAS.find((a) => a.id === params.get("aba"))?.id ?? "cortes";
  const [detalhe, setDetalhe] = useState<EpisodioDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const lista = useRef<HTMLDivElement>(null);
  const [indicador, setIndicador] = useState<{ x: number; w: number } | null>(null);

  // A linha azul embaixo da aba escolhida desliza até a nova aba.
  useLayoutEffect(() => {
    function medir() {
      const ativa = lista.current?.querySelector<HTMLElement>('[aria-selected="true"]');
      if (ativa) setIndicador({ x: ativa.offsetLeft, w: ativa.offsetWidth });
    }
    medir();
    window.addEventListener("resize", medir);
    void document.fonts?.ready.then(medir);
    return () => window.removeEventListener("resize", medir);
  }, [aba]);

  useEffect(() => {
    setDetalhe(null);
    setErro(null);
    pedir<EpisodioDetalhe>(caminhoEpisodio(ep))
      .then(setDetalhe)
      .catch((x) => setErro(mensagem(x)));
  }, [ep]);

  function escolher(id: AbaId) {
    setParams(id === "cortes" ? {} : { aba: id }, { replace: true });
  }

  function teclas(e: KeyboardEvent<HTMLButtonElement>, i: number) {
    let alvo = -1;
    if (e.key === "ArrowRight") alvo = (i + 1) % ABAS.length;
    else if (e.key === "ArrowLeft") alvo = (i - 1 + ABAS.length) % ABAS.length;
    else if (e.key === "Home") alvo = 0;
    else if (e.key === "End") alvo = ABAS.length - 1;
    if (alvo < 0) return;
    e.preventDefault();
    escolher(ABAS[alvo].id);
    document.getElementById(`aba-${ABAS[alvo].id}`)?.focus();
  }

  return (
    <main className="coluna">
      <p className="voltar">
        <Link to="/" className="alvo-inline">
          ← Episódios
        </Link>
      </p>
      <h1>{ep}</h1>
      {detalhe?.resumo.aviso ? <p className="aviso">⚠ {detalhe.resumo.aviso}</p> : null}
      <div role="tablist" aria-label="Seções do episódio" className="abas" ref={lista}>
        {ABAS.map((a, i) => (
          <button
            key={a.id}
            role="tab"
            id={`aba-${a.id}`}
            aria-selected={aba === a.id}
            aria-controls={`painel-${aba}`}
            tabIndex={aba === a.id ? 0 : -1}
            onClick={() => escolher(a.id)}
            onKeyDown={(e) => teclas(e, i)}
          >
            {a.rotulo}
          </button>
        ))}
        {indicador ? (
          <span
            className="abas-indicador"
            aria-hidden="true"
            style={{ transform: `translateX(${indicador.x}px)`, width: indicador.w }}
          />
        ) : null}
      </div>
      <div role="tabpanel" id={`painel-${aba}`} aria-labelledby={`aba-${aba}`}>
        {erro ? <Erro texto={erro} /> : null}
        {aba === "cortes" && !erro ? (
          detalhe ? <Cortes ep={ep} cortes={detalhe.cortes} /> : <p>Carregando…</p>
        ) : null}
        {aba === "calendario" ? <PainelCalendario ep={ep} /> : null}
        {aba === "imagens" && !erro ? (
          detalhe ? <ImagensDoEpisodio ep={ep} cortes={detalhe.cortes} /> : <p>Carregando…</p>
        ) : null}
        {aba === "descartados" ? <PainelDescartados ep={ep} /> : null}
      </div>
    </main>
  );
}
