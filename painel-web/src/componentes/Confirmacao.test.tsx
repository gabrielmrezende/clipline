import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { vi } from "vitest";
import {
  botaoConfirmarDoDialogo,
  dialogoAberto,
  haDialogo,
  responderDialogo,
  tituloDoDialogo,
} from "../testes/dialogo";
import { OpcoesConfirmacao, ProvedorConfirmacao, useConfirmar } from "./Confirmacao";

/** Um botão que pede a confirmação e mostra a resposta. */
function Pede({ opcoes, rotulo = "Pedir" }: { opcoes: OpcoesConfirmacao; rotulo?: string }) {
  const confirmar = useConfirmar();
  const [resposta, setResposta] = useState("nada");
  const [erro, setErro] = useState("");
  return (
    <>
      <button
        type="button"
        onClick={() =>
          confirmar(opcoes)
            .then((sim) => setResposta(String(sim)))
            .catch((x: Error) => setErro(x.message))
        }
      >
        {rotulo}
      </button>
      <output aria-label={`resposta ${rotulo}`}>{resposta}</output>
      {erro ? <p role="alert">{erro}</p> : null}
    </>
  );
}

const CUSTO: OpcoesConfirmacao = {
  titulo: "Gerar 2 imagens com openai (gpt-image-1), ~US$ 0,10?",
  custo: "~US$ 0,10",
  confirmar: "Gerar",
};

async function esperar() {
  await act(async () => {
    await Promise.resolve();
  });
}

function abrir(rotulo = "Pedir") {
  fireEvent.click(screen.getByRole("button", { name: rotulo }));
}

const resposta = (rotulo = "Pedir") => screen.getByLabelText(`resposta ${rotulo}`).textContent;

