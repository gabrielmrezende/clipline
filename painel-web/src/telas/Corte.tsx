import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CorteDetalhe, ErroApi, caminhoCorte, pedir } from "../api";
import { BlocoImagens } from "../componentes/BlocoImagens";
import { BlocoMusica } from "../componentes/BlocoMusica";
import { EditorPost } from "../componentes/EditorPost";
import { Markdown } from "../componentes/Markdown";
import { Players } from "../componentes/Players";
import { Selo } from "../componentes/Selo";

const CORTE_NAO_MONTADO = "corte não montado";

export function Corte() {
  const { ep = "", n = "" } = useParams();
  const [dados, setDados] = useState<CorteDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [versaoVideo, setVersaoVideo] = useState<string | null>(null);
  const [sinalPost, setSinalPost] = useState(0);
  const [montando, setMontando] = useState(false);
  const [comMomentos, setComMomentos] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    setDados(null);
    setErro(null);
    setVersaoVideo(null);
    setMontando(false);
    setComMomentos(false);
    pedir<CorteDetalhe>(caminhoCorte(ep, n))
      .then(setDados)
      .catch((x) => setErro(x instanceof ErroApi ? x.detail : "Erro inesperado."));
  }, [ep, n]);

  const voltar = (
    <p>
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
    <main className="coluna">
      {voltar}
      <h1>
        {bloco.numero}. {bloco.titulo}
      </h1>
      <p>{montando ? <span className="suave">montando…</span> : <Selo valor={bloco.selo} />}</p>
      <div className="corte-layout">
        <div className="corte-esquerda">
          <Players
            ep={ep}
            n={n}
            videoFinal={bloco.video_final}
            videoRef={videoRef}
            versao={versaoVideo}
            montando={montando}
          />
          <BlocoMusica
            key={`${ep}/${n}`}
            ep={ep}
            n={n}
            videoFinal={bloco.video_final}
            tempoDoPlayer={() => videoRef.current?.currentTime ?? 0}
            soltarVideo={soltarVideo}
            aoMudarAndamento={setMontando}
            aoTerminar={aoTerminarTroca}
          />
          <section aria-labelledby="titulo-info" className="info-corte">
            <h2 id="titulo-info">Informações</h2>
            <dl>
              <dt>Redes</dt>
              <dd>{bloco.redes.join(", ") || "Nenhuma"}</dd>
              <dt>Data</dt>
              <dd>{bloco.data || "Sem data"}</dd>
              <dt>Música</dt>
              <dd>{bloco.musica ?? "Sem música"}</dd>
              <dt>Antes</dt>
              <dd>{bloco.antes || "—"}</dd>
              <dt>Depois</dt>
              <dd>{bloco.depois || "—"}</dd>
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
          <BlocoImagens key={`imagens-${ep}/${n}`} ep={ep} n={n} irPara={irPara} aoCarregar={setComMomentos} />
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
                    <img
                      loading="lazy"
                      src={`${base}/imagens/${encodeURIComponent(nome)}`}
                      alt={nome}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
        <div className="corte-direita">
          <EditorPost ep={ep} n={n} recarregarSinal={sinalPost} />
        </div>
      </div>
    </main>
  );
}
