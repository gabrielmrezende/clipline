import { MouseEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CorteDetalhe, ErroApi, Momento, caminhoCorte, pedir } from "../api";
import { BlocoImagens } from "../componentes/BlocoImagens";
import { Aprovacao } from "../componentes/Aprovacao";
import { BlocoMusica } from "../componentes/BlocoMusica";
import { BlocoPublicacao } from "../componentes/BlocoPublicacao";
import { EditorLegenda } from "../componentes/EditorLegenda";
import { EditorPost } from "../componentes/EditorPost";
import { LinhaDoCorte } from "../componentes/LinhaDoCorte";
import { Markdown } from "../componentes/Markdown";
import { Players } from "../componentes/Players";
import { Selo } from "../componentes/Selo";

const CORTE_NAO_MONTADO = "corte não montado";

const SECOES = [
  { id: "titulo-info", rotulo: "Informações" },
  { id: "titulo-musica", rotulo: "Música" },
  { id: "titulo-imagens", rotulo: "Imagens" },
  { id: "titulo-legenda", rotulo: "Legenda" },
  { id: "titulo-post", rotulo: "Post" },
  { id: "titulo-publicar", rotulo: "Publicar" },
];

/** A seção cujo título já passou do topo da tela (para marcar o atalho dela). */
function useSecaoAtual(ids: string[]): string {
  const chave = ids.join("|");
  const [atual, setAtual] = useState(ids[0]);
  useEffect(() => {
    const lista = chave.split("|");
    let quadro = 0;
    function medir() {
      quadro = 0;
      let escolhida = lista[0];
      for (const id of lista) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top < 160) escolhida = id;
      }
      // No fim da página a última seção fica marcada, mesmo que o título dela não chegue ao topo.
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) {
        escolhida = lista[lista.length - 1];
      }
      setAtual(escolhida);
    }
    function aoRolar() {
      if (!quadro) quadro = requestAnimationFrame(medir);
    }
    window.addEventListener("scroll", aoRolar, { passive: true });
    return () => {
      window.removeEventListener("scroll", aoRolar);
      if (quadro) cancelAnimationFrame(quadro);
    };
  }, [chave]);
  return atual;
}

function irParaSecao(e: MouseEvent<HTMLAnchorElement>, id: string) {
  e.preventDefault();
  const reduzir = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(id)?.scrollIntoView?.({ behavior: reduzir ? "auto" : "smooth", block: "start" });
}

