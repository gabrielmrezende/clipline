// Só o que os testes usam do Node: o painel não depende de @types/node.
declare module "node:fs" {
  export function readFileSync(caminho: URL, codificacao: "utf-8"): string;
}
