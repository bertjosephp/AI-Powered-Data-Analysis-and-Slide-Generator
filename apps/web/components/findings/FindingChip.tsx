/** A citation of a finding (F3), linking to its card in the Findings section. */
export function FindingChip({ id, title }: { id: string; title?: string }) {
  return (
    <a
      href={`#finding-${id}`}
      title={title ? `${id}: ${title}` : `See finding ${id}`}
      className="inline-flex items-center rounded-md bg-accent-soft px-1.5 py-0.5 font-mono text-xs font-medium text-accent hover:underline"
    >
      {id}
    </a>
  );
}

export function FindingChips({
  ids,
  titles,
}: {
  ids: string[];
  titles?: Map<string, string>;
}) {
  if (ids.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap gap-1" aria-label="Evidence">
      {ids.map((id) => (
        <FindingChip key={id} id={id} title={titles?.get(id)} />
      ))}
    </span>
  );
}
