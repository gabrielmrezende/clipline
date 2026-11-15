import "./dialogo.css";
import { KeyboardEvent, MouseEvent, ReactNode, RefObject, useLayoutEffect, useRef } from "react";

const FOCAVEIS = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "summary",
  '[tabindex]:not([tabindex="-1"])',
].join(",");
/** Quanto tempo o foco espera o botão de origem voltar a ficar habilitado. */
const ESPERA_FOCO_MS = 30_000;

interface Props {
  /** id do título (aria-labelledby). */
  tituloId: string;
  /** ids do que descreve o diálogo (aria-describedby), separados por espaço. */
  descricaoId?: string;
  /** "alertdialog" para confirmações; "dialog" para o resto (ajuda, por exemplo). */
  papel?: "dialog" | "alertdialog";
  /** Esc, clique fora ou o botão de fechar. */
  aoFechar: () => void;
  /** Quem recebe o foco ao abrir; sem ele, o primeiro elemento focável. */
  focoInicial?: RefObject<HTMLElement>;
  /** Para onde o foco volta ao fechar; sem ele, o que tinha o foco ao abrir. */
  origem?: Element | null;
  className?: string;
  children: ReactNode;
}

function focaveis(raiz: HTMLElement): HTMLElement[] {
  return Array.from(raiz.querySelectorAll<HTMLElement>(FOCAVEIS)).filter((el) => !el.closest("[inert]"));
}

/**
 * Devolve o foco ao elemento de origem. Se ele estiver desabilitado (o botão que abriu a confirmação fica
 * desabilitado enquanto a ação roda), espera ele voltar, desde que ninguém tenha pegado o foco nesse meio tempo.
 */
export function devolverFoco(origem: Element | null | undefined) {
  if (!(origem instanceof HTMLElement) || !origem.isConnected) return;
  if (!(origem as HTMLButtonElement).disabled) {
    origem.focus();
    return;
  }
  const observador = new MutationObserver(() => {
    if (!origem.isConnected) return parar();
    if ((origem as HTMLButtonElement).disabled) return;
    parar();
    const ativo = document.activeElement;
    if (!ativo || ativo === document.body) origem.focus();
  });
  const limite = setTimeout(parar, ESPERA_FOCO_MS);
  function parar() {
    observador.disconnect();
    clearTimeout(limite);
  }
  observador.observe(origem, { attributes: true, attributeFilter: ["disabled"] });
}

/**
 * Diálogo modal acessível sobre o <dialog> nativo: foco preso dentro dele, Esc fecha, clique fora fecha e o
 * foco volta para quem abriu. Onde não há showModal (jsdom), abre com o atributo open e o mesmo comportamento.
 */
export function Dialogo({
  tituloId,
  descricaoId,
  papel = "dialog",
  aoFechar,
  focoInicial,
  origem,
  className,
  children,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const aoFecharRef = useRef(aoFechar);
  aoFecharRef.current = aoFechar;

  useLayoutEffect(() => {
    const dialogo = ref.current;
    if (!dialogo) return;
    const voltar = origem ?? document.activeElement;
    if (typeof dialogo.showModal === "function") {
      if (!dialogo.open) dialogo.showModal();
    } else {
      dialogo.setAttribute("open", "");
    }
    (focoInicial?.current ?? focaveis(dialogo)[0] ?? dialogo).focus();
    return () => {
      if (typeof dialogo.close === "function" && dialogo.open) dialogo.close();
      devolverFoco(voltar);
    };
    // Abre uma vez por montagem: quem muda de pedido troca a key.
  }, []);

  function teclas(e: KeyboardEvent<HTMLDialogElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      aoFecharRef.current();
      return;
    }
    if (e.key !== "Tab" || !ref.current) return;
    const lista = focaveis(ref.current);
    if (lista.length === 0) {
      e.preventDefault();
      return;
    }
    const primeiro = lista[0];
    const ultimo = lista[lista.length - 1];
    const ativo = document.activeElement;
    if (e.shiftKey && (ativo === primeiro || !ref.current.contains(ativo))) {
      e.preventDefault();
      ultimo.focus();
    } else if (!e.shiftKey && (ativo === ultimo || !ref.current.contains(ativo))) {
      e.preventDefault();
      primeiro.focus();
    }
  }

  // O clique no fundo escurecido chega ao próprio <dialog> (o conteúdo fica num filho).
  function clique(e: MouseEvent<HTMLDialogElement>) {
    if (e.target === e.currentTarget) aoFecharRef.current();
  }

  return (
    <dialog
      ref={ref}
      role={papel === "alertdialog" ? "alertdialog" : undefined}
      aria-modal="true"
      aria-labelledby={tituloId}
      aria-describedby={descricaoId || undefined}
      className={["dialogo", className].filter(Boolean).join(" ")}
      onKeyDown={teclas}
      onCancel={(e) => {
        e.preventDefault(); // o Esc nativo também passa por aqui: quem fecha é o aoFechar
        aoFecharRef.current();
      }}
      onClick={clique}
    >
      <div className="dialogo-caixa">{children}</div>
    </dialog>
  );
}
