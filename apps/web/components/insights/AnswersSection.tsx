import { MessageSquareText } from "lucide-react";

import { FindingChips } from "@/components/findings/FindingChip";
import { SectionHeader } from "@/components/ui/SectionHeader";
import type { Insights } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const CONFIDENCE = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

type Props = {
  answers: Insights["questions_answered"];
  userQuestion?: string | null;
  titles: Map<string, string>;
};

export function AnswersSection({ answers, userQuestion, titles }: Props) {
  if (answers.length === 0) return null;
  return (
    <section aria-labelledby="answers-heading">
      <SectionHeader
        id="answers-heading"
        eyebrow="Answer"
        title={userQuestion ? "Your question, answered" : "Questions answered"}
        description="Each answer cites the tested findings it rests on."
      />
      <ol className="space-y-3">
        {answers.map((a, i) => {
          const lead = i === 0 && Boolean(userQuestion);
          return (
            <li
              key={a.question}
              className={cn(
                "rounded-2xl border p-5 shadow-card",
                lead
                  ? "border-accent/25 bg-gradient-to-br from-accent-soft to-surface p-6"
                  : "border-border bg-surface",
              )}
            >
              <p className={cn("flex items-start gap-2 font-medium", lead && "text-accent")}>
                {lead && <MessageSquareText className="mt-0.5 size-4 shrink-0" aria-hidden />}
                {a.question}
              </p>
              <p className={cn("mt-2 leading-relaxed", lead && "text-lg")}>{a.answer}</p>
              <p className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
                <span>{CONFIDENCE[a.confidence]}</span>
                <FindingChips ids={a.finding_ids} titles={titles} />
              </p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