export function Corte() {
  const { ep = "", n = "" } = useParams();
  const [dados, setDados] = useState<CorteDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [versaoVideo, setVersaoVideo] = useState<string | null>(null);
  const [sinalPost, setSinalPost] = useState(0);
  const [montando, setMontando] = useState(false);
  const [comMomentos, setComMomentos] = useState(false);
  const [momentos, setMomentos] = useState<Momento[]>([]);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [elVideo, setElVideo] = useState<HTMLVideoElement | null>(null);
  // O <video> é recriado quando muda o arquivo: a linha do corte precisa do elemento da vez.
  const refVideo = useCallback((el: HTMLVideoElement | null) => {
    videoRef.current = el;
    setElVideo(el);
  }, []);

  const temImagens = comMomentos || (dados?.imagens.length ?? 0) > 0;
  const secoes = SECOES.filter((s) => s.id !== "titulo-imagens" || temImagens);
  const secaoAtual = useSecaoAtual(secoes.map((s) => s.id));

  useEffect(() => {
    setDados(null);
    setErro(null);
    setVersaoVideo(null);
    setMontando(false);
    setComMomentos(false);
    setMomentos([]);
    let vivo = true; // trocar de corte rápido: a resposta do corte anterior não pode cobrir a deste
    pedir<CorteDetalhe>(caminhoCorte(ep, n))
      .then((d) => vivo && setDados(d))
      .catch((x) => vivo && setErro(x instanceof ErroApi ? x.detail : "Erro inesperado."));
    return () => {
      vivo = false;
    };
  }, [ep, n]);

  const voltar = (
    <p className="voltar">
      <Link to={`/episodios/${encodeURIComponent(ep)}`} className="alvo-inline">
        ← {ep}
      </Link>
    </p>
  );

  if (erro) {
    return (
      <main className="coluna">
        {voltar}
        <p role="alert" className="mensagem-erro">
          {erro}
        </p>
      </main>
    );
  }
  if (!dados) {
    return (
      <main className="coluna">
        {voltar}
        <p>Carregando…</p>
      </main>
    );
  }

  const { bloco, guia, imagens } = dados;
  const base = caminhoCorte(ep, n);

  /** Depois da troca: selo, "Música" das Informações, vídeo e editor do post de novo. */
  function aoTerminarTroca() {
    setVersaoVideo(String(Date.now()));
    setSinalPost((s) => s + 1);
    pedir<CorteDetalhe>(caminhoCorte(ep, n))
      .then(setDados)
      .catch(() => {
        /* fica o que já estava na tela */
      });
  }

  /** Solta o corte.mp4 antes da troca: no Windows, arquivo aberto no player não pode ser trocado. */
  function soltarVideo() {
    const video = videoRef.current;
    if (video) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    }
    setMontando(true);
  }

  /** ▶ de um momento: põe o player do corte no tempo e dá play. */
  function irPara(segundos: number) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = segundos;
    const tocando = video.play();
    if (tocando && typeof tocando.catch === "function") tocando.catch(() => {});
  }

  return (
    <main className="corte">
      <div className="monitor">
        <Players
          ep={ep}
          n={n}
          videoFinal={bloco.video_final}
          videoRef={refVideo}
          versao={versaoVideo}
          montando={montando}
        />
        <LinhaDoCorte video={elVideo} momentos={momentos} irPara={irPara} />
      </div>
      <div className="folha">
        <header>
          {voltar}
          <h1>
            {bloco.numero}. {bloco.titulo}
          </h1>
          <p className="selo-e-aprovacao">
            {montando ? <span className="suave">montando…</span> : <Selo valor={bloco.selo} />}{" "}
            <Aprovacao ep={ep} n={n} aprovacao={dados.aprovacao} montando={montando} aoMudar={aoTerminarTroca} />
          </p>
        </header>
        <nav className="secoes" aria-label="Seções do corte">
            {secoes.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              aria-current={secaoAtual === s.id ? "true" : undefined}
              onClick={(e) => irParaSecao(e, s.id)}
            >
              {s.rotulo}
            </a>
          ))}
        </nav>
        <section aria-labelledby="titulo-info" className="info-corte">
          <h2 id="titulo-info">Informações</h2>
          <dl>
            <dt>Redes</dt>
            <dd className="redes">{bloco.redes.join(", ") || "Nenhuma"}</dd>
            <dt>Data</dt>
            <dd>{bloco.data || "Sem data"}</dd>
            <dt>Música</dt>
            <dd>{bloco.musica ?? "Sem música"}</dd>
            <dt>Antes</dt>
            <dd className={bloco.antes ? "fala" : undefined}>{bloco.antes || "—"}</dd>
            <dt>Depois</dt>
            <dd className={bloco.depois ? "fala" : undefined}>{bloco.depois || "—"}</dd>
          </dl>
          {bloco.erro && !(montando && bloco.erro === CORTE_NAO_MONTADO) ? (
            <p role="alert" className="mensagem-erro">
              {bloco.erro}
            </p>
          ) : null}
          {bloco.alertas.length > 0 ? (
            <ul className="alertas">
              {bloco.alertas.map((a, i) => (
                <li key={i} className="aviso">
                  ⚠ {a}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
        <BlocoMusica
          key={`${ep}/${n}`}
          ep={ep}
          n={n}
          videoFinal={bloco.video_final}
          tempoDoPlayer={() => videoRef.current?.currentTime ?? 0}
          soltarVideo={soltarVideo}
          aoMudarAndamento={setMontando}
          aoTerminar={aoTerminarTroca}
          montandoNaTela={montando}
        />
        <BlocoImagens
          key={`imagens-${ep}/${n}`}
          ep={ep}
          n={n}
          irPara={irPara}
          aoCarregar={setComMomentos}
          aoMudarMomentos={setMomentos}
          soltarVideo={soltarVideo}
          aoMudarAndamento={setMontando}
          aoTerminarMontagem={aoTerminarTroca}
          montandoNaTela={montando}
        />
        {guia && !comMomentos ? (
          <section aria-label="Guia do corte">
            <Markdown texto={guia} />
          </section>
        ) : null}
        {imagens.length > 0 && !comMomentos ? (
          <section aria-labelledby="titulo-imagens">
            <h2 id="titulo-imagens">Imagens</h2>
            <ul className="miniaturas">
              {imagens.map((nome) => (
                <li key={nome}>
                  <img loading="lazy" src={`${base}/imagens/${encodeURIComponent(nome)}`} alt={nome} />
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <EditorLegenda
          key={`legenda-${ep}/${n}/${versaoVideo ?? ""}`}
          ep={ep}
          n={n}
          irPara={irPara}
          soltarVideo={soltarVideo}
          aoMudarAndamento={setMontando}
          aoTerminarMontagem={aoTerminarTroca}
          montandoNaTela={montando}
        />
        <EditorPost ep={ep} n={n} recarregarSinal={sinalPost} />
        <BlocoPublicacao key={`publicar-${ep}/${n}`} ep={ep} n={n} />
      </div>
    </main>
  );
}
