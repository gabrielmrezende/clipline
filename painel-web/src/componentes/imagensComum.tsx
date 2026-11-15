import { useCallback, useRef, useState } from "react";
import { ErroApi, OrcamentoIa, Pedido, ResumoFotos, cancelarTarefa, formatarDolar, formatarMb, plural } from "../api";
import { ESPERA_CONSULTA_MS, useAcompanharPedido } from "../useTarefas";

export const PEDIDO_PERDIDO = "O pedido se perdeu (o painel foi reiniciado?). Confira as imagens e peça de novo se precisar.";

export const ativo = (p: Pedido | null) => p !== null && (p.estado === "na fila" || p.estado === "montando");
export const ehDeImagens = (p: Pedido) => p.tipo === "fotos" || p.tipo === "ia" || p.tipo === "montar";
export const NADA_PARA_REFAZER = "Não há nada pendente para refazer: confira as escolhas e as aprovações.";

/**
 * Entre os pedidos de um bloco (os mais recentes primeiro): o que ainda anda ou, se o último foi interrompido pelo
 * fechamento do painel, ele (para tentar de novo ou descartar). Pronto, erro e cancelado ficam para trás.
 */
export function paraRetomar(pedidos: Pedido[]): Pedido | undefined {
  return pedidos.find(ativo) ?? (pedidos[0]?.estado === "interrompido" ? pedidos[0] : undefined);
}

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
 * Acompanha o pedido até ele terminar: pelos eventos da fila (SSE) ou, se eles falharem, consultando a cada 2 s.
 * Ao terminar chama `aoTerminar` uma vez; se o painel esqueceu o pedido (404), limpa-o e chama `aoPerder`.
 */
export const useAcompanhamento = useAcompanharPedido;

/** "cancelado antes de começar" vira "Cancelado antes de começar." */
export function frase(texto: string): string {
  if (!texto) return "";
  return `${texto[0].toUpperCase()}${texto.slice(1)}${texto.endsWith(".") ? "" : "."}`;
}

const PARA_NO_MEIO = ["ia"]; // os tipos que param no meio (antes da próxima imagem paga)

interface PropsAndamento {
  pedido: Pedido;
  /** Com ele, aparecem Cancelar o pedido (na fila), Parar (IA gerando) e Descartar o pedido (interrompido). */
  aoMudar?: (p: Pedido) => void;
  /** Refaz o pedido interrompido pelo mesmo caminho do botão original (com a mesma confirmação). */
  aoTentarDeNovo?: () => void;
}

export function AndamentoPedido({ pedido, aoMudar, aoTentarDeNovo }: PropsAndamento) {
  const [erro, setErro] = useState<string | null>(null);
  const [cancelando, setCancelando] = useState(false);
  const texto: Record<Pedido["estado"], string> = {
    "na fila": "Na fila",
    montando: pedido.cancelando
      ? "Parando antes da próxima imagem…"
      : pedido.progresso || EM_ANDAMENTO[pedido.tipo ?? ""] || "Baixando…",
    pronto: "Pronto",
    erro: `Erro: ${pedido.mensagem}`,
    interrompido: `Interrompido: ${pedido.mensagem}.`,
    cancelado: frase(pedido.mensagem),
  };
  const podeParar = pedido.estado === "montando" && PARA_NO_MEIO.includes(pedido.tipo ?? "") && !pedido.cancelando;
  const rotuloCancelar =
    pedido.estado === "na fila"
      ? "Cancelar o pedido"
      : pedido.estado === "interrompido"
        ? "Descartar o pedido"
        : "Parar antes da próxima imagem";

  async function cancelar() {
    if (!aoMudar) return;
    setErro(null);
    setCancelando(true);
    try {
      aoMudar(await cancelarTarefa(pedido.id));
    } catch (x) {
      setErro(mensagem(x));
    } finally {
      setCancelando(false);
    }
  }

  return (
    <div className={ativo(pedido) ? "andamento ativo" : "andamento"} role="status">
      <p className={pedido.estado === "erro" ? "mensagem-erro" : undefined}>{texto[pedido.estado]}</p>
      {pedido.estado === "interrompido" && aoTentarDeNovo ? (
        <button type="button" onClick={aoTentarDeNovo}>
          Tentar de novo
        </button>
      ) : null}
      {aoMudar && (pedido.estado === "na fila" || pedido.estado === "interrompido" || podeParar) ? (
        <button
          type="button"
          disabled={cancelando}
          title={podeParar ? "As imagens já geradas ficam." : undefined}
          onClick={() => void cancelar()}
        >
          {rotuloCancelar}
        </button>
      ) : null}
      <Alerta texto={erro} />
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
