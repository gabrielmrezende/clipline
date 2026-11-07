import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import { CamposPost, ErroApi, Post, caminhoCorte, enviarJson, pedir } from "../api";

interface Props {
  ep: string;
  n: number | string;
}

const CAMPOS: { chave: keyof CamposPost; rotulo: string; limite: number; linhas: number }[] = [
  { chave: "youtube_titulo", rotulo: "Título do YouTube", limite: 100, linhas: 2 },
  { chave: "youtube_descricao", rotulo: "Descrição do YouTube", limite: 5000, linhas: 8 },
  { chave: "instagram", rotulo: "Legenda do Instagram", limite: 2200, linhas: 8 },
  { chave: "tiktok", rotulo: "Legenda do TikTok", limite: 2200, linhas: 6 },
];

const VAZIO: CamposPost = { youtube_titulo: "", youtube_descricao: "", instagram: "", tiktok: "" };
const ESPERA_MS = 400;

function mensagem(x: unknown): string {
  return x instanceof ErroApi ? x.detail : "Erro inesperado.";
}

export function EditorPost({ ep, n }: Props) {
  const caminho = `${caminhoCorte(ep, n)}/post`;
  const [carregando, setCarregando] = useState(true);
  const [post, setPost] = useState<Post | null>(null);
  const [campos, setCampos] = useState<CamposPost>(VAZIO);
  const [versao, setVersao] = useState<string | null>(null);
  const [erroLeitura, setErroLeitura] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [salvo, setSalvo] = useState(false);
  const [erroSalvar, setErroSalvar] = useState<string | null>(null);
  const [conflito, setConflito] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [copia, setCopia] = useState<string | null>(null);
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sequencia = useRef(0);

  const carregar = useCallback(async () => {
    sequencia.current += 1;
    if (temporizador.current) clearTimeout(temporizador.current);
    try {
      const dados = await pedir<Post>(caminho);
      if (dados.erro || !dados.campos) {
        setPost(null);
        setErroLeitura(dados.erro ?? "O post.md não pôde ser lido.");
        setVersao(null);
      } else {
        setPost(dados);
        setErroLeitura(null);
        setCampos(dados.campos);
        setVersao(dados.versao);
        setAvisos(dados.avisos ?? []);
      }
    } catch (x) {
      setPost(null);
      setErroLeitura(mensagem(x));
    }
    setSalvo(false);
    setErroSalvar(null);
    setConflito(false);
    setCarregando(false);
  }, [caminho]);

  useEffect(() => {
    setCarregando(true);
    void carregar();
    return () => {
      if (temporizador.current) clearTimeout(temporizador.current);
    };
  }, [carregar]);

  function agendarConferencia(novos: CamposPost) {
    if (temporizador.current) clearTimeout(temporizador.current);
    temporizador.current = setTimeout(() => {
      const minha = ++sequencia.current;
      enviarJson<{ avisos: string[] }>(`${caminho}/conferir`, "POST", { campos: novos })
        .then((r) => {
          if (minha === sequencia.current) setAvisos(r.avisos);
        })
        .catch(() => {
          /* a conferência é só uma ajuda; o salvar mostra o erro real */
        });
    }, ESPERA_MS);
  }

  function editar(chave: keyof CamposPost, e: ChangeEvent<HTMLTextAreaElement>) {
    const novos = { ...campos, [chave]: e.target.value };
    setCampos(novos);
    setSalvo(false);
    agendarConferencia(novos);
  }

  async function salvar() {
    if (versao === null) return;
    setSalvando(true);
    setSalvo(false);
    setErroSalvar(null);
    setConflito(false);
    try {
      const r = await enviarJson<{ versao: string; avisos: string[] }>(caminho, "PUT", {
        versao,
        campos,
      });
      setVersao(r.versao);
      setAvisos(r.avisos);
      setSalvo(true);
    } catch (x) {
      if (x instanceof ErroApi && x.status === 409) setConflito(true);
      else setErroSalvar(mensagem(x));
    } finally {
      setSalvando(false);
    }
  }

  async function copiarCredito() {
    try {
      await navigator.clipboard.writeText(post?.credito ?? "");
      setCopia("Crédito copiado.");
    } catch {
      setCopia("Não consegui copiar. Selecione o texto e copie à mão.");
    }
  }

  if (carregando) return <p>Carregando o post…</p>;

  const quebrado = erroLeitura !== null;
  const leitura = Object.entries(post?.somente_leitura ?? {});

  return (
    <section aria-labelledby="titulo-post" className="editor-post">
      <h2 id="titulo-post">Post</h2>
      {quebrado ? (
        <p role="alert" className="mensagem-erro">
          {erroLeitura}
        </p>
      ) : null}
      {CAMPOS.map(({ chave, rotulo, limite, linhas }) => {
        const tamanho = campos[chave].length;
        const acima = tamanho > limite;
        return (
          <div key={chave} className="campo">
            <label htmlFor={`campo-${chave}`}>{rotulo}</label>
            <textarea
              id={`campo-${chave}`}
              rows={linhas}
              value={campos[chave]}
              disabled={quebrado}
              aria-describedby={`contador-${chave}`}
              aria-invalid={acima}
              onChange={(e) => editar(chave, e)}
            />
            <span id={`contador-${chave}`} className={acima ? "contador acima" : "contador"}>
              {tamanho}/{limite}
            </span>
          </div>
        );
      })}
      <div className="avisos-post" role="status">
        {avisos.length > 0 ? (
          <>
            <h3>Avisos</h3>
            <ul>
              {avisos.map((a, i) => (
                <li key={i} className="aviso">
                  ⚠ {a}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </div>
      {leitura.length > 0 ? (
        <div className="somente-leitura">
          <h3>Só leitura</h3>
          {leitura.map(([titulo, texto]) => (
            <details key={titulo}>
              <summary>{titulo}</summary>
              <pre>{texto}</pre>
            </details>
          ))}
        </div>
      ) : null}
      {post?.credito ? (
        <div className="credito">
          <h3>Crédito</h3>
          <pre>{post.credito}</pre>
          <button type="button" onClick={copiarCredito}>
            Copiar crédito
          </button>
          <span role="status" className="suave">
            {copia}
          </span>
        </div>
      ) : null}
      <div className="acoes-post">
        <button type="button" onClick={salvar} disabled={quebrado || salvando}>
          Salvar
        </button>
        <span role="status">{salvo ? "Salvo." : ""}</span>
      </div>
      {conflito ? (
        <div role="alert" className="mensagem-erro">
          <p>O post.md mudou desde que você abriu.</p>
          <button type="button" onClick={() => void carregar()}>
            Carregar a versão nova
          </button>
        </div>
      ) : null}
      {erroSalvar ? (
        <p role="alert" className="mensagem-erro">
          {erroSalvar}
        </p>
      ) : null}
    </section>
  );
}
