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
  montarCorte,
  orcamentoDeIa,
  plural,
  resumoDeFotos,
} from "../api";
import { CartaoMomento } from "./CartaoMomento";
import {
  Alerta,
  AndamentoPedido,
  AvisosDoResumo,
  PEDIDO_PERDIDO,
  ativo,
  ehDeImagens,
  mensagem,
  rotuloDeFotos,
  rotuloDeIa,
  textoDeFotos,
  textoDeIa,
  useAcompanhamento,
  useUmaPorVez,
} from "./imagensComum";

interface Props {
  ep: string;
  n: number | string;
  /** Põe o player do corte no tempo (em segundos) e dá play. */
  irPara: (segundos: number) => void;
  /** Avisa a tela se há momentos: com eles, o bloco substitui o guia e a lista de miniaturas. */
  aoCarregar?: (temMomentos: boolean) => void;
  /** Solta o corte.mp4 do player antes de montar (no Windows, arquivo aberto não pode ser trocado). */
  soltarVideo?: () => void;
  /** true ao pedir a montagem; false quando ela termina (ou falha). */
  aoMudarAndamento?: (montando: boolean) => void;
  /** A montagem terminou: a tela recarrega o vídeo e o selo. */
  aoTerminarMontagem?: () => void;
  /** A tela está montando o corte (troca de música ou imagens): não dá para pedir outra montagem. */
  montandoNaTela?: boolean;
}

const ESPERA_RESUMOS_MS = 500;
const SUBSTITUIDAS = "As fotos baixadas antes neste corte serão substituídas.";
const DESATUALIZADA = "As imagens mudaram desde a última montagem.";

export function textoDeMontar(imagens: number): string {
  return `Montar o corte de novo com ${plural(imagens, "imagem", "imagens")}? O corte.mp4 atual será substituído (leva cerca de 1 minuto).`;
}

const emOrdem = (lista: Momento[]) => [...lista].sort((a, b) => a.inicio - b.inicio);

