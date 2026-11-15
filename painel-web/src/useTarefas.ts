import { useEffect, useRef, useState } from "react";
import { ErroApi, Pedido, consultarTarefa } from "./api";

/**
 * A fila do painel em tempo real.
 *
 * Uma conexão de eventos (SSE) só por aba, dividida entre os blocos que acompanham algum pedido, e só enquanto
 * algum acompanha: sem pedido andando, nada fica aberto. O servidor manda a lista inteira quando ela muda.
 * Se os eventos falham (o painel caiu, um proxy segura a resposta, navegador sem EventSource), o modo vira
 * "consulta": cada bloco volta a perguntar pelo seu pedido a cada 2 s, e os eventos são tentados de novo depois.
 */

export const URL_EVENTOS = "/api/tarefas/eventos";
export const ESPERA_CONSULTA_MS = 2000;
/** Sem a primeira lista nesse tempo, os eventos não estão chegando (um proxy que segura a resposta, por exemplo). */
export const ESPERA_PRIMEIRO_EVENTO_MS = 5000;
/** No modo de consulta, de quanto em quanto tempo os eventos são tentados de novo. */
export const REABRIR_EVENTOS_MS = 30000;
/** Erros seguidos sem nenhuma lista no meio: o servidor caiu (um erro só é a reconexão normal). */
const ERROS_SEGUIDOS = 2;
const FECHADA = 2; // EventSource.CLOSED: o navegador desistiu (resposta 401, 403, 404…)

export type ModoTarefas = "eventos" | "consulta";

export interface EstadoTarefas {
  /** A lista da fila (os mais recentes primeiro); null enquanto não chegou ou no modo de consulta. */
  tarefas: Pedido[] | null;
  /** "eventos": a lista chega sozinha. "consulta": cada um pergunta pelo seu pedido a cada 2 s. */
  modo: ModoTarefas;
}

const DESLIGADO: EstadoTarefas = { tarefas: null, modo: "consulta" };

let estado: EstadoTarefas = DESLIGADO;
const ouvintes = new Set<(e: EstadoTarefas) => void>();
let fonte: EventSource | null = null;
let ultimaLista = "";
let erros = 0;
let prazoDoPrimeiro: ReturnType<typeof setTimeout> | null = null;
let reabrir: ReturnType<typeof setTimeout> | null = null;

function publicar(novo: EstadoTarefas) {
  estado = novo;
  ouvintes.forEach((ouvinte) => ouvinte(novo));
}

function limpar() {
  if (prazoDoPrimeiro) clearTimeout(prazoDoPrimeiro);
  if (reabrir) clearTimeout(reabrir);
  prazoDoPrimeiro = null;
  reabrir = null;
  fonte?.close();
  fonte = null;
  erros = 0;
}

/** Os eventos falharam: cada um volta a consultar o seu pedido; daqui a pouco os eventos são tentados de novo. */
function paraConsulta() {
  limpar();
  ultimaLista = "";
  publicar(DESLIGADO);
  if (typeof EventSource !== "undefined") reabrir = setTimeout(abrir, REABRIR_EVENTOS_MS);
}

function abrir() {
  limpar();
  if (typeof EventSource === "undefined") {
    paraConsulta();
    return;
  }
  const es = new EventSource(URL_EVENTOS); // mesma origem: o cookie da sessão vai junto
  fonte = es;
  // Até a primeira lista chegar, o modo continua o de antes (consulta): ninguém fica sem notícia.
  prazoDoPrimeiro = setTimeout(paraConsulta, ESPERA_PRIMEIRO_EVENTO_MS);
  es.addEventListener("tarefas", (evento) => {
    if (fonte !== es) return;
    const texto = (evento as MessageEvent).data as string;
    let lista: unknown;
    try {
      lista = JSON.parse(texto);
    } catch {
      return;
    }
    if (!Array.isArray(lista)) return;
    erros = 0;
    if (prazoDoPrimeiro) clearTimeout(prazoDoPrimeiro);
    prazoDoPrimeiro = null;
    if (estado.modo === "eventos" && texto === ultimaLista) return; // a reconexão manda a mesma lista
    ultimaLista = texto;
    publicar({ tarefas: lista as Pedido[], modo: "eventos" });
  });
  es.onerror = () => {
    if (fonte !== es) return;
    erros += 1;
    if (es.readyState === FECHADA || erros >= ERROS_SEGUIDOS) paraConsulta();
  };
}

