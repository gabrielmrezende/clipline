import { useCallback, useEffect, useRef, useState } from "react";
import { ErroApi, OrcamentoIa, Pedido, ResumoFotos, consultarTarefa, formatarDolar, formatarMb, plural } from "../api";

const ESPERA_CONSULTA_MS = 2000;
export const PEDIDO_PERDIDO = "O pedido se perdeu (o painel foi reiniciado?). Confira as imagens e peça de novo se precisar.";

export const ativo = (p: Pedido | null) => p !== null && (p.estado === "na fila" || p.estado === "montando");
export const ehDeImagens = (p: Pedido) => p.tipo === "fotos" || p.tipo === "ia" || p.tipo === "montar";

const EM_ANDAMENTO: Record<string, string> = { ia: "Gerando…", montar: "Montando…" };

export function mensagem(x: unknown): string {
  return x instanceof ErroApi ? x.detail : "Erro inesperado.";
}

/** Texto da confirmação de baixar fotos; `substituidas` diz o que acontece com as fotos de antes. */
export function textoDeFotos(r: ResumoFotos, substituidas: string): string {
  return [
    `Baixar ${plural(r.fotos, "foto", "fotos")} (${formatarMb(r.megabytes)}) de ${r.origem}?`,
    ...r.avisos,
    substituidas,
  ].join("\n");
}

export function textoDeIa(o: OrcamentoIa): string {
  return `Gerar ${plural(o.imagens, "imagem", "imagens")} com ${o.provedor} (${o.modelo}), ${formatarDolar(o.custo_usd)}?`;
}

export function rotuloDeFotos(r: ResumoFotos | null): string {
  return r
    ? `Baixar as fotos escolhidas (${plural(r.fotos, "foto", "fotos")}, ${formatarMb(r.megabytes)})`
    : "Baixar as fotos escolhidas";
}

export function rotuloDeIa(o: OrcamentoIa | null): string {
  return o
    ? `Gerar as aprovadas (${plural(o.imagens, "imagem", "imagens")}, ${formatarDolar(o.custo_usd)})`
    : "Gerar as aprovadas";
}

/**
 * Uma ação de cada vez (ler o resumo ou o orçamento, confirmar, enviar): enquanto ela não termina,
 * novos cliques são ignorados, então um clique duplo abre uma confirmação só.
 */
export function useUmaPorVez(): [boolean, (acao: () => Promise<void>) => Promise<void>] {
  const [ocupado, setOcupado] = useState(false);
  const emCurso = useRef(false);
  const rodar = useCallback(async (acao: () => Promise<void>) => {
    if (emCurso.current) return;
    emCurso.current = true;
    setOcupado(true);
    try {
      await acao();
    } finally {
      emCurso.current = false;
      setOcupado(false);
    }
  }, []);
  return [ocupado, rodar];
}

/** Por que um corte não tem fotos para baixar (escolha vazia, IA sem prompt…), logo abaixo dos botões. */
export function AvisosDoResumo({ resumo }: { resumo: ResumoFotos | null }) {
  if (!resumo || resumo.avisos.length === 0) return null;
  return (
    <ul className="alertas" aria-label="Avisos das fotos">
      {resumo.avisos.map((a, i) => (
        <li key={i} className="aviso">
          ⚠ {a}
        </li>
      ))}
    </ul>
  );
}

/** Uma mensagem de erro (ou aviso) em destaque; nada quando vazia. */
export function Alerta({ texto }: { texto: string | null | undefined }) {
  return texto ? (
    <p role="alert" className="mensagem-erro">
      {texto}
    </p>
  ) : null;
}

/**
 * Consulta o pedido a cada 2 s até ele terminar. Ao terminar chama `aoTerminar` uma vez;
 * se o painel esqueceu o pedido (404), limpa-o e chama `aoPerder`.
 */
export function useAcompanhamento(
  pedido: Pedido | null,
  setPedido: (p: Pedido | null) => void,
  aoTerminar: () => void,
  aoPerder: () => void,
) {
  const [tick, setTick] = useState(0);
  const terminados = useRef<Set<string>>(new Set());
  const funcoes = useRef({ aoTerminar, aoPerder, setPedido });
  funcoes.current = { aoTerminar, aoPerder, setPedido };

  useEffect(() => {
    if (!pedido) return;
    if (!ativo(pedido)) {
      if (!terminados.current.has(pedido.id)) {
        terminados.current.add(pedido.id);
        funcoes.current.aoTerminar();
      }
      return;
    }
    let vivo = true;
    const id = setTimeout(() => {
      consultarTarefa(pedido.id)
        .then((novo) => vivo && funcoes.current.setPedido(novo))
        .catch((x) => {
          if (!vivo) return;
          if (x instanceof ErroApi && x.status === 404) {
            funcoes.current.setPedido(null);
            funcoes.current.aoPerder();
            return;
          }
          setTick((t) => t + 1);
        });
    }, ESPERA_CONSULTA_MS);
    return () => {
      vivo = false;
      clearTimeout(id);
    };
  }, [pedido, tick]);
}

export function AndamentoPedido({ pedido }: { pedido: Pedido }) {
  const texto: Record<Pedido["estado"], string> = {
    "na fila": "Na fila",
    montando: pedido.progresso || EM_ANDAMENTO[pedido.tipo ?? ""] || "Baixando…",
    pronto: "Pronto",
    erro: `Erro: ${pedido.mensagem}`,
  };
  return (
    <div className="andamento" role="status">
      <p className={pedido.estado === "erro" ? "mensagem-erro" : undefined}>{texto[pedido.estado]}</p>
      {pedido.estado === "pronto" && pedido.mensagem ? <p>{pedido.mensagem}</p> : null}
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
  );
}

export { ESPERA_CONSULTA_MS };