export function BlocoImagens({
  ep,
  n,
  irPara,
  aoCarregar,
  soltarVideo,
  aoMudarAndamento,
  aoTerminarMontagem,
  montandoNaTela = false,
}: Props) {
  const [momentos, setMomentos] = useState<Momento[] | null>(null);
  const [erroLeitura, setErroLeitura] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [erros, setErros] = useState<Record<string, string>>({});
  const [resumo, setResumo] = useState<ResumoFotos | null>(null);
  const [erroResumo, setErroResumo] = useState<string | null>(null);
  const [orcamento, setOrcamento] = useState<OrcamentoIa | null>(null);
  const [erroOrcamento, setErroOrcamento] = useState<string | null>(null);
  const [avisoGlossario, setAvisoGlossario] = useState<string | null>(null);
  const [preparando, umaPorVez] = useUmaPorVez();
  const [config, setConfig] = useState<ConfigImagens | null>(null);
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [erroPedido, setErroPedido] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [desatualizada, setDesatualizada] = useState(false);
  const montandoAgora = useRef(false);
  const versao = useRef("");
  const carregou = useRef(false);
  const cadeia = useRef<Promise<void>>(Promise.resolve());
  const emVoo = useRef(0);
  const espera = useRef<ReturnType<typeof setTimeout> | null>(null);
  const aoCarregarRef = useRef(aoCarregar);
  aoCarregarRef.current = aoCarregar;
  const montagemRef = useRef({ aoMudarAndamento, aoTerminarMontagem });
  montagemRef.current = { aoMudarAndamento, aoTerminarMontagem };

  /** Fim (ou perda) de uma montagem pedida aqui: devolve o player à tela e manda recarregar o corte. */
  const terminarMontagem = useCallback(() => {
    if (!montandoAgora.current) return;
    montandoAgora.current = false;
    montagemRef.current.aoMudarAndamento?.(false);
    montagemRef.current.aoTerminarMontagem?.();
  }, []);

  const carregar = useCallback(async () => {
    try {
      const d = await lerMomentos(ep, n);
      versao.current = d.versao;
      carregou.current = true;
      setMomentos(emOrdem(d.momentos));
      setErroLeitura(null);
      setAvisoGlossario(d.aviso_glossario ?? null);
      setDesatualizada(Boolean(d.montagem_desatualizada));
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
      setErroResumo(null);
      return r;
    } catch (x) {
      setErroResumo(mensagem(x));
      return null;
    }
  }, [ep, n]);

  const lerOrcamento = useCallback(async () => {
    try {
      const o = await orcamentoDeIa(ep, n);
      setOrcamento(o);
      setErroOrcamento(null);
      return o;
    } catch (x) {
      setErroOrcamento(mensagem(x));
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
        if (vivo && retomar) {
          setPedido(retomar);
          if (retomar.tipo === "montar") {
            montandoAgora.current = true;
            montagemRef.current.aoMudarAndamento?.(true);
          }
        }
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
      terminarMontagem();
    },
    () => {
      setErroPedido(PEDIDO_PERDIDO);
      void carregar();
      terminarMontagem();
    },
  );

  function falhou(chave: string, x: unknown) {
    if (x instanceof ErroApi && x.status === 409) setAviso(x.detail);
    else setErros((e) => ({ ...e, [chave]: mensagem(x) }));
  }

  /**
   * Um pedido de cada vez, na ordem dos cliques: cada um precisa da versão que o anterior gerou.
   * `sempre`: a resposta redesenha o cartão mesmo com outros pedidos a caminho (a busca troca as candidatas).
   */
  function enfileirar(chave: string, enviar: () => Promise<RespostaMomento>, sempre = false) {
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
        if (r.montagem_desatualizada !== undefined) setDesatualizada(r.montagem_desatualizada);
        emVoo.current -= 1;
        // Só a última resposta da fila redesenha: as anteriores apagariam cliques que ainda estão a caminho.
        if (sempre || emVoo.current === 0) {
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
    enfileirar(chave, () => buscarOutras(ep, n, chave, versao.current, busca), true);
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

  // Baixar e Gerar esperam os cliques que ainda estão a caminho (a fila de PUTs) antes de ler o
  // resumo ou o orçamento: a confirmação mostra o estado já gravado e o POST manda exatamente isso.
  function baixar() {
    return umaPorVez(async () => {
      setErroPedido(null);
      await cadeia.current;
      const r = await lerResumo();
      if (!r) return;
      if (window.confirm(textoDeFotos(r, SUBSTITUIDAS))) await enviarPedido(() => baixarFotos(ep, n));
    });
  }

  function gerar() {
    return umaPorVez(async () => {
      setErroPedido(null);
      await cadeia.current;
      const o = await lerOrcamento();
      if (!o || o.imagens === 0) return;
      if (window.confirm(textoDeIa(o))) await enviarPedido(() => gerarImagensIa(ep, n, o.itens));
    });
  }

  /** Monta o corte de novo com as imagens marcadas; os cliques a caminho gravam antes da contagem. */
  function montarDeNovo() {
    return umaPorVez(async () => {
      setErroPedido(null);
      await cadeia.current;
      const imagens = (momentos ?? []).filter((m) => !m.descartar && m.no_video).length;
      if (!window.confirm(textoDeMontar(imagens))) return;
      soltarVideo?.();
      montandoAgora.current = true;
      aoMudarAndamento?.(true);
      setEnviando(true);
      try {
        setPedido(await montarCorte(ep, n));
      } catch (x) {
        setErroPedido(mensagem(x));
        montandoAgora.current = false;
        aoMudarAndamento?.(false);
      } finally {
        setEnviando(false);
      }
    });
  }

  /** "Gerar (de novo)" de um cartão, já confirmado nele: a aprovação a caminho grava antes do pedido. */
  function gerarUma(chave: string) {
    return umaPorVez(async () => {
      await cadeia.current;
      await enviarPedido(() => gerarDeNovoIa(ep, n, chave), chave);
    });
  }

  if (momentos === null || momentos.length === 0) {
    return erroLeitura ? (
      <p role="alert" className="mensagem-erro">
        {erroLeitura}
      </p>
    ) : null;
  }

  const ocupado = ativo(pedido) || enviando || preparando;
  const fotosAtivas = ativo(pedido) && pedido?.tipo === "fotos";
  const iaAtiva = ativo(pedido) && pedido?.tipo === "ia";
  const precoIa = config?.provedores?.[config.provedor]?.preco_usd ?? null;

  return (
    <section aria-labelledby="titulo-imagens" className="bloco-imagens">
      <h2 id="titulo-imagens">Imagens</h2>
      <Alerta texto={erroLeitura} />
      <Alerta texto={avisoGlossario} />
      <Alerta texto={aviso} />
      <div className="acoes-musica">
        <button type="button" disabled={ocupado || !resumo || resumo.fotos === 0} onClick={() => void baixar()}>
          {rotuloDeFotos(resumo)}
        </button>
        <button type="button" disabled={ocupado || !orcamento || orcamento.imagens === 0} onClick={() => void gerar()}>
          {rotuloDeIa(orcamento)}
        </button>
        <button type="button" disabled={ocupado || montandoNaTela} onClick={() => void montarDeNovo()}>
          Montar com as imagens
        </button>
      </div>
      {desatualizada && !ativo(pedido) ? <p className="aviso">{DESATUALIZADA}</p> : null}
      <AvisosDoResumo resumo={resumo} />
      <Alerta texto={erroResumo === avisoGlossario ? null : erroResumo} />
      <Alerta texto={erroOrcamento} />
      <Alerta texto={erroPedido} />
      {pedido ? <AndamentoPedido pedido={pedido} /> : null}
      <ul className="momentos">
        {momentos.map((m) => (
          <CartaoMomento
            key={m.chave}
            m={m}
            ep={ep}
            n={n}
            bloqueado={fotosAtivas}
            gerando={iaAtiva || enviando || preparando}
            erro={erros[m.chave] ?? null}
            precoIa={precoIa}
            irPara={irPara}
            alterar={(corpo, otimista) => alterar(m.chave, corpo, otimista)}
            buscar={(busca) => buscar(m.chave, busca)}
            gerarDeNovo={() => void gerarUma(m.chave)}
          />
        ))}
      </ul>
    </section>
  );
}
