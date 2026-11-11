import { useCallback, useEffect, useState } from "react";
import { ErroApi, Legenda, Pedido, gravarLegenda, lerLegenda, montarCorte, tempoTexto } from "../api";
import { Alerta, AndamentoPedido, PEDIDO_PERDIDO, ativo, mensagem, useAcompanhamento, useUmaPorVez } from "./imagensComum";

interface Props {
  ep: string;
  n: number | string;
  /** Põe o player no tempo (segundos do corte.mp4). */
  irPara: (segundos: number) => void;
  /** Solta o corte.mp4 do player antes de montar (no Windows, arquivo aberto não pode ser trocado). */
  soltarVideo: () => void;
  aoMudarAndamento: (montando: boolean) => void;
  aoTerminarMontagem: () => void;
  montandoNaTela: boolean;
}

/** Texto das telas da legenda, uma por linha do formulário; montar de novo aplica no corte.mp4. */
export function EditorLegenda({ ep, n, irPara, soltarVideo, aoMudarAndamento, aoTerminarMontagem, montandoNaTela }: Props) {
  const [legenda, setLegenda] = useState<Legenda | null>(null);
  const [rascunho, setRascunho] = useState<Record<number, string>>({});
  const [erro, setErro] = useState<string | null>(null);
  const [salvo, setSalvo] = useState(false);
  const [aberto, setAberto] = useState(false);
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [ocupado, umaPorVez] = useUmaPorVez();

  const carregar = useCallback(() => {
    lerLegenda(ep, n)
      .then((l) => {
        setLegenda(l);
        setRascunho({});
      })
      .catch((x) => setErro(x instanceof ErroApi && x.status === 404 ? null : mensagem(x)));
  }, [ep, n]);

  useEffect(carregar, [carregar]);
  useAcompanhamento(
    pedido,
    setPedido,
    () => {
      aoMudarAndamento(false);
      aoTerminarMontagem();
    },
    () => {
      aoMudarAndamento(false);
      setErro(PEDIDO_PERDIDO);
    },
  );

  if (!legenda) return null;
  const alteradas = Object.keys(rascunho).length;

  const salvar = () =>
    umaPorVez(async () => {
      setErro(null);
      const telas = Object.entries(rascunho).map(([indice, texto]) => ({
        indice: Number(indice),
        linhas: texto.split("\n").map((l) => l.trim()).filter(Boolean),
      }));
      try {
        const r = await gravarLegenda(ep, n, legenda.versao, telas);
        setLegenda({
          ...legenda,
          versao: r.versao,
          telas: legenda.telas.map((t) => {
            const nova = telas.find((x) => x.indice === t.indice);
            return nova ? { ...t, linhas: nova.linhas } : t;
          }),
        });
        setRascunho({});
        setSalvo(true);
      } catch (x) {
        setErro(mensagem(x));
      }
    });

  const montar = () =>
    umaPorVez(async () => {
      setErro(null);
      soltarVideo();
      aoMudarAndamento(true);
      try {
        setPedido(await montarCorte(ep, n));
        setSalvo(false);
      } catch (x) {
        aoMudarAndamento(false);
        setErro(mensagem(x));
      }
    });

  return (
    <section aria-labelledby="titulo-legenda" className="editor-legenda">
      <h2 id="titulo-legenda">Legenda</h2>
      <Alerta texto={erro} />
      <p>
        <button type="button" aria-expanded={aberto} onClick={() => setAberto((a) => !a)}>
          {aberto ? "Esconder as telas" : `Editar o texto (${legenda.telas.length} telas)`}
        </button>
      </p>
      {aberto ? (
        <ol className="telas-legenda">
          {legenda.telas.map((t) => {
            const valor = rascunho[t.indice] ?? t.linhas.join("\n");
            const longa = valor.split("\n").some((l) => l.trim().length > legenda.max_caracteres);
            return (
              <li key={t.indice}>
                <button type="button" className="alvo-inline" aria-label={`Ir para ${tempoTexto(t.inicio)}`} onClick={() => irPara(t.inicio)}>
                  {tempoTexto(t.inicio)}
                </button>
                <textarea
                  aria-label={`Tela ${t.indice + 1}, ${tempoTexto(t.inicio)}`}
                  aria-invalid={longa}
                  rows={2}
                  value={valor}
                  onChange={(e) => {
                    setSalvo(false);
                    const texto = e.target.value;
                    setRascunho((r) => {
                      const novo = { ...r };
                      if (texto === t.linhas.join("\n")) delete novo[t.indice];
                      else novo[t.indice] = texto;
                      return novo;
                    });
                  }}
                />
                {longa ? <span className="aviso">⚠ linha com mais de {legenda.max_caracteres} caracteres</span> : null}
              </li>
            );
          })}
        </ol>
      ) : null}
      <p className="acoes-legenda">
        {alteradas > 0 ? (
          <button type="button" className="primario" disabled={ocupado} onClick={() => void salvar()}>
            Salvar {alteradas === 1 ? "1 tela" : `${alteradas} telas`}
          </button>
        ) : null}
        {salvo ? (
          <button type="button" disabled={ocupado || montandoNaTela || ativo(pedido)} onClick={() => void montar()}>
            Montar com a legenda nova
          </button>
        ) : null}
        <span role="status">{salvo ? "Legenda salva. Monte o corte para ver no vídeo." : ""}</span>
      </p>
      {pedido ? <AndamentoPedido pedido={pedido} /> : null}
    </section>
  );
}
