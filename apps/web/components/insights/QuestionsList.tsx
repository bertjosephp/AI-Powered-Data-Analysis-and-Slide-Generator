import { Card } from "@/components/ui/Card";
import type { Insights } from "@/lib/api/types";

export function QuestionsList({ questions }: { questions: Insights["open_questions"] }) {
  return (
    <Card title="Questions worth asking" description="What this data raises but can't answer alone">
      <ol className="space-y-3">
        {questions.map((q, i) => (
          <li key={q.question} className="flex gap-3">
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-surface-muted text-xs text-muted">
              {i + 1}
            </span>
            <div>
              <p className="font-medium">{q.question}</p>
              <p className="text-sm text-muted">{q.why_it_matters}</p>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export function NotesList({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  if (items.length === 0) return null;
  return (
    <Card title={title}>
      <ul className="list-disc space-y-1.5 pl-5 text-sm">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </Card>
  );
}
