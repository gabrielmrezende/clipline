import { useEffect, useState } from "react";
import { AlteracaoMomento, Momento, formatarDolar, plural, tempoTexto, urlImagem } from "../api";

const MAXIMO_ESCOLHAS = 3;
const MAXIMO_VERSOES = 3;

export type Alterar = (corpo: AlteracaoMomento, otimista: Partial<Momento>) => void;

interface Props {
  m: Momento;
  ep: string;
  n: number | string;
  /** Fotos sendo baixadas: o servidor recusa qualquer mudança no pedidos.json. */
  bloqueado: boolean;
  /** Há um pedido de imagens em andamento (ou sendo confirmado) neste corte. */
  gerando: boolean;
  erro: string | null;
  /** Preço (US$) de uma imagem no provedor atual, se conhecido. */
  precoIa: number | null;
  irPara: (segundos: number) => void;
  alterar: Alterar;
  buscar: (busca: string) => void;
  gerarDeNovo: () => void;
}

const ROTULO_TIPO: Record<string, string> = { foto: "Foto", ia: "IA", noticia: "Notícia" };

function CorpoFoto({ m, bloqueado, alterar, buscar }: Pick<Props, "m" | "bloqueado" | "alterar" | "buscar">) {
  const [busca, setBusca] = useState(m.busca);
  useEffect(() => setBusca(m.busca), [m.busca]);
  const cheio = m.escolhas.length >= MAXIMO_ESCOLHAS;

  function alternar(k: number) {
    const novas = m.escolhas.includes(k) ? m.escolhas.filter((e) => e !== k) : [...m.escolhas, k];
    alterar({ escolhas: novas }, { escolhas: novas });
  }

  return (
    <>
      <ul className="candidatas">
        {m.candidatas.map((c, i) => {
          const k = i + 1;
          const pos = m.escolhas.indexOf(k) + 1;
          const pronta = pos > 0 && m.fotos_prontas.includes(`${m.chave}-${pos}.jpg`);
          return (
            <li key={k} className={pos > 0 ? "candidata escolhida" : "candidata"}>
              <button
                type="button"
                aria-pressed={pos > 0}
                aria-label={`Candidata ${k}: ${c.titulo ?? ""}${pos > 0 ? `, escolhida em ${pos}º` : ""}`}
                disabled={bloqueado || (cheio && pos === 0)}
                onClick={() => alternar(k)}
              >
                <img loading="lazy" src={c.miniatura} alt="" />
                {pos > 0 ? <span className="ordem">{pos}</span> : null}
              </button>
              <small className="suave-bloco">{[c.autor, c.licenca].filter(Boolean).join(" · ")}</small>
              {pronta ? <span className="pronta">Pronta</span> : null}
            </li>
          );
        })}
      </ul>
      <div className="busca-momento">
        <label>
          Buscar outras
          <input type="text" value={busca} disabled={bloqueado} onChange={(e) => setBusca(e.target.value)} />
        </label>
        <button type="button" disabled={bloqueado || !busca.trim()} onClick={() => buscar(busca.trim())}>
          Buscar
        </button>
      </div>
    </>
  );
}

