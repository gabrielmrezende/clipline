import "./esqueleto.css";
import { CSSProperties, ReactNode } from "react";

// Esqueletos de carregamento: a forma do que vem, no lugar do texto "Carregando…". O leitor de tela
// continua ouvindo o texto (escondido da vista); as formas ficam fora da árvore de acessibilidade.

const LARGURAS = ["92%", "78%", "86%", "64%", "88%", "70%"];

function Osso({ largura, altura, className }: { largura?: string; altura?: string; className?: string }) {
  return (
    <span
      className={["osso", className].filter(Boolean).join(" ")}
      style={{ width: largura, height: altura } as CSSProperties}
    />
  );
}

function Carregando({ rotulo, className, children }: { rotulo: string; className?: string; children: ReactNode }) {
  return (
    <div role="status" className={["esqueleto", className].filter(Boolean).join(" ")}>
      <span className="so-leitor">{rotulo}</span>
      <div className="esqueleto-formas" aria-hidden="true">
        {children}
      </div>
    </div>
  );
}

/** Algumas linhas de texto. */
export function EsqueletoLinhas({ rotulo, linhas = 3, className }: { rotulo: string; linhas?: number; className?: string }) {
  return (
    <Carregando rotulo={rotulo} className={className}>
      {Array.from({ length: linhas }, (_, i) => (
        <Osso key={i} largura={LARGURAS[i % LARGURAS.length]} />
      ))}
    </Carregando>
  );
}

/** A lista de episódios: nome, contagem e a barra de progresso. */
export function EsqueletoEpisodios() {
  return (
    <Carregando rotulo="Carregando os episódios…" className="esqueleto-episodios">
      {[0, 1, 2].map((i) => (
        <div key={i} className="esqueleto-episodio">
          <Osso largura={LARGURAS[i + 1]} altura="1.25rem" />
          <Osso largura="7rem" />
          <Osso className="osso-fino" largura="100%" />
        </div>
      ))}
    </Carregando>
  );
}

/** Os cartões dos cortes de um episódio. */
export function EsqueletoCartoes({ quantos = 6 }: { quantos?: number }) {
  return (
    <Carregando rotulo="Carregando os cortes…">
      <div className="cartoes grade">
        {Array.from({ length: quantos }, (_, i) => (
          <div key={i} className="cartao esqueleto-cartao">
            <Osso largura="2.25rem" altura="1.75rem" />
            <Osso largura={LARGURAS[i % LARGURAS.length]} altura="1.1rem" />
            <Osso largura="8rem" altura="1.5rem" className="osso-pilula" />
            <Osso largura="10rem" />
          </div>
        ))}
      </div>
    </Carregando>
  );
}

/** A tela do corte: o monitor com o vídeo vertical e a folha com título e seções. */
export function EsqueletoCorte({ voltar }: { voltar?: ReactNode }) {
  return (
    <main className="corte" aria-busy="true">
      <div className="monitor">
        <div className="players">
          <div className="tela esqueleto-tela" />
        </div>
      </div>
      <div className="folha">
        {voltar}
        <Carregando rotulo="Carregando o corte…" className="esqueleto-folha">
          <Osso largura="70%" altura="2.25rem" />
          <Osso largura="9rem" altura="1.75rem" className="osso-pilula" />
          <div className="esqueleto-secao">
            <Osso largura="8rem" altura="1.25rem" />
            <Osso largura="92%" />
            <Osso largura="84%" />
            <Osso largura="60%" />
          </div>
          <div className="esqueleto-secao">
            <Osso largura="6rem" altura="1.25rem" />
            <Osso largura="88%" />
            <Osso largura="72%" />
          </div>
        </Carregando>
      </div>
    </main>
  );
}

/** Uma tela que ainda não chegou (divisão de código): título e algumas linhas. */
export function EsqueletoTela() {
  return (
    <main className="coluna" aria-busy="true">
      <Carregando rotulo="Carregando…">
        <Osso largura="45%" altura="2.25rem" />
        <Osso largura="92%" />
        <Osso largura="80%" />
        <Osso largura="66%" />
      </Carregando>
    </main>
  );
}
