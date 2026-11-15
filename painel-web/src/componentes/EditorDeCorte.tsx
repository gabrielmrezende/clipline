import { Fragment, KeyboardEvent, MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ConferenciaTrecho,
  ErroApi,
  PalavraTrecho,
  Pedido,
  Trecho,
  conferirTrecho,
  lerTrecho,
  segundosTexto,
  tempoComDecimo,
  trocarTrecho,
} from "../api";
import { Alerta, AndamentoPedido, ativo, mensagem, useAcompanhamento, useUmaPorVez } from "./imagensComum";
import "./EditorDeCorte.css";

interface Props {
  ep: string;
  n: number | string;
  /** Solta o corte.mp4 do player antes da troca (no Windows, arquivo aberto não pode ser trocado). */
  soltarVideo: () => void;
  aoMudarAndamento: (montando: boolean) => void;
  /** Depois da troca (deu certo ou voltou ao que era): recarrega o corte, o vídeo e os blocos. */
  aoTerminar: () => void;
  montandoNaTela: boolean;
}

type Ponta = "inicio" | "fim";

interface Selecao {
  inicio: number;
  fim: number;
}

interface Grupo {
  falante: string | null;
  cor: number;
  itens: number[];
}

const JANELA = 30; // segundos de transcrição antes e depois do corte
const JANELA_MAXIMA = 600;
const PASSO_PAGINA = 20; // palavras por PageUp/PageDown
const PAUSA_MARCADA = 1; // segundos: pausas maiores aparecem na transcrição
const FOLGA = 0.001;
const CORES_DE_VOZ = 4;
const PEDIDO_PERDIDO = "O pedido se perdeu (o painel foi reiniciado?). Confira o trecho e peça de novo se precisar.";

/** A confirmação da troca. Por enquanto, o window.confirm; o diálogo do painel entra aqui. */
function confirmar(texto: string): Promise<boolean> {
  return Promise.resolve(window.confirm(texto));
}

function outraPonta(ponta: Ponta): Ponta {
  return ponta === "inicio" ? "fim" : "inicio";
}

/** Falas seguidas da mesma voz, cada voz com uma cor (na ordem em que aparecem). */
function agrupar(palavras: PalavraTrecho[]): Grupo[] {
  const cores = new Map<string, number>();
  const grupos: Grupo[] = [];
  let vozAnterior: string | null | undefined;
  palavras.forEach((p, i) => {
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && p.voz === vozAnterior) {
      ultimo.itens.push(i);
      return;
    }
    const chave = p.voz ?? "";
    if (!cores.has(chave)) cores.set(chave, cores.size % CORES_DE_VOZ);
    grupos.push({ falante: p.falante, cor: cores.get(chave) ?? 0, itens: [i] });
    vozAnterior = p.voz;
  });
  return grupos;
}

function dentroDe(p: PalavraTrecho, inicio: number, fim: number): boolean {
  return p.inicio >= inicio - FOLGA && p.fim <= fim + FOLGA;
}

/** O texto da confirmação: o trecho novo, o que muda, o que se perde e os avisos. */
export function textoDaConfirmacao(n: number | string, c: ConferenciaTrecho): string {
  const linhas = [
    `Trocar o trecho do corte ${n} para ${tempoComDecimo(c.inicio)} a ${tempoComDecimo(c.fim)} ` +
      `(${segundosTexto(c.duracao)})?`,
  ];
  if (c.resumo.length) linhas.push("", "O que muda:", ...c.resumo.map((r) => `• ${r}`));
  if (c.perdas.length) linhas.push("", "O que se perde:", ...c.perdas.map((r) => `• ${r}`));
  if (c.avisos.length) linhas.push("", "Atenção:", ...c.avisos.map((r) => `• ${r}`));
  return linhas.join("\n");
}