function CorpoIa({
  m,
  ep,
  n,
  bloqueado,
  alterar,
  gerando,
  precoIa,
  gerarDeNovo,
}: Pick<Props, "m" | "ep" | "n" | "bloqueado" | "alterar" | "gerando" | "precoIa" | "gerarDeNovo">) {
  const [rascunho, setRascunho] = useState(m.prompt);
  useEffect(() => setRascunho(m.prompt), [m.prompt]);
  const salvo = rascunho === m.prompt;
  const aprovado = m.aprovado && salvo;
  const rotuloGerar = m.ia.length > 0 ? "Gerar de novo" : "Gerar";
  const podeGerar =
    aprovado &&
    !gerando &&
    !bloqueado &&
    m.ia.length < MAXIMO_VERSOES &&
    precoIa !== null &&
    m.pessoa_citada === null &&
    m.prompt.trim() !== "";

  function salvarPrompt() {
    if (!salvo) alterar({ prompt: rascunho }, { prompt: rascunho, aprovado: false });
  }

  function mudarAprovado(marcado: boolean) {
    if (marcado) {
      const corpo: AlteracaoMomento = salvo ? { aprovado: true } : { prompt: rascunho, aprovado: true };
      alterar(corpo, { prompt: rascunho, aprovado: true });
    } else {
      alterar({ aprovado: false }, { aprovado: false });
    }
  }

  function novaVersao() {
    if (!podeGerar || precoIa === null) return;
    const texto = `${rotuloGerar} esta imagem: ${plural(1, "imagem", "imagens")}, ${formatarDolar(precoIa)}?`;
    if (window.confirm(texto)) gerarDeNovo();
  }

  return (
    <>
      <label className="campo-bloco">
        Prompt
        <textarea
          rows={3}
          value={rascunho}
          disabled={bloqueado}
          onChange={(e) => setRascunho(e.target.value)}
          onBlur={salvarPrompt}
        />
      </label>
      {m.pessoa_citada ? (
        <p role="alert" className="aviso">
          {`Cita pessoa real (${m.pessoa_citada}): não pode gerar`}
        </p>
      ) : null}
      <label className="aprovado">
        <input
          type="checkbox"
          checked={aprovado}
          disabled={bloqueado || m.pessoa_citada !== null}
          onChange={(e) => mudarAprovado(e.target.checked)}
        />
        Aprovado
      </label>
      {m.ia.length > 0 ? (
        <ul className="candidatas">
          {m.ia.map((v) => (
            <li key={v.arquivo} className="candidata">
              <img loading="lazy" src={urlImagem(ep, n, v.arquivo)} alt={`Versão ${v.versao ?? ""}`} />
              <small className="suave-bloco">{[v.provedor, v.data].filter(Boolean).join(" · ")}</small>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="acoes-musica">
        <button type="button" disabled={!podeGerar} onClick={novaVersao}>
          {rotuloGerar}
        </button>
      </div>
    </>
  );
}

function CorpoNoticia({ m, ep, n }: Pick<Props, "m" | "ep" | "n">) {
  const pronta = m.fotos_prontas[0];
  return (
    <>
      <p>
        <strong>{m.titulo}</strong>
      </p>
      <p className="suave-bloco">{[m.veiculo, m.data].filter(Boolean).join(" · ")}</p>
      {pronta ? (
        <img className="noticia-imagem" loading="lazy" src={urlImagem(ep, n, pronta)} alt={m.titulo} />
      ) : null}
    </>
  );
}

export function CartaoMomento(props: Props) {
  const { m, ep, n, bloqueado, erro, irPara, alterar } = props;
  const tempo = tempoTexto(m.inicio);
  const trocaveis = m.tipo === "foto" || m.tipo === "ia";
  const destino = m.tipo === "foto" ? "ia" : "foto";

  return (
    <li className={m.descartar ? "momento descartado" : "momento"}>
      <div className="momento-topo">
        <button type="button" className="faixa-tocar" aria-label={`Ir para ${tempo}`} onClick={() => irPara(m.inicio)}>
          ▶
        </button>
        <span className="momento-tempo" data-testid="tempo-momento">
          {tempo}
        </span>
        <span className="momento-tipo">{ROTULO_TIPO[m.tipo] ?? m.tipo}</span>
      </div>
      <p className="momento-fala">{m.fala}</p>
      {m.descartar ? null : m.tipo === "foto" ? (
        <CorpoFoto m={m} bloqueado={bloqueado} alterar={alterar} buscar={props.buscar} />
      ) : m.tipo === "ia" ? (
        <CorpoIa
          m={m}
          ep={ep}
          n={n}
          bloqueado={bloqueado}
          alterar={alterar}
          gerando={props.gerando}
          precoIa={props.precoIa}
          gerarDeNovo={props.gerarDeNovo}
        />
      ) : m.tipo === "noticia" ? (
        <CorpoNoticia m={m} ep={ep} n={n} />
      ) : null}
      {erro ? (
        <p role="alert" className="mensagem-erro">
          {erro}
        </p>
      ) : null}
      <div className="acoes-musica">
        {trocaveis && !m.descartar ? (
          <button
            type="button"
            disabled={bloqueado}
            onClick={() => alterar({ tipo: destino }, { tipo: destino, aprovado: false })}
          >
            {destino === "ia" ? "Trocar para IA" : "Trocar para foto"}
          </button>
        ) : null}
        {m.descartar ? (
          <button type="button" disabled={bloqueado} onClick={() => alterar({ descartar: false }, { descartar: false })}>
            Restaurar
          </button>
        ) : (
          <button type="button" disabled={bloqueado} onClick={() => alterar({ descartar: true }, { descartar: true })}>
            Descartar
          </button>
        )}
      </div>
    </li>
  );
}
