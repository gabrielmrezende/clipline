import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import { CamposPost, ErroApi, Post, caminhoCorte, enviarJson, pedir } from "../api";

interface Props {
  ep: string;
  n: number | string;
  /** Muda quando algo de fora (a troca de música) alterou o post.md. */
  recarregarSinal: number;
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

export function EditorPost({ ep, n, recarregarSinal }: Props) {
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
  const [disco, setDisco] = useState<Post | null>(null);
  const [erroDisco, setErroDisco] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [copia, setCopia] = useState<string | null>(null);
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sequencia = useRef(0);
  const camposRef = useRef<CamposPost>(VAZIO);
  const carregadosRef = useRef<CamposPost>(VAZIO);
  const sinalAnterior = useRef(recarregarSinal);
  const [creditoMudou, setCreditoMudou] = useState(false);
  camposRef.current = campos;

  const limparConflito = useCallback(() => {
    setConflito(false);
    setDisco(null);
    setErroDisco(null);
  }, []);

  /** Põe nos campos um post lido do disco e esquece conferências pendentes. */
  const aplicar = useCallback((dados: Post & { campos: CamposPost }) => {
    sequencia.current += 1;
    if (temporizador.current) clearTimeout(temporizador.current);
    setPost(dados);
    setErroLeitura(null);
    carregadosRef.current = dados.campos;
    setCreditoMudou(false);
    setCampos(dados.campos);
    setVersao(dados.versao);
    setAvisos(dados.avisos ?? []);
  }, []);

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
        aplicar({ ...dados, campos: dados.campos });
      }
    } catch (x) {
      setPost(null);
      setErroLeitura(mensagem(x));
    }
    setSalvo(false);
    setErroSalvar(null);
    limparConflito();
    setCarregando(false);
  }, [caminho, aplicar, limparConflito]);

  useEffect(() => {
    setCarregando(true);
    void carregar();
    return () => {
      if (temporizador.current) clearTimeout(temporizador.current);
    };
  }, [carregar]);

  useEffect(() => {
    if (sinalAnterior.current === recarregarSinal) return;
    sinalAnterior.current = recarregarSinal;
    const sujo = CAMPOS.some(({ chave }) => camposRef.current[chave] !== carregadosRef.current[chave]);
    if (sujo) setCreditoMudou(true);
    else void carregar();
  }, [recarregarSinal, carregar]);

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

  /** Depois de um 409: lê o post de novo só para mostrar o disco; o rascunho fica nos campos. */
  async function lerDisco() {
    setConflito(true);
    setDisco(null);
    setErroDisco(null);
    try {
      const dados = await pedir<Post>(caminho);
      if (dados.erro || !dados.campos || dados.versao === null) {
        setErroDisco(dados.erro ?? "O post.md não pôde ser lido.");
      } else {
        setDisco(dados);
      }
    } catch (x) {
      setErroDisco(mensagem(x));
    }
  }

  async function salvar(versaoEnviada: string | null) {
    if (versaoEnviada === null) return;
    setSalvando(true);
    setSalvo(false);
    setErroSalvar(null);
    try {
      const r = await enviarJson<{ versao: string; avisos: string[] }>(caminho, "PUT", {
        versao: versaoEnviada,
        campos,
      });
      setVersao(r.versao);
      setAvisos(r.avisos);
      carregadosRef.current = campos;
      setCreditoMudou(false);
      setSalvo(true);
      limparConflito();
    } catch (x) {
      if (x instanceof ErroApi && x.status === 409) await lerDisco();
      else setErroSalvar(mensagem(x));
    } finally {
      setSalvando(false);
    }
  }

  function usarArquivo() {
    if (!disco?.campos) return;
    if (!window.confirm("Descartar o que você escreveu e usar a versão do arquivo?")) return;
    aplicar({ ...disco, campos: disco.campos });
    setSalvo(false);
    setErroSalvar(null);
    limparConflito();
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
      {creditoMudou ? (
        <p role="status" className="aviso">
          O crédito da música mudou no post.md
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
            {disco?.campos && disco.campos[chave] !== campos[chave] ? (
              <div className="no-arquivo">
                <span>No arquivo agora:</span>
                <pre>{disco.campos[chave]}</pre>
              </div>
            ) : null}
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
        <button type="button" onClick={() => void salvar(versao)} disabled={quebrado || salvando}>
          Salvar
        </button>
        <span role="status">{salvo ? "Salvo." : ""}</span>
      </div>
      {conflito ? (
        <div role="alert" className="mensagem-erro conflito">
          <p>O post.md mudou desde que você abriu.</p>
          {erroDisco ? <p>{erroDisco}</p> : null}
          {disco ? (
            <div className="acoes-conflito">
              <button type="button" onClick={usarArquivo} disabled={salvando}>
                Usar a versão do arquivo
              </button>
              <button type="button" onClick={() => void salvar(disco.versao)} disabled={salvando}>
                Salvar o meu por cima
              </button>
            </div>
          ) : null}
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
