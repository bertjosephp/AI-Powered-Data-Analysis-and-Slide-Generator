import { BarChart3, Presentation, Sparkles } from "lucide-react";

import { UploadForm } from "@/components/upload/UploadForm";

const STEPS = [
  {
    icon: BarChart3,
    title: "Profile",
    body: "Types, missing values, distributions and correlations are computed from your data with Pandas.",
  },
  {
    icon: Sparkles,
    title: "Analyze",
    body: "Claude reads the statistical profile, not your rows, and drafts findings, hypotheses and questions.",
  },
  {
    icon: Presentation,
    title: "Present",
    body: "Gamma turns the narrative into a slide deck you can open, share or download.",
  },
];

export default function HomePage() {
  return (
    <div className="mx-auto max-w-2xl">
      <section className="text-center">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Turn a spreadsheet into a slide deck
        </h1>
        <p className="mt-3 text-muted">
          Upload a dataset and get a statistical profile, AI-written findings, and a presentation.
        </p>
      </section>

      <div className="mt-8">
        <UploadForm />
      </div>

      <ol className="mt-10 grid gap-4 sm:grid-cols-3">
        {STEPS.map(({ icon: Icon, title, body }, i) => (
          <li key={title} className="rounded-xl border border-border bg-surface p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Icon className="size-4 text-accent" aria-hidden />
              {i + 1}. {title}
            </div>
            <p className="mt-2 text-sm text-muted">{body}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
