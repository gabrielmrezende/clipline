import { useCallback, useEffect, useState } from "react";
import {
  ErroApi,
  ItemPublicacao,
  Pedido,
  Publicacao,
  ResumoPublicacao,
  cancelarPublicacao,
  confirmarPublicacao,
  lerPublicacao,
  resumoDaPublicacao,
} from "../api";
import { Alerta, AndamentoPedido, PEDIDO_PERDIDO, ativo, mensagem, useAcompanhamento, useUmaPorVez } from "./imagensComum";

const REDES = [
  { id: "youtube", rotulo: "YouTube" },
  { id: "instagram", rotulo: "Instagram" },
  { id: "tiktok", rotulo: "TikTok" },
];

const ESTADOS: Record<string, string> = {
  agendado: "agendado",
  enviando: "enviando",
  privado: "no YouTube como privado",
  rascunho: "nos rascunhos do TikTok",
  publicado: "publicado",
  erro: "erro",
  conferir: "conferir no app",
};

/** "2026-11-08 18:00" (aprovados.json) para o campo datetime-local ("2026-11-08T18:00"). */
export function paraCampo(data: string): string {
  return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(data) ? data.replace(" ", "T") : "";
}

interface Props {
  ep: string;
  n: number | string;
}

/**
 * Agendar a publicação pelo painel: o dono vê o mesmo resumo do `publicar agendar` e confirma ali.
 * A confirmação leva a marca do resumo: se algo mudou desde então, o painel recusa e pede para ver de novo.
 */
export function BlocoPublicacao({ ep, n }: Props) {
  const [dados, setDados] = useState<Publicacao | null>(null);
  const [data, setData] = useState("");
  const [redes, setRedes] = useState<string[]>([]);
  const [resumo, setResumo] = useState<ResumoPublicacao | null>(null);
  const [problemas, setProblemas] = useState<string[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [ocupado, umaPorVez] = useUmaPorVez();
  const [indisponivel, setIndisponivel] = useState(false);

  const carregar = useCallback(() => {
    lerPublicacao(ep, n)
      .then((d) => {
        setDados(d);
        setData((atual) => atual || paraCampo(d.data));
        setRedes((atual) => (atual.length ? atual : d.redes));
      })
      .catch((x) => {
        if (x instanceof ErroApi && x.status === 404) setIndisponivel(true); // painel antigo ou corte sem bloco
        else setErro(mensagem(x));
      });
  }, [ep, n]);

  useEffect(carregar, [carregar]);
  useAcompanhamento(pedido, setPedido, carregar, () => setErro(PEDIDO_PERDIDO));
  if (indisponivel) return null;

  function alternar(rede: string) {
    setResumo(null);
    setRedes((atual) => (atual.includes(rede) ? atual.filter((r) => r !== rede) : [...atual, rede]));
  }

  const verResumo = () =>
    umaPorVez(async () => {
      setErro(null);
      setProblemas([]);
      setResumo(null);
      try {
        setResumo(await resumoDaPublicacao(ep, n, data, redes));
      } catch (x) {
        const lista = x instanceof ErroApi && Array.isArray(x.corpo?.problemas) ? (x.corpo?.problemas as string[]) : [];
        if (lista.length) setProblemas(lista);
        else setErro(mensagem(x));
      }
    });

  const confirmar = () =>
    umaPorVez(async () => {
      if (!resumo) return;
      setErro(null);
      try {
        setPedido(await confirmarPublicacao(ep, n, data, redes, resumo.marca));
        setResumo(null);
      } catch (x) {
        setErro(mensagem(x));
        if (x instanceof ErroApi && x.status === 409) setResumo(null);
      }
    });

  const cancelar = (item: ItemPublicacao) =>
    umaPorVez(async () => {
      try {
        const r = await cancelarPublicacao(ep, n, [item.rede]);
        setDados((d) => (d ? { ...d, itens: r.itens } : d));
      } catch (x) {
        setErro(mensagem(x));
      }
    });

  const andando = ativo(pedido);

  return (
    <section aria-labelledby="titulo-publicar" className="bloco-publicar">
      <h2 id="titulo-publicar">Publicar</h2>
      <Alerta texto={erro} />
      {dados && dados.itens.length > 0 ? (
        <ul className="fila-publicacao" aria-label="Publicações deste corte">
          {dados.itens.map((i) => (
            <li key={`${i.rede}-${i.data}`}>
              <strong>{REDES.find((r) => r.id === i.rede)?.rotulo ?? i.rede}</strong>{" "}
              <span>{i.data.slice(0, 16).replace("T", " ")}</span> <span className="suave">{ESTADOS[i.estado] ?? i.estado}</span>
              {i.link ? (
                <>
                  {" "}
                  <a href={i.link} target="_blank" rel="noreferrer">
                    abrir
                  </a>
                </>
              ) : null}
              {i.erro ? <span className="aviso"> ⚠ {i.erro}</span> : null}
              {i.estado === "agendado" ? (
                <button type="button" disabled={ocupado} onClick={() => void cancelar(i)}>
                  Cancelar
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="campos-publicar">
        <label htmlFor={`data-${n}`}>Data e hora (Brasília)</label>
        <input
          id={`data-${n}`}
          type="datetime-local"
          value={data}
          onChange={(e) => {
            setData(e.target.value);
            setResumo(null);
          }}
        />
        <fieldset>
          <legend>Redes</legend>
          {REDES.map((r) => (
            <label key={r.id} className="opcao-rede">
              <input type="checkbox" checked={redes.includes(r.id)} onChange={() => alternar(r.id)} /> {r.rotulo}
            </label>
          ))}
        </fieldset>
      </div>
      <p>
        <button type="button" disabled={ocupado || andando || !data || redes.length === 0} onClick={() => void verResumo()}>
          Ver o resumo
        </button>
      </p>
      {problemas.length > 0 ? (
        <ul className="alertas" aria-label="O que falta para agendar">
          {problemas.map((p, i) => (
            <li key={i} className="aviso">
              ⚠ {p}
            </li>
          ))}
        </ul>
      ) : null}
      {resumo ? (
        <div className="resumo-publicacao">
          <pre tabIndex={0} aria-label="Resumo da publicação">
            {resumo.resumo}
          </pre>
          <p>Confira tudo acima. Ao confirmar, o YouTube recebe o vídeo agora e as outras redes entram na fila.</p>
          <button type="button" className="primario" disabled={ocupado || andando} onClick={() => void confirmar()}>
            Confirmar o agendamento
          </button>
        </div>
      ) : null}
      {pedido ? <AndamentoPedido pedido={pedido} /> : null}
    </section>
  );
}