function assinar(ouvinte: (e: EstadoTarefas) => void): () => void {
  ouvintes.add(ouvinte);
  if (ouvintes.size === 1) abrir();
  ouvinte(estado);
  return () => {
    ouvintes.delete(ouvinte);
    if (ouvintes.size > 0) return;
    limpar();
    ultimaLista = "";
    estado = DESLIGADO;
  };
}

/** Só para os testes: esquece a conexão e os ouvintes entre um teste e outro. */
export function reiniciarTarefas() {
  ouvintes.clear();
  limpar();
  ultimaLista = "";
  estado = DESLIGADO;
}

/** A fila em tempo real enquanto `ligado`; desligado, não abre conexão nenhuma. */
export function useTarefas(ligado = true): EstadoTarefas {
  const [atual, setAtual] = useState<EstadoTarefas>(DESLIGADO);
  useEffect(() => {
    if (!ligado) return;
    return assinar(setAtual);
  }, [ligado]);
  return ligado ? atual : DESLIGADO;
}

const ativo = (p: Pedido | null) => p !== null && (p.estado === "na fila" || p.estado === "montando");
const igual = (a: Pedido, b: Pedido) => JSON.stringify(a) === JSON.stringify(b);

/**
 * Acompanha um pedido até ele terminar: pelos eventos quando funcionam, senão consultando a cada 2 s.
 * `aoTerminar` é chamado uma vez quando um pedido visto andando termina (não para um que já chegou terminado,
 * como um interrompido de antes do reinício); se o painel esqueceu o pedido (404), limpa-o e chama `aoPerder`.
 */
export function useAcompanharPedido(
  pedido: Pedido | null,
  setPedido: (p: Pedido | null) => void,
  aoTerminar: (final: Pedido) => void,
  aoPerder: () => void,
) {
  const { tarefas, modo } = useTarefas(ativo(pedido));
  const [tick, setTick] = useState(0);
  const vistosAndando = useRef<Set<string>>(new Set());
  const conferida = useRef<Pedido[] | null>(null);
  const funcoes = useRef({ aoTerminar, aoPerder, setPedido });
  funcoes.current = { aoTerminar, aoPerder, setPedido };

  useEffect(() => {
    if (!pedido) return;
    if (ativo(pedido)) {
      vistosAndando.current.add(pedido.id);
    } else if (vistosAndando.current.delete(pedido.id)) {
      funcoes.current.aoTerminar(pedido);
    }
  }, [pedido]);

  // Pelos eventos: o pedido vem na lista. Fora dela (acabou de ser criado, ou o painel o esqueceu), confere uma vez.
  useEffect(() => {
    if (!pedido || !ativo(pedido) || modo !== "eventos" || tarefas === null) return;
    const novo = tarefas.find((t) => t.id === pedido.id);
    if (novo) {
      if (!igual(novo, pedido)) funcoes.current.setPedido(novo);
      return;
    }
    if (conferida.current === tarefas) return;
    conferida.current = tarefas;
    let vivo = true;
    consultarTarefa(pedido.id)
      .then((achado) => vivo && !igual(achado, pedido) && funcoes.current.setPedido(achado))
      .catch((x) => {
        if (!vivo || !(x instanceof ErroApi && x.status === 404)) return;
        funcoes.current.setPedido(null);
        funcoes.current.aoPerder();
      });
    return () => {
      vivo = false;
    };
  }, [pedido, tarefas, modo]);

  // Sem eventos: consulta o pedido a cada 2 s, como antes.
  useEffect(() => {
    if (!pedido || !ativo(pedido) || modo !== "consulta") return;
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
  }, [pedido, tick, modo]);
}
