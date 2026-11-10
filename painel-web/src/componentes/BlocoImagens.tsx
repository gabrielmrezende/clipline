import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlteracaoMomento,
  ConfigImagens,
  ErroApi,
  Momento,
  OrcamentoIa,
  Pedido,
  RespostaMomento,
  ResumoFotos,
  alterarMomento,
  baixarFotos,
  buscarOutras,
  configuracaoDeImagens,
  consultarTarefa,
  formatarDolar,
  formatarMb,
  gerarDeNovoIa,
  gerarImagensIa,
  lerMomentos,
  listarTarefas,
  orcamentoDeIa,
  plural,
  resumoDeFotos,
} from "../api";
import { CartaoMomento } from "./CartaoMomento";

interface Props {
  ep: string;
  n: number | string;
  /** Põe o player do corte no tempo (em segundos) e dá play. */
  irPara: (segundos: number) => void;
  /** Avisa a tela se há momentos: com eles, o bloco substitui o guia e a lista de miniaturas. */
  aoCarregar?: (temMomentos: boolean) => void;
}

const ESPERA_CONSULTA_MS = 2000;
const ESPERA_RESUMOS_MS = 500;
const PEDIDO_PERDIDO = "O pedido se perdeu (o painel foi reiniciado?). Confira as imagens e peça de novo se precisar.";
const SUBSTITUIDAS = "As fotos baixadas antes neste corte serão substituídas.";

const ativo = (p: Pedido | null) => p !== null && (p.estado === "na fila" || p.estado === "montando");
const ehDeImagens = (p: Pedido) => p.tipo === "fotos" || p.tipo === "ia";

function mensagem(x: unknown): string {
  return x instanceof ErroApi ? x.detail : "Erro inesperado.";
}

const emOrdem = (lista: Momento[]) => [...lista].sort((a, b) => a.inicio - b.inicio);

