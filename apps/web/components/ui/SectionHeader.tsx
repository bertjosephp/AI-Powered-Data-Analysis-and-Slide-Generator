type Props = {
  id: string;
  eyebrow: string;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
};

/** Consistent header for the top-level sections of the job page. */
export function SectionHeader({ id, eyebrow, title, description, action }: Props) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <p className="text-xs font-semibold tracking-wider text-accent uppercase">{eyebrow}</p>
        <h2 id={id} className="mt-1 text-xl font-semibold tracking-tight">
          {title}
        </h2>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}
