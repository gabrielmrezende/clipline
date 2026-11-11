import { Component, ReactNode } from "react";

interface Estado {
  erro: Error | null;
}

/** Um erro de JavaScript numa tela vira uma mensagem com botão de recarregar, e não uma página em branco. */
export class ErroDaTela extends Component<{ children: ReactNode }, Estado> {
  state: Estado = { erro: null };

  static getDerivedStateFromError(erro: Error): Estado {
    return { erro };
  }

  render() {
    if (!this.state.erro) return this.props.children;
    return (
      <main className="coluna">
        <h1>Algo deu errado nesta tela</h1>
        <p role="alert" className="mensagem-erro">
          {this.state.erro.message || "Erro inesperado."}
        </p>
        <p>
          <button type="button" className="primario" onClick={() => location.reload()}>
            Recarregar
          </button>{" "}
          <a href="/">Voltar aos episódios</a>
        </p>
      </main>
    );
  }
}
