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
  gerarDeNovoIa,
  gerarImagensIa,
  lerMomentos,
  listarTarefas,
  orcamentoDeIa,
  resumoDeFotos,
} from "../api";
import { CartaoMomento } from "./CartaoMomento";
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
  n: number | string;
  /** Põe o player do corte no tempo (em segundos) e dá play. */
  irPara: (segundos: number) => void;
  /** Avisa a tela se há momentos: com eles, o bloco substitui o guia e a lista de miniaturas. */
  aoCarregar?: (temMomentos: boolean) => void;
}

const ESPERA_RESUMOS_MS = 500;
const SUBSTITUIDAS = "As fotos baixadas antes neste corte serão substituídas.";

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
  const [erroPedido, setErroPedido] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const versao = useRef("");
  const carregou = useRef(false);
  const cadeia = useRef<Promise<void>>(Promise.resolve());
  const emVoo = useRef(0);
  const espera = useRef<ReturnType<typeof setTimeout> | null>(null);
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

  // Consulta o pedido até ele terminar; ao terminar, recarrega tudo uma vez.
  useAcompanhamento(
    pedido,
    setPedido,
    () => {
      void carregar();
      void lerResumo();
      void lerOrcamento();
    },
    () => {
      setErroPedido(PEDIDO_PERDIDO);
      void carregar();
    },
  );

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
    if (window.confirm(textoDeFotos(r, SUBSTITUIDAS))) await enviarPedido(() => baixarFotos(ep, n));
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
    if (window.confirm(textoDeIa(o))) await enviarPedido(() => gerarImagensIa(ep, n));
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
          {rotuloDeFotos(resumo)}
        </button>
        <button type="button" disabled={ocupado || !orcamento || orcamento.imagens === 0} onClick={() => void gerar()}>
          {rotuloDeIa(orcamento)}
        </button>
      </div>
      {erroPedido ? (
        <p role="alert" className="mensagem-erro">
          {erroPedido}
        </p>
      ) : null}
      {pedido ? <AndamentoPedido pedido={pedido} /> : null}
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
