import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bloco,
  Momento,
  OrcamentoIa,
  Pedido,
  ResumoFotos,
  baixarFotosDoEpisodio,
  gerarImagensIaDoEpisodio,
  lerMomentos,
  listarTarefas,
  orcamentoDeIaDoEpisodio,
  plural,
  resumoDeFotosDoEpisodio,
} from "../api";
import {
  AndamentoPedido,
  PEDIDO_PERDIDO,
  ativo,
  ehDeImagens,
  mensagem,
  rotuloDeFotos,
  rotuloDeIa,
  textoDeFotos,
  textoDeIa,
  useAcompanhamento,
} from "./imagensComum";

interface Props {
  ep: string;
  cortes: Bloco[];
}

type Leitura = { momentos: Momento[] } | { erro: string };

const SUBSTITUIDAS = "As fotos baixadas antes nestes cortes serão substituídas.";

function Numeros({ momentos }: { momentos: Momento[] }) {
  const ativos = momentos.filter((m) => !m.descartar);
  if (ativos.length === 0) return <span className="suave">Sem momentos de imagem</span>;
  const fotos = ativos.reduce((soma, m) => soma + m.fotos_prontas.length, 0);
  const prompts = ativos.filter((m) => m.tipo === "ia" && m.aprovado).length;
  const imagens = ativos.reduce((soma, m) => soma + m.ia.length, 0);
  return (
    <span>
      {[
        plural(ativos.length, "momento", "momentos"),
        plural(fotos, "foto baixada", "fotos baixadas"),
        plural(prompts, "prompt aprovado", "prompts aprovados"),
        plural(imagens, "imagem gerada", "imagens geradas"),
      ].join(" · ")}
    </span>
  );
}

export function ImagensDoEpisodio({ ep, cortes }: Props) {
  const [leituras, setLeituras] = useState<Record<number, Leitura>>({});
  const [resumo, setResumo] = useState<ResumoFotos | null>(null);
  const [orcamento, setOrcamento] = useState<OrcamentoIa | null>(null);
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erroPedido, setErroPedido] = useState<string | null>(null);
  const [erroResumo, setErroResumo] = useState<string | null>(null);
  const vivo = useRef(true);
  const numeros = cortes.map((c) => c.numero).join(",");

  const lerCortes = useCallback(async () => {
    const lista = numeros ? numeros.split(",").map(Number) : [];
    const lidos = await Promise.all(
      lista.map(async (n): Promise<[number, Leitura]> => {
        try {
          return [n, { momentos: (await lerMomentos(ep, n)).momentos }];
        } catch (x) {
          return [n, { erro: mensagem(x) }];
        }
      }),
    );
    if (vivo.current) setLeituras(Object.fromEntries(lidos));
  }, [ep, numeros]);

  const lerResumo = useCallback(async () => {
    try {
      const r = await resumoDeFotosDoEpisodio(ep);
      if (vivo.current) {
        setResumo(r);
        setErroResumo(null);
      }
      return r;
    } catch (x) {
      if (vivo.current) setErroResumo(mensagem(x));
      return null;
    }
  }, [ep]);

  const lerOrcamento = useCallback(async () => {
    try {
      const o = await orcamentoDeIaDoEpisodio(ep);
      if (vivo.current) setOrcamento(o);
      return o;
    } catch {
      return null;
    }
  }, [ep]);

  useEffect(() => {
    vivo.current = true;
    void lerCortes();
    void lerResumo();
    void lerOrcamento();
    listarTarefas()
      .then((ts) => {
        const retomar = ts.find((t) => ehDeImagens(t) && t.episodio === ep && ativo(t));
        if (vivo.current && retomar) setPedido(retomar);
      })
      .catch(() => {
        /* sem lista: a aba abre sem andamento */
      });
    return () => {
      vivo.current = false;
    };
  }, [ep, lerCortes, lerResumo, lerOrcamento]);

  useAcompanhamento(
    pedido,
    setPedido,
    () => {
      void lerCortes();
      void lerResumo();
      void lerOrcamento();
    },
    () => {
      setErroPedido(PEDIDO_PERDIDO);
      void lerCortes();
    },
  );

  async function enviarPedido(enviar: () => Promise<Pedido>) {
    setEnviando(true);
    setErroPedido(null);
    try {
      const novo = await enviar();
      if (vivo.current) setPedido(novo);
    } catch (x) {
      if (vivo.current) setErroPedido(mensagem(x));
    } finally {
      if (vivo.current) setEnviando(false);
    }
  }

  async function baixar() {
    setErroPedido(null);
    const r = await lerResumo();
    if (!r) return;
    if (window.confirm(textoDeFotos(r, SUBSTITUIDAS))) await enviarPedido(() => baixarFotosDoEpisodio(ep));
  }

  async function gerar() {
    setErroPedido(null);
    const o = await lerOrcamento();
    if (!o || o.imagens === 0) return;
    if (window.confirm(textoDeIa(o))) await enviarPedido(() => gerarImagensIaDoEpisodio(ep));
  }

  const ocupado = ativo(pedido) || enviando;

  return (
    <section aria-label="Imagens do episódio" className="bloco-imagens">
      <div className="acoes-musica">
        <button type="button" disabled={ocupado || !resumo || resumo.fotos === 0} onClick={() => void baixar()}>
          {rotuloDeFotos(resumo)}
        </button>
        <button type="button" disabled={ocupado || !orcamento || orcamento.imagens === 0} onClick={() => void gerar()}>
          {rotuloDeIa(orcamento)}
        </button>
      </div>
      {erroResumo ? (
        <p role="alert" className="mensagem-erro">
          {erroResumo}
        </p>
      ) : null}
      {erroPedido ? (
        <p role="alert" className="mensagem-erro">
          {erroPedido}
        </p>
      ) : null}
      {pedido ? <AndamentoPedido pedido={pedido} /> : null}
      {cortes.length === 0 ? <p>Nenhum corte neste episódio.</p> : null}
      <ul className="resumo-cortes">
        {cortes.map((c) => {
          const leitura = leituras[c.numero];
          return (
            <li key={c.numero}>
              <Link to={`/episodios/${encodeURIComponent(ep)}/cortes/${c.numero}`} className="alvo-inline">
                {c.numero}. {c.titulo}
              </Link>
              <p>
                {!leitura ? (
                  <span className="suave">Carregando…</span>
                ) : "erro" in leitura ? (
                  <span role="alert" className="mensagem-erro">
                    {leitura.erro}
                  </span>
                ) : (
                  <Numeros momentos={leitura.momentos} />
                )}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
