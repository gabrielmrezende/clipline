import type { ItemCalendario } from "../api";

function hora(data: string): string {
  return data.slice(11, 16);
}

function Linha({ rotulo, id, itens }: { rotulo: string; id: string; itens: ItemCalendario[] }) {
  return (
    <div className="cal-linha">
      <h4>{rotulo}</h4>
      <ul data-testid={id}>
        {itens.map((i) => (
          <li key={i.numero}>
            {i.data ? <span className="cal-hora">{hora(i.data)}</span> : null}{" "}
            <strong>{i.numero}</strong> {i.titulo}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Calendario({ itens }: { itens: ItemCalendario[] }) {
  const dias = new Map<string, ItemCalendario[]>();
  const semData: ItemCalendario[] = [];
  for (const item of itens) {
    if (!item.data) {
      semData.push(item);
      continue;
    }
    const dia = item.data.slice(0, 10);
    dias.set(dia, [...(dias.get(dia) ?? []), item]);
  }
  const ordenados = [...dias.keys()].sort();
  const porHora = (a: ItemCalendario, b: ItemCalendario) => a.data.localeCompare(b.data);

  if (itens.length === 0) return <p>Nenhum corte neste episódio.</p>;

  return (
    <div className="calendario">
      {ordenados.map((dia) => {
        const doDia = [...(dias.get(dia) ?? [])].sort(porHora);
        return (
          <section key={dia} className="cal-dia" aria-label={dia}>
            <h3>{dia}</h3>
            <Linha rotulo="TikTok e Shorts" id="linha-tiktok" itens={doDia} />
            <Linha
              rotulo="Instagram"
              id="linha-instagram"
              itens={doDia.filter((i) => i.redes.includes("instagram"))}
            />
          </section>
        );
      })}
      {semData.length > 0 ? (
        <section className="cal-dia" aria-label="Sem data">
          <h3>Sem data</h3>
          <ul>
            {semData.map((i) => (
              <li key={i.numero}>
                <strong>{i.numero}</strong> {i.titulo}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
