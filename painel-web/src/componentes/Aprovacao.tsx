import "./imagensNoVideo.css";
import { useState } from "react";
import { Aprovacao as EstadoAprovacao, CorteDetalhe, aprovarCorte, caminhoCorte, pedir } from "../api";
import { mensagem } from "./imagensComum";

const CONFIRMA =
  "Aprovar este corte? O corte.mp4 vai para video-final/ como corte-aprovado.mp4 e passa a ser o vídeo que o agendar publica.";
const DESATUALIZADA = "As imagens mudaram desde a última montagem.";

interface Props {
  ep: string;
  n: number | string;
  aprovacao: EstadoAprovacao | undefined;
  /** Há uma montagem (troca de música ou imagens) deste corte em andamento. */
  montando: boolean;
  /** Depois de aprovar: a tela recarrega o corte (selo e vídeos). */
  aoMudar: () => void;
}

/** Botão de aprovar o corte da esteira: copia o corte.mp4 para video-final/. */
export function Aprovacao({ ep, n, aprovacao, montando, aoMudar }: Props) {
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  if (!aprovacao) return null;
  if (aprovacao.estado === "aprovado") return <span className="selo selo-pronto">Aprovado</span>;
  if (aprovacao.estado === "bloqueado") return <span className="suave">{aprovacao.motivo}</span>;
  const rotulo = aprovacao.estado === "aprovar de novo" ? "Aprovar de novo" : "Aprovar este vídeo";

  async function aprovar() {
    setErro(null);
    setEnviando(true);
    try {
      // O estado de agora (o dono pode ter mudado as imagens depois de abrir a tela).
      const atual = await pedir<Pick<CorteDetalhe, "montagem_desatualizada">>(caminhoCorte(ep, n));
      const texto = atual.montagem_desatualizada ? `${DESATUALIZADA}\n${CONFIRMA}` : CONFIRMA;
      if (!window.confirm(texto)) return;
      await aprovarCorte(ep, n);
      aoMudar();
    } catch (x) {
      setErro(mensagem(x));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <span className="aprovacao">
      <button type="button" disabled={montando || enviando} onClick={() => void aprovar()}>
        {rotulo}
      </button>
      {erro ? (
        <span role="alert" className="mensagem-erro">
          {erro}
        </span>
      ) : null}
    </span>
  );
}
