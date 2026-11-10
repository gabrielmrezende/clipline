import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ConfigImagens, configuracaoDeImagens, gravarConfiguracaoDeImagens } from "../api";
import { mensagem } from "../componentes/imagensComum";

interface Campos {
  modelo: string;
  qualidade: string;
  preco: string;
}

const PROVEDORES = ["openai", "google"];

function paraCampos(config: ConfigImagens): Record<string, Campos> {
  return Object.fromEntries(
    PROVEDORES.map((p) => {
      const c = config.provedores?.[p] ?? {};
      return [p, { modelo: c.modelo ?? "", qualidade: c.qualidade ?? "", preco: c.preco_usd === undefined ? "" : String(c.preco_usd) }];
    }),
  );
}

export function Configuracoes() {
  const [config, setConfig] = useState<ConfigImagens | null>(null);
  const [provedor, setProvedor] = useState("openai");
  const [campos, setCampos] = useState<Record<string, Campos>>({});
  const [erro, setErro] = useState<string | null>(null);
  const [salvo, setSalvo] = useState(false);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    let vivo = true;
    configuracaoDeImagens()
      .then((c) => {
        if (!vivo) return;
        setConfig(c);
        setProvedor(PROVEDORES.includes(c.provedor) ? c.provedor : PROVEDORES[0]);
        setCampos(paraCampos(c));
      })
      .catch((x) => vivo && setErro(mensagem(x)));
    return () => {
      vivo = false;
    };
  }, []);

  function mudar(p: string, campo: keyof Campos, valor: string) {
    setSalvo(false);
    setCampos((cs) => ({ ...cs, [p]: { ...cs[p], [campo]: valor } }));
  }

  async function salvar() {
    setSalvo(false);
    const provedores: ConfigImagens["provedores"] = {};
    for (const p of PROVEDORES) {
      const c = campos[p];
      const preco = c.preco.trim() === "" ? NaN : Number(c.preco);
      if (!Number.isFinite(preco) || preco < 0) {
        setErro(`Informe o preço por imagem de ${p} (um número igual ou maior que zero).`);
        return;
      }
      provedores[p] = { modelo: c.modelo, qualidade: c.qualidade, preco_usd: preco };
    }
    setErro(null);
    setSalvando(true);
    try {
      const nova = await gravarConfiguracaoDeImagens(provedor, provedores);
      setConfig(nova);
      setSalvo(true);
    } catch (x) {
      setErro(mensagem(x));
    } finally {
      setSalvando(false);
    }
  }

  return (
    <main className="coluna">
      <p>
        <Link to="/" className="alvo-inline">
          ← Episódios
        </Link>
      </p>
      <h1>Configurações</h1>
      {erro ? (
        <p role="alert" className="mensagem-erro">
          {erro}
        </p>
      ) : null}
      {salvo ? <p role="status">Configurações salvas.</p> : null}
      {config ? (
        <form
          className="configuracoes"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void salvar();
          }}
        >
          <h2>Imagens de IA</h2>
          <label>
            Provedor
            <select value={provedor} onChange={(e) => (setSalvo(false), setProvedor(e.target.value))}>
              {PROVEDORES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          {PROVEDORES.map((p) => (
            <fieldset key={p}>
              <legend>{p}</legend>
              <label>
                Modelo ({p})
                <input type="text" value={campos[p]?.modelo ?? ""} onChange={(e) => mudar(p, "modelo", e.target.value)} />
              </label>
              <label>
                Qualidade ({p})
                <input
                  type="text"
                  value={campos[p]?.qualidade ?? ""}
                  onChange={(e) => mudar(p, "qualidade", e.target.value)}
                />
              </label>
              <label>
                Preço por imagem em US$ ({p})
                <input
                  type="number"
                  min="0"
                  step="0.001"
                  value={campos[p]?.preco ?? ""}
                  onChange={(e) => mudar(p, "preco", e.target.value)}
                />
              </label>
              <p className="chave">
                {config.chaves?.[p] ? "Conectado" : `Rode python -m esteira imagens conectar ${p}`}
              </p>
            </fieldset>
          ))}
          <button type="submit" disabled={salvando}>
            Salvar
          </button>
        </form>
      ) : null}
    </main>
  );
}