/** O bloco "Trecho": a transcrição ao redor do corte, onde se marca um início e um fim novos. */
export function EditorDeCorte({ ep, n, soltarVideo, aoMudarAndamento, aoTerminar, montandoNaTela }: Props) {
  const [dados, setDados] = useState<Trecho | null>(null);
  const [erroLeitura, setErroLeitura] = useState<{ texto: string; grave: boolean } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [janela, setJanela] = useState({ antes: JANELA, depois: JANELA });
  const [selecao, setSelecao] = useState<Selecao | null>(null);
  const [modo, setModo] = useState<Ponta>("inicio");
  const [foco, setFoco] = useState(0);
  const [conferencia, setConferencia] = useState<{ chave: string; dados: ConferenciaTrecho } | null>(null);
  const [erroConferir, setErroConferir] = useState<string | null>(null);
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [ultimo, setUltimo] = useState<Pedido | null>(null);
  const [ocupado, umaPorVez] = useUmaPorVez();
  const palavrasRef = useRef<(HTMLSpanElement | null)[]>([]);
  const caixa = useRef<HTMLDivElement | null>(null);
  const rodadaConferir = useRef(0);
  const centralizar = useRef(true);
  const aoMudarAndamentoRef = useRef(aoMudarAndamento);
  aoMudarAndamentoRef.current = aoMudarAndamento;

  useEffect(() => {
    let vivo = true;
    lerTrecho(ep, n, JANELA, JANELA)
      .then((d) => {
        if (!vivo) return;
        setDados(d);
        setSelecao({ inicio: d.inicio, fim: d.fim });
        setFoco(Math.max(0, d.palavras.findIndex((p) => p.inicio >= d.inicio - FOLGA)));
        if (d.pedido && ativo(d.pedido)) {
          setPedido(d.pedido);
          aoMudarAndamentoRef.current(true);
        } else if (d.pedido) {
          setUltimo(d.pedido);
        }
      })
      .catch((x) => {
        if (!vivo) return;
        setErroLeitura({ texto: mensagem(x), grave: !(x instanceof ErroApi && x.status === 404) });
      });
    return () => {
      vivo = false;
    };
  }, [ep, n]);

  /** Lê de novo (outra janela, ou depois da troca). `manter`: a seleção do dono continua. */
  async function recarregar(antes: number, depois: number, manter: boolean) {
    const tempoEmFoco = dados?.palavras[foco]?.inicio;
    try {
      const d = await lerTrecho(ep, n, antes, depois);
      // a palavra em foco continua a mesma, mesmo com palavras novas antes dela
      const indice = d.palavras.findIndex((p) => p.inicio === tempoEmFoco);
      setFoco(indice >= 0 ? indice : Math.max(0, d.palavras.findIndex((p) => p.inicio >= d.inicio - FOLGA)));
      setDados(d);
      setSelecao((s) => (manter && s ? s : { inicio: d.inicio, fim: d.fim }));
      setErroLeitura(null);
    } catch (x) {
      setErro(mensagem(x));
    }
  }

  useAcompanhamento(
    pedido,
    setPedido,
    () => {
      aoMudarAndamento(false);
      void recarregar(janela.antes, janela.depois, pedido?.estado !== "pronto");
      aoTerminar();
    },
    () => {
      aoMudarAndamento(false);
      setErro(PEDIDO_PERDIDO);
      void recarregar(janela.antes, janela.depois, true);
      aoTerminar();
    },
  );

  const mudou = !!(dados && selecao && (selecao.inicio !== dados.inicio || selecao.fim !== dados.fim));
  const chave = selecao ? `${selecao.inicio}|${selecao.fim}` : "";
  const versao = dados?.versao;

  // Cada seleção nova é conferida no painel: alinhamento, validar, sobreposição e o que muda ou se perde.
  useEffect(() => {
    rodadaConferir.current += 1;
    const rodada = rodadaConferir.current;
    setErroConferir(null);
    if (!mudou || !selecao) return;
    conferirTrecho(ep, n, selecao.inicio, selecao.fim)
      .then((c) => rodada === rodadaConferir.current && setConferencia({ chave, dados: c }))
      .catch((x) => rodada === rodadaConferir.current && setErroConferir(mensagem(x)));
  }, [ep, n, chave, mudou, versao]);

  // Ao abrir, a transcrição rola (só dentro da caixa) até o começo do corte.
  useEffect(() => {
    if (!dados || !centralizar.current) return;
    centralizar.current = false;
    const el = palavrasRef.current[foco];
    const area = caixa.current;
    if (el && area) area.scrollTop = Math.max(0, el.offsetTop - area.clientHeight / 3);
  }, [dados, foco]);

  const grupos = useMemo(() => (dados ? agrupar(dados.palavras) : []), [dados]);

  if (!dados || !selecao) {
    return (
      <section aria-labelledby="titulo-trecho" className="editor-trecho">
        <h2 id="titulo-trecho">Trecho</h2>
        {erroLeitura?.grave ? <Alerta texto={erroLeitura.texto} /> : null}
        {erroLeitura && !erroLeitura.grave ? <p className="suave-bloco">{erroLeitura.texto}</p> : null}
        {!erroLeitura ? <p className="suave-bloco">Carregando a transcrição…</p> : null}
      </section>
    );
  }

  const trecho = dados;
  const travado = ocupado || ativo(pedido);
  const duracao = selecao.fim - selecao.inicio;
  const fora = duracao < trecho.minima - FOLGA || duracao > trecho.maxima + FOLGA;
  const conf = conferencia && conferencia.chave === chave ? conferencia.dados : null;
  const pode = !!conf && conf.mudou && conf.problemas.length === 0 && !travado && !montandoNaTela;

  function marcar(i: number, ponta: Ponta) {
    const p = trecho.palavras[i];
    if (!p || travado) return;
    setErro(null);
    setSelecao((s) => {
      const atual = s ?? { inicio: trecho.inicio, fim: trecho.fim };
      return ponta === "inicio" ? { ...atual, inicio: p.inicio } : { ...atual, fim: p.fim };
    });
    setFoco(i);
  }

  function irPara(i: number) {
    const alvo = Math.min(trecho.palavras.length - 1, Math.max(0, i));
    setFoco(alvo);
    palavrasRef.current[alvo]?.focus();
  }

  function aoTeclar(e: KeyboardEvent<HTMLDivElement>) {
    switch (e.key) {
      case "ArrowRight":
      case "ArrowDown":
        irPara(foco + 1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        irPara(foco - 1);
        break;
      case "Home":
        irPara(0);
        break;
      case "End":
        irPara(trecho.palavras.length - 1);
        break;
      case "PageDown":
        irPara(foco + PASSO_PAGINA);
        break;
      case "PageUp":
        irPara(foco - PASSO_PAGINA);
        break;
      case "Enter":
      case " ":
        marcar(foco, e.shiftKey ? outraPonta(modo) : modo);
        break;
      default:
        return;
    }
    e.preventDefault();
  }

  function aoClicar(e: MouseEvent<HTMLSpanElement>, i: number) {
    marcar(i, e.shiftKey ? outraPonta(modo) : modo);
  }

  function mostrarMais(lado: "antes" | "depois") {
    const nova = { ...janela, [lado]: Math.min(JANELA_MAXIMA, janela[lado] + JANELA) };
    setJanela(nova);
    void recarregar(nova.antes, nova.depois, true);
  }

  const aplicar = () =>
    umaPorVez(async () => {
      if (!conf || !pode) return;
      if (!(await confirmar(textoDaConfirmacao(n, conf)))) return;
      setErro(null);
      setUltimo(null);
      if (trecho.montado) soltarVideo();
      aoMudarAndamento(true);
      try {
        setPedido(await trocarTrecho(ep, n, conf.inicio, conf.fim, trecho.versao));
      } catch (x) {
        aoMudarAndamento(false);
        setErro(mensagem(x));
        if (x instanceof ErroApi && x.status === 409) void recarregar(janela.antes, janela.depois, true);
      }
    });

  const andamento = pedido ? { ...pedido, progresso: pedido.progresso || "Trocando o trecho…" } : ultimo;

  return (
    <section aria-labelledby="titulo-trecho" className="editor-trecho">
      <h2 id="titulo-trecho">Trecho</h2>
      <p id="ajuda-trecho" className="suave-bloco">
        Clique numa palavra para marcar o {modo === "inicio" ? "início" : "fim"} do corte; com Shift, marca o{" "}
        {modo === "inicio" ? "fim" : "início"}. No teclado, as setas andam pelas palavras, Enter marca e Shift+Enter
        marca a outra ponta. Sublinhado: o trecho de agora.
      </p>
      <Alerta texto={erro} />
      {trecho.problemas.length > 0 ? (
        <ul className="alertas" aria-label="Problemas do trecho de agora">
          {trecho.problemas.map((p, i) => (
            <li key={i} className="aviso">
              ⚠ Trecho de agora: {p}
            </li>
          ))}
        </ul>
      ) : null}
      <fieldset className="modo-trecho" disabled={travado}>
        <legend>O clique marca</legend>
        <label>
          <input type="radio" name={`modo-trecho-${n}`} checked={modo === "inicio"} onChange={() => setModo("inicio")} />{" "}
          o início
        </label>
        <label>
          <input type="radio" name={`modo-trecho-${n}`} checked={modo === "fim"} onChange={() => setModo("fim")} /> o fim
        </label>
      </fieldset>
      <p className="medidas-trecho" aria-live="polite">
        <span>
          Início <strong>{tempoComDecimo(selecao.inicio)}</strong>
        </span>
        <span>
          Fim <strong>{tempoComDecimo(selecao.fim)}</strong>
        </span>
        <span className={fora ? "duracao-fora" : undefined}>
          Duração <strong>{segundosTexto(duracao)}</strong> (de {trecho.minima} a {trecho.maxima} s)
          {fora ? ": fora do limite" : ""}
        </span>
      </p>
      <p className="acoes-trecho">
        <button type="button" disabled={travado || trecho.de <= 0 || janela.antes >= JANELA_MAXIMA} onClick={() => mostrarMais("antes")}>
          Mostrar mais {JANELA} s antes
        </button>
        <button
          type="button"
          disabled={travado || trecho.ate >= trecho.duracao_episodio || janela.depois >= JANELA_MAXIMA}
          onClick={() => mostrarMais("depois")}
        >
          Mostrar mais {JANELA} s depois
        </button>
        {mudou ? (
          <button type="button" className="discreto" disabled={travado} onClick={() => setSelecao({ inicio: trecho.inicio, fim: trecho.fim })}>
            Voltar ao trecho de agora
          </button>
        ) : null}
      </p>
      {trecho.outros.length > 0 ? (
        <p className="suave-bloco">
          Em cinza, as falas de outros cortes:{" "}
          {trecho.outros.map((o) => `corte ${o.numero} (${o.titulo})`).join(", ")}.
        </p>
      ) : null}
      <div
        ref={caixa}
        className="transcricao-trecho"
        role="listbox"
        aria-multiselectable="true"
        aria-label="Transcrição ao redor do corte"
        aria-describedby="ajuda-trecho"
        aria-disabled={travado || undefined}
        onKeyDown={aoTeclar}
      >
        {grupos.map((g) => (
          <div key={g.itens[0]} role="group" aria-label={g.falante ?? "Fala"} className={`fala-trecho voz-${g.cor}`}>
            {g.falante ? (
              <span className="falante-trecho" aria-hidden="true">
                {g.falante}
              </span>
            ) : null}
            {g.itens.map((i) => {
              const p = trecho.palavras[i];
              const anterior = trecho.palavras[i - 1];
              const pausa = anterior ? p.inicio - anterior.fim : 0;
              const outro = trecho.outros.find((o) => dentroDe(p, o.inicio, o.fim));
              const classes = [
                "palavra",
                dentroDe(p, selecao.inicio, selecao.fim) ? "dentro" : "",
                dentroDe(p, trecho.inicio, trecho.fim) ? "no-corte-atual" : "",
                Math.abs(p.inicio - selecao.inicio) < FOLGA ? "ponta-inicio" : "",
                Math.abs(p.fim - selecao.fim) < FOLGA ? "ponta-fim" : "",
                outro ? "de-outro-corte" : "",
                i === foco ? "em-foco" : "",
              ].filter(Boolean);
              return (
                <Fragment key={i}>
                  {pausa >= PAUSA_MARCADA ? (
                    <span className="pausa-trecho" aria-hidden="true">
                      pausa {segundosTexto(pausa)}
                    </span>
                  ) : null}
                  <span
                    ref={(el) => {
                      palavrasRef.current[i] = el;
                    }}
                    role="option"
                    tabIndex={i === foco ? 0 : -1}
                    aria-selected={dentroDe(p, selecao.inicio, selecao.fim)}
                    aria-label={`${p.texto} ${tempoComDecimo(p.inicio)}`}
                    title={outro ? `${tempoComDecimo(p.inicio)}, corte ${outro.numero}` : tempoComDecimo(p.inicio)}
                    className={classes.join(" ")}
                    onClick={(e) => aoClicar(e, i)}
                    onFocus={() => setFoco(i)}
                  >
                    {p.texto}
                  </span>{" "}
                </Fragment>
              );
            })}
          </div>
        ))}
      </div>
      {mudou ? (
        <div className="conferencia-trecho" aria-live="polite">
          {!conf && !erroConferir ? <p className="suave-bloco">Conferindo o trecho novo…</p> : null}
          <Alerta texto={erroConferir} />
          {conf && conf.problemas.length > 0 ? (
            <>
              <h3>Não dá para trocar</h3>
              <ul className="alertas">
                {conf.problemas.map((p, i) => (
                  <li key={i} className="mensagem-erro">
                    {p}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {conf && conf.problemas.length === 0 ? (
            <>
              <h3>O que muda</h3>
              <ul className="resumo-trecho">
                {conf.resumo.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
              {conf.perdas.length > 0 ? (
                <>
                  <h3>O que se perde</h3>
                  <ul className="alertas">
                    {conf.perdas.map((r, i) => (
                      <li key={i} className="aviso">
                        ⚠ {r}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {conf.avisos.length > 0 ? (
                <ul className="alertas" aria-label="Avisos do trecho novo">
                  {conf.avisos.map((r, i) => (
                    <li key={i} className="aviso">
                      ⚠ {r}
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : null}
          <p className="acoes-trecho">
            <button type="button" className="primario" disabled={!pode} onClick={() => void aplicar()}>
              Trocar o trecho
            </button>
          </p>
        </div>
      ) : null}
      {andamento ? <AndamentoPedido pedido={andamento} /> : null}
    </section>
  );
}
