import type { ItemCalendario } from "../api";

function hora(data: string): string {
  return data.slice(11, 16);
}

/** "2026-11-08" vira "8 de nov." e "domingo"; uma data ilegível fica como veio. */
function rotuloDoDia(dia: string): { data: string; semana: string } {
  const d = new Date(`${dia}T12:00:00`);
  if (Number.isNaN(d.getTime())) return { data: dia, semana: "" };
  return {
    data: new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "short" }).format(d),
    semana: new Intl.DateTimeFormat("pt-BR", { weekday: "long" }).format(d),
  };
}

function Linha({ rotulo, id, itens }: { rotulo: string; id: string; itens: ItemCalendario[] }) {
  return (
    <div className="cal-linha">
      <h4>{rotulo}</h4>
      <ul data-testid={id}>
        {itens.map((i) => (
          <li key={i.numero}>
            {i.data ? <span className="cal-hora">{hora(i.data)}</span> : null}{" "}
            <strong className="cal-num">{i.numero}</strong> {i.titulo}
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
        const { data, semana } = rotuloDoDia(dia);
        return (
          <section key={dia} className="cal-dia" aria-label={dia}>
            <h3 className="cal-data">
              <span className="cal-data-dia">{data}</span>
              {semana ? <span className="cal-semana">{semana}</span> : null}
            </h3>
            <div className="cal-linhas">
              <Linha rotulo="TikTok e Shorts" id="linha-tiktok" itens={doDia} />
              <Linha
                rotulo="Instagram"
                id="linha-instagram"
                itens={doDia.filter((i) => i.redes.includes("instagram"))}
              />
            </div>
          </section>
        );
      })}
      {semData.length > 0 ? (
        <section className="cal-dia" aria-label="Sem data">
          <h3 className="cal-data">
            <span className="cal-data-dia">Sem data</span>
          </h3>
          <ul>
            {semData.map((i) => (
              <li key={i.numero}>
                <strong className="cal-num">{i.numero}</strong> {i.titulo}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