export function BlocoImagens({ ep, n, irPara, aoCarregar }: Props) {
  const [momentos, setMomentos] = useState<Momento[] | null>(null);
  const [erroLeitura, setErroLeitura] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [erros, setErros] = useState<Record<string, string>>({});
  const [resumo, setResumo] = useState<ResumoFotos | null>(null);
  const [orcamento, setOrcamento] = useState<OrcamentoIa | null>(null);
  const [config, setConfig] = useState<ConfigImagens | null>(null);
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [tick, setTick] = useState(0);
  const [erroPedido, setErroPedido] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const versao = useRef("");
  const carregou = useRef(false);
  const cadeia = useRef<Promise<void>>(Promise.resolve());
  const emVoo = useRef(0);
  const espera = useRef<ReturnType<typeof setTimeout> | null>(null);
  const terminados = useRef<Set<string>>(new Set());
  const aoCarregarRef = useRef(aoCarregar);
  aoCarregarRef.current = aoCarregar;

  const carregar = useCallback(async () => {
    try {
      const d = await lerMomentos(ep, n);
      versao.current = d.versao;
      carregou.current = true;
      setMomentos(emOrdem(d.momentos));
      setErroLeitura(null);
      aoCarregarRef.current?.(d.momentos.length > 0);
    } catch (x) {
      setErroLeitura(mensagem(x));
      if (!carregou.current) aoCarregarRef.current?.(false);
    }
  }, [ep, n]);

  const lerResumo = useCallback(async () => {
    try {
      const r = await resumoDeFotos(ep, n);
      setResumo(r);
      return r;
    } catch {
      return null;
    }
  }, [ep, n]);

  const lerOrcamento = useCallback(async () => {
    try {
      const o = await orcamentoDeIa(ep, n);
      setOrcamento(o);
      return o;
    } catch {
      return null;
    }
  }, [ep, n]);

  /** Espera um pouco, para uma sequência de cliques gerar uma leitura só. */
  const agendarResumos = useCallback(() => {
    if (espera.current) clearTimeout(espera.current);
    espera.current = setTimeout(() => {
      espera.current = null;
      void lerResumo();
      void lerOrcamento();
    }, ESPERA_RESUMOS_MS);
  }, [lerResumo, lerOrcamento]);

  useEffect(() => {
    let vivo = true;
    void carregar();
    void lerResumo();
    void lerOrcamento();
    configuracaoDeImagens()
      .then((c) => vivo && setConfig(c))
      .catch(() => {
        /* sem preço: a confirmação de "Gerar de novo" só não mostra o custo */
      });
    listarTarefas()
      .then((ts) => {
        const retomar = ts.find(
          (t) => ehDeImagens(t) && t.episodio === ep && (t.cortes ?? []).includes(Number(n)) && ativo(t),
        );
        if (vivo && retomar) setPedido(retomar);
      })
      .catch(() => {
        /* sem lista: o bloco abre sem andamento */
      });
    return () => {
      vivo = false;
      if (espera.current) clearTimeout(espera.current);
    };
  }, [ep, n, carregar, lerResumo, lerOrcamento]);

  // Consulta o pedido a cada 2 s até ele terminar; ao terminar, recarrega tudo uma vez.
  useEffect(() => {
    if (!pedido) return;
    if (!ativo(pedido)) {
      if (!terminados.current.has(pedido.id)) {
        terminados.current.add(pedido.id);
        void carregar();
        void lerResumo();
        void lerOrcamento();
      }
      return;
    }
    let vivo = true;
    const id = setTimeout(() => {
      consultarTarefa(pedido.id)
        .then((novo) => vivo && setPedido(novo))
        .catch((x) => {
          if (!vivo) return;
          if (x instanceof ErroApi && x.status === 404) {
            setPedido(null);
            setErroPedido(PEDIDO_PERDIDO);
            void carregar();
            return;
          }
          setTick((t) => t + 1);
        });
    }, ESPERA_CONSULTA_MS);
    return () => {
      vivo = false;
      clearTimeout(id);
    };
  }, [pedido, tick, carregar, lerResumo, lerOrcamento]);

  function falhou(chave: string, x: unknown) {
    if (x instanceof ErroApi && x.status === 409) setAviso(x.detail);
    else setErros((e) => ({ ...e, [chave]: mensagem(x) }));
  }

  /** Um pedido de cada vez, na ordem dos cliques: cada um precisa da versão que o anterior gerou. */
  function enfileirar(chave: string, enviar: () => Promise<RespostaMomento>) {
    setErros((e) => {
      const { [chave]: _, ...resto } = e;
      return resto;
    });
    setAviso(null);
    emVoo.current += 1;
    cadeia.current = cadeia.current.then(async () => {
      try {
        const r = await enviar();
        versao.current = r.versao;
        emVoo.current -= 1;
        // Só a última resposta da fila redesenha: as anteriores apagariam cliques que ainda estão a caminho.
        if (emVoo.current === 0) {
          setMomentos((ms) => ms && ms.map((m) => (m.chave === r.momento.chave ? r.momento : m)));
        }
        agendarResumos();
      } catch (x) {
        emVoo.current -= 1;
        falhou(chave, x);
        await carregar();
      }
    });
  }

  function alterar(chave: string, corpo: AlteracaoMomento, otimista: Partial<Momento>) {
    setMomentos((ms) => ms && ms.map((m) => (m.chave === chave ? { ...m, ...otimista } : m)));
    enfileirar(chave, () => alterarMomento(ep, n, chave, versao.current, corpo));
  }

  function buscar(chave: string, busca: string) {
    enfileirar(chave, () => buscarOutras(ep, n, chave, busca));
  }

  async function enviarPedido(enviar: () => Promise<Pedido>, chave?: string) {
    setEnviando(true);
    setErroPedido(null);
    try {
      setPedido(await enviar());
    } catch (x) {
      if (chave) falhou(chave, x);
      else setErroPedido(mensagem(x));
    } finally {
      setEnviando(false);
    }
  }

  async function baixar() {
    setErroPedido(null);
    let r: ResumoFotos;
    try {
      r = await resumoDeFotos(ep, n);
    } catch (x) {
      setErroPedido(mensagem(x));
      return;
    }
    setResumo(r);
    const texto = [
      `Baixar ${plural(r.fotos, "foto", "fotos")} (${formatarMb(r.megabytes)}) de ${r.origem}?`,
      ...r.avisos,
      SUBSTITUIDAS,
    ].join("\n");
    if (window.confirm(texto)) await enviarPedido(() => baixarFotos(ep, n));
  }

  async function gerar() {
    setErroPedido(null);
    let o: OrcamentoIa;
    try {
      o = await orcamentoDeIa(ep, n);
    } catch (x) {
      setErroPedido(mensagem(x));
      return;
    }
    setOrcamento(o);
    if (o.imagens === 0) return;
    const texto = `Gerar ${plural(o.imagens, "imagem", "imagens")} com ${o.provedor} (${o.modelo}), ${formatarDolar(o.custo_usd)}?`;
    if (window.confirm(texto)) await enviarPedido(() => gerarImagensIa(ep, n));
  }

  if (momentos === null || momentos.length === 0) {
    return erroLeitura ? (
      <p role="alert" className="mensagem-erro">
        {erroLeitura}
      </p>
    ) : null;
  }

  const ocupado = ativo(pedido) || enviando;
  const fotosAtivas = ativo(pedido) && pedido?.tipo === "fotos";
  const iaAtiva = ativo(pedido) && pedido?.tipo === "ia";
  const precoIa = config?.provedores?.[config.provedor]?.preco_usd ?? null;

  const rotuloFotos = resumo
    ? `Baixar as fotos escolhidas (${plural(resumo.fotos, "foto", "fotos")}, ${formatarMb(resumo.megabytes)})`
    : "Baixar as fotos escolhidas";
  const rotuloIa = orcamento
    ? `Gerar as aprovadas (${plural(orcamento.imagens, "imagem", "imagens")}, ${formatarDolar(orcamento.custo_usd)})`
    : "Gerar as aprovadas";

  const andamento: Record<Pedido["estado"], string> = {
    "na fila": "Na fila",
    montando: pedido?.progresso || (pedido?.tipo === "ia" ? "Gerando…" : "Baixando…"),
    pronto: "Pronto",
    erro: pedido ? `Erro: ${pedido.mensagem}` : "",
  };

  return (
    <section aria-labelledby="titulo-imagens" className="bloco-imagens">
      <h2 id="titulo-imagens">Imagens</h2>
      {erroLeitura ? (
        <p role="alert" className="mensagem-erro">
          {erroLeitura}
        </p>
      ) : null}
      {aviso ? (
        <p role="alert" className="mensagem-erro">
          {aviso}
        </p>
      ) : null}
      <div className="acoes-musica">
        <button type="button" disabled={ocupado || !resumo || resumo.fotos === 0} onClick={() => void baixar()}>
          {rotuloFotos}
        </button>
        <button type="button" disabled={ocupado || !orcamento || orcamento.imagens === 0} onClick={() => void gerar()}>
          {rotuloIa}
        </button>
      </div>
      {erroPedido ? (
        <p role="alert" className="mensagem-erro">
          {erroPedido}
        </p>
      ) : null}
      {pedido ? (
        <div className="andamento" role="status">
          <p className={pedido.estado === "erro" ? "mensagem-erro" : undefined}>{andamento[pedido.estado]}</p>
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
      ) : null}
      <ul className="momentos">
        {momentos.map((m) => (
          <CartaoMomento
            key={m.chave}
            m={m}
            ep={ep}
            n={n}
            bloqueado={fotosAtivas}
            gerando={iaAtiva || enviando}
            erro={erros[m.chave] ?? null}
            precoIa={precoIa}
            irPara={irPara}
            alterar={(corpo, otimista) => alterar(m.chave, corpo, otimista)}
            buscar={(busca) => buscar(m.chave, busca)}
            gerarDeNovo={() => void enviarPedido(() => gerarDeNovoIa(ep, n, m.chave), m.chave)}
          />
        ))}
      </ul>
    </section>
  );
}