describe("Confirmacao", () => {
  it("mostra título, resumo, aviso e itens, e liga título e descrição ao diálogo", () => {
    render(
      <ProvedorConfirmacao>
        <Pede
          opcoes={{
            titulo: "Baixar 2 fotos (1,5 MB) de Wikimedia Commons?",
            resumo: "As fotos baixadas antes neste corte serão substituídas.",
            aviso: "As imagens mudaram desde a última montagem.",
            itens: ["tamanho desconhecido: f1-2.jpg"],
            confirmar: "Baixar",
          }}
        />
      </ProvedorConfirmacao>,
    );
    expect(haDialogo()).toBe(false);
    abrir();
    const d = dialogoAberto();
    expect(d.tagName).toBe("DIALOG");
    expect(d.getAttribute("aria-modal")).toBe("true");
    expect(tituloDoDialogo()).toBe("Baixar 2 fotos (1,5 MB) de Wikimedia Commons?");
    const descricao = d.getAttribute("aria-describedby")!.split(" ").map((id) => document.getElementById(id)!.textContent);
    expect(descricao.join(" ")).toContain("As fotos baixadas antes neste corte serão substituídas.");
    expect(descricao.join(" ")).toContain("As imagens mudaram desde a última montagem.");
    expect(within(d).getByRole("listitem").textContent).toBe("tamanho desconhecido: f1-2.jpg");
    expect(botaoConfirmarDoDialogo().textContent).toBe("Baixar");
    expect(botaoConfirmarDoDialogo().className).toContain("tom-normal");
  });

  it("confirmar responde true e fecha; o foco volta ao botão de origem", async () => {
    render(
      <ProvedorConfirmacao>
        <Pede opcoes={{ titulo: "Aprovar este corte?", confirmar: "Aprovar" }} />
      </ProvedorConfirmacao>,
    );
    const origem = screen.getByRole("button", { name: "Pedir" });
    origem.focus();
    abrir();
    // Ação comum: o foco começa no botão de confirmar.
    expect(document.activeElement).toBe(botaoConfirmarDoDialogo());
    responderDialogo(true);
    await esperar();
    expect(resposta()).toBe("true");
    expect(haDialogo()).toBe(false);
    expect(document.activeElement).toBe(origem);
  });

  it("com custo: destaque do preço, botão âmbar com o preço e o foco começa em Cancelar", async () => {
    render(
      <ProvedorConfirmacao>
        <Pede opcoes={CUSTO} />
      </ProvedorConfirmacao>,
    );
    abrir();
    const d = dialogoAberto();
    expect(within(d).getByText("Custo estimado")).toBeTruthy();
    expect(botaoConfirmarDoDialogo().textContent).toBe("Gerar por ~US$ 0,10");
    expect(botaoConfirmarDoDialogo().className).toContain("tom-custo");
    expect(document.activeElement).toBe(within(d).getByRole("button", { name: "Cancelar" }));
    const descricao = d.getAttribute("aria-describedby")!;
    expect(document.getElementById(descricao)!.textContent).toContain("~US$ 0,10");
    responderDialogo(false);
    await esperar();
    expect(resposta()).toBe("false");
  });

  it("irreversível: botão vermelho, foco em Cancelar", () => {
    render(
      <ProvedorConfirmacao>
        <Pede opcoes={{ titulo: "Descartar o que você escreveu?", confirmar: "Descartar", tom: "irreversivel" }} />
      </ProvedorConfirmacao>,
    );
    abrir();
    expect(botaoConfirmarDoDialogo().className).toContain("tom-irreversivel");
    expect(document.activeElement?.textContent).toBe("Cancelar");
  });

  it("Esc e clique fora cancelam", async () => {
    render(
      <ProvedorConfirmacao>
        <Pede opcoes={CUSTO} />
      </ProvedorConfirmacao>,
    );
    abrir();
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    await esperar();
    expect(resposta()).toBe("false");
    expect(haDialogo()).toBe(false);
    abrir();
    fireEvent.click(dialogoAberto());
    await esperar();
    expect(haDialogo()).toBe(false);
  });

  it("o Tab fica preso dentro do diálogo", () => {
    render(
      <ProvedorConfirmacao>
        <Pede opcoes={{ titulo: "Montar?", confirmar: "Montar" }} />
      </ProvedorConfirmacao>,
    );
    abrir();
    const cancelar = within(dialogoAberto()).getByRole("button", { name: "Cancelar" });
    const confirmar = botaoConfirmarDoDialogo();
    expect(document.activeElement).toBe(confirmar);
    fireEvent.keyDown(confirmar, { key: "Tab" });
    expect(document.activeElement).toBe(cancelar);
    fireEvent.keyDown(cancelar, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(confirmar);
  });

  it("duas confirmações pedidas juntas aparecem uma de cada vez, na ordem", async () => {
    render(
      <ProvedorConfirmacao>
        <Pede rotulo="A" opcoes={{ titulo: "Primeira?" }} />
        <Pede rotulo="B" opcoes={{ titulo: "Segunda?" }} />
      </ProvedorConfirmacao>,
    );
    abrir("A");
    fireEvent.click(screen.getByRole("button", { name: "B" }));
    expect(screen.getAllByRole("alertdialog")).toHaveLength(1);
    expect(tituloDoDialogo()).toBe("Primeira?");
    responderDialogo(true);
    await esperar();
    expect(tituloDoDialogo()).toBe("Segunda?");
    responderDialogo(false);
    await esperar();
    expect(resposta("A")).toBe("true");
    expect(resposta("B")).toBe("false");
  });

  it("clique duplo em confirmar responde uma vez só", async () => {
    render(
      <ProvedorConfirmacao>
        <Pede rotulo="A" opcoes={{ titulo: "Primeira?" }} />
        <Pede rotulo="B" opcoes={{ titulo: "Segunda?" }} />
      </ProvedorConfirmacao>,
    );
    abrir("A");
    fireEvent.click(screen.getByRole("button", { name: "B" }));
    const botao = botaoConfirmarDoDialogo();
    fireEvent.click(botao);
    fireEvent.click(botao);
    await esperar();
    expect(resposta("A")).toBe("true");
    expect(resposta("B")).toBe("nada");
    expect(tituloDoDialogo()).toBe("Segunda?");
  });

  it("sem o provedor, confirmar() falha com uma mensagem clara (nada é confirmado por engano)", async () => {
    const espiao = vi.spyOn(window, "confirm");
    render(<Pede opcoes={CUSTO} />);
    abrir();
    await esperar();
    expect(screen.getByRole("alert").textContent).toContain("ProvedorConfirmacao");
    expect(resposta()).toBe("nada");
    expect(espiao).not.toHaveBeenCalled();
  });
});
