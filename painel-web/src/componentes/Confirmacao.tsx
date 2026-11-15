import { ReactNode, createContext, useCallback, useContext, useEffect, useId, useRef, useState } from "react";
import { Dialogo } from "./Dialogo";

/** "custo": gasta dinheiro; "irreversivel": apaga ou substitui algo que não volta. */
export type TomConfirmacao = "normal" | "custo" | "irreversivel";

export interface OpcoesConfirmacao {
  /** A pergunta, em uma frase. */
  titulo: string;
  /** O que acontece, em uma ou duas frases. */
  resumo?: string;
  /** Um aviso em destaque, antes do resumo. */
  aviso?: string;
  /** Itens a conferir (avisos de cada foto, por exemplo). */
  itens?: string[];
  /** Custo já formatado ("~US$ 0,10"): aparece em destaque e no botão de confirmar. */
  custo?: string;
  /** Rótulo do botão de confirmar (padrão: "Confirmar"). */
  confirmar?: string;
  /** Rótulo do botão de cancelar (padrão: "Cancelar"). */
  cancelar?: string;
  /** Padrão: "custo" quando há custo; senão "normal". */
  tom?: TomConfirmacao;
}

export type Confirmar = (opcoes: OpcoesConfirmacao) => Promise<boolean>;

const semProvedor: Confirmar = () =>
  Promise.reject(new Error("confirmar() precisa do ProvedorConfirmacao em volta da tela."));

const Contexto = createContext<Confirmar>(semProvedor);

/** A confirmação da tela: `await confirmar({...})` devolve true só se a pessoa clicou em confirmar. */
export function useConfirmar(): Confirmar {
  return useContext(Contexto);
}

interface Pedido {
  id: number;
  opcoes: OpcoesConfirmacao;
  resolver: (sim: boolean) => void;
  origem: Element | null;
  respondido: boolean;
}

/** Último elemento clicado ou focado: no Safari o clique não foca o botão, e um botão desabilitado perde o foco. */
function useUltimoAlvo() {
  const alvo = useRef<Element | null>(null);
  useEffect(() => {
    function guardar(e: Event) {
      const origem = e.target instanceof Element ? e.target : null;
      const el = origem?.closest("button, a, input, select, textarea, [tabindex]") ?? null;
      if (el && !el.closest("dialog")) alvo.current = el;
    }
    document.addEventListener("pointerdown", guardar, true);
    document.addEventListener("focusin", guardar, true);
    return () => {
      document.removeEventListener("pointerdown", guardar, true);
      document.removeEventListener("focusin", guardar, true);
    };
  }, []);
  return alvo;
}

/**
 * Guarda as confirmações pedidas pela tela e mostra uma de cada vez, na ordem dos pedidos.
 * Cancelar, Esc ou clique fora respondem false; o foco volta ao botão que pediu a confirmação.
 */
export function ProvedorConfirmacao({ children }: { children: ReactNode }) {
  const [fila, setFila] = useState<Pedido[]>([]);
  const proximo = useRef(0);
  const ultimoAlvo = useUltimoAlvo();

  const confirmar = useCallback<Confirmar>(
    (opcoes) =>
      new Promise<boolean>((resolver) => {
        const ativo = document.activeElement;
        const origem = ativo && ativo !== document.body ? ativo : ultimoAlvo.current;
        proximo.current += 1;
        const pedido: Pedido = { id: proximo.current, opcoes, resolver, origem, respondido: false };
        setFila((f) => [...f, pedido]);
      }),
    [ultimoAlvo],
  );

  const atual = fila[0];

  function responder(pedido: Pedido, sim: boolean) {
    if (pedido.respondido) return; // clique duplo no botão: uma resposta só
    pedido.respondido = true;
    setFila((f) => f.filter((p) => p !== pedido));
    pedido.resolver(sim);
  }

  return (
    <Contexto.Provider value={confirmar}>
      {children}
      {atual ? (
        <DialogoConfirmacao
          key={atual.id}
          opcoes={atual.opcoes}
          origem={atual.origem}
          responder={(sim) => responder(atual, sim)}
        />
      ) : null}
    </Contexto.Provider>
  );
}

function IconeTom({ tom }: { tom: TomConfirmacao }) {
  if (tom === "normal") return null;
  return (
    <span className="dialogo-icone" aria-hidden="true">
      {tom === "custo" ? (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="9" />
          <path
            d={
              "M15 9.2c-.5-1-1.7-1.6-3-1.6-1.7 0-3 .9-3 2.2 0 3 6 1.6 6 4.5 " +
              "0 1.3-1.3 2.2-3 2.2-1.4 0-2.6-.7-3.1-1.7"
            }
          />
          <path d="M12 6v1.6M12 16.4V18" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 3.5 2.8 19.5h18.4L12 3.5Z" strokeLinejoin="round" />
          <path d="M12 10v4.5M12 17v.5" strokeLinecap="round" />
        </svg>
      )}
    </span>
  );
}

function DialogoConfirmacao({
  opcoes,
  origem,
  responder,
}: {
  opcoes: OpcoesConfirmacao;
  origem: Element | null;
  responder: (sim: boolean) => void;
}) {
  const id = useId();
  const botaoConfirmar = useRef<HTMLButtonElement>(null);
  const botaoCancelar = useRef<HTMLButtonElement>(null);
  const { titulo, resumo, aviso, itens = [], custo } = opcoes;
  const tom: TomConfirmacao = opcoes.tom ?? (custo ? "custo" : "normal");
  const rotulo = opcoes.confirmar ?? "Confirmar";
  const descricao = [aviso || resumo ? `${id}-descricao` : "", custo ? `${id}-custo` : ""].filter(Boolean).join(" ");

  return (
    <Dialogo
      papel="alertdialog"
      tituloId={`${id}-titulo`}
      descricaoId={descricao}
      aoFechar={() => responder(false)}
      // Ação que gasta ou não volta: o foco começa em Cancelar, e um Enter apressado não confirma.
      focoInicial={tom === "normal" ? botaoConfirmar : botaoCancelar}
      origem={origem}
      className={`dialogo-confirmacao tom-${tom}`}
    >
      <div className="dialogo-cabeca">
        <IconeTom tom={tom} />
        <h2 id={`${id}-titulo`} className="dialogo-titulo">
          {titulo}
        </h2>
      </div>
      {aviso || resumo ? (
        <div id={`${id}-descricao`} className="dialogo-descricao">
          {aviso ? <p className="dialogo-aviso">{aviso}</p> : null}
          {resumo ? <p>{resumo}</p> : null}
        </div>
      ) : null}
      {itens.length > 0 ? (
        <ul className="dialogo-itens">
          {itens.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : null}
      {custo ? (
        <p id={`${id}-custo`} className="dialogo-custo">
          <span>Custo estimado</span>
          <strong>{custo}</strong>
        </p>
      ) : null}
      <div className="dialogo-acoes">
        <button ref={botaoCancelar} type="button" onClick={() => responder(false)}>
          {opcoes.cancelar ?? "Cancelar"}
        </button>
        <button
          ref={botaoConfirmar}
          type="button"
          className={`dialogo-confirmar tom-${tom}`}
          onClick={() => responder(true)}
        >
          {custo ? `${rotulo} por ${custo}` : rotulo}
        </button>
      </div>
    </Dialogo>
  );
}
