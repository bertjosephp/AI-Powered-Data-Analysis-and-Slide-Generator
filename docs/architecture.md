# Architecture

## Overview

```
Browser (Next.js, apps/web)
  │  POST /jobs (file + question + outcome)   GET /jobs/{id} every 2s   GET /jobs/{id}/deck.pptx
  ▼
FastAPI (apps/api)
  ├─ ingest    loader.load_dataset         bytes → DataFrame (kept in the DatasetStore)
  ├─ profile   profiler.build_profile      DataFrame → DatasetProfile
  ├─ explore   analysis.run_battery        sample → ranked, FDR-controlled Findings (F1…)
  ├─ analyze   ClaudeAnalyst               findings + follow-up tools → Insights (+ grounding)
  └─ deck      resolve → fit → render      Insights.slides + findings → native .pptx
               ▲
               └─ Pipeline (orchestrator.py) records each stage on the job in the JobStore
```

The only external call is to Claude. Mock mode needs no API key and still produces real findings and a real deck.

## The findings engine (`services/analysis/`)

Descriptive statistics restate data; they rarely tell a decision-maker something new. The engine runs real analyses and keeps only what survives testing.

**Roles** (`roles.py`) classifies each column:
- **Outcomes:** the user's target, otherwise inferred from names (churn, returned, readmitted, margin, revenue, …) and types. Up to two are analyzed.
- **Other roles:** dimensions (up to 30 levels), measures, yes/no columns, the date column, an entity (customer, patient, …) and the main value measure.

**Analyses** (`analyses.py`) each return a `Finding`:

| Analysis | Question it answers | Test and effect size |
|---|---|---|
| `compare_segments` | Which groups differ on the outcome? | Kruskal-Wallis → ε², or χ² → rate ratio |
| `metric_by_bins` | Does the outcome change across bands of a driver? Where is the threshold? | Spearman ρ or rank-biserial r, plus the ratio between bands |
| `trend` | Is it rising? Is it seasonal? | Spearman on the period index; χ² or Kruskal-Wallis by month |
| `concentration` | How much comes from the top 10% or 20%? | Pareto shares, Gini |
| `crosstab` | Are two categories linked? | Cramér's V |
| `driver_ranking` | What moves with the outcome at all? | The above, on a common 0–1 association scale |

**Each finding carries:**
- Its statistics: the effect size and its strength, p, q and n.
- What to show: a chart spec and a templated `summary` and `headline`.
- `caveats` (small groups, sampled data, associations rather than causes) and machine-readable `facts`.

**The battery** (`battery.py`) runs a fixed plan per outcome:
- driver ranking
- segments for significant dimensions
- bands for significant measures
- trend and seasonality

It adds three dataset-wide passes:
- **Second-order explanations:** what drives the strongest drivers ("returns fall with rating" → "ratings are lowest where shipping is slowest").
- **Pareto concentration.**
- **A scan** of the remaining measures × dimensions.

**Guardrails:**
- **False discoveries:** Benjamini-Hochberg across *every* test run, including screening tests that never became findings.
- **Effect-size floor:** results must reach at least a weak effect.
- **Minimum group size.**
- **Obvious relationships** (unit price by category, seats by plan) are excluded from the scan.
- **Formula components** of the outcome (margin = revenue − cost) are excluded as drivers.
- **Duplicates:** dimensions that split rows identically (department vs diagnosis) count once, and mirror-image pairs are merged.

**Insight-recall eval** (`tests/eval/test_insight_recall.py`): the four sample datasets in `app/sample_data/` contain planted patterns listed in their manifests.
- Every primary pattern must appear among the battery's findings, in the right direction.
- Secondary and null patterns are checked with direct analyses.
- Noise columns must never be reported.

## The analyst (`services/llm/`)

- **Input:** Claude receives the profile, the ranked findings, the column roles and the user's question. It never sees rows.
- **Explore phase** (`analyst.py`): Claude may call five analysis tools (`tools.py`; not strict, since strict tools plus the report schema exceed the API's grammar limit, and bad arguments come back as error results instead) that run the same analyses on the server-side dataset, optionally on a subset (`where plan = Enterprise`). The budget is at most 8 calls over at most 4 rounds. Each call returns a new finding (F16, …) that joins the job's evidence. Follow-ups are single tests and are labelled as not FDR-adjusted.
- **Report phase:** one structured-output call (`tool_choice: none`) returns `Insights`: an executive summary answering the question, key findings, answered and open questions, hypotheses with tests, recommended actions, and slides. Every claim cites `finding_ids`.
- **Grounding** (`grounding.py`): every figure in the prose and slides is matched, within its printed precision, against typed evidence (percentages, ratios, plain numbers) from the profile and findings, including natural comparisons (group vs overall, top vs bottom). Figures it can't trace are reported on the job and shown in the UI.
- **Caching and limits:** the system prompt and the large first message carry cache breakpoints, so each exploration round re-reads them cheaply. Full assistant content, including thinking, is appended every turn.

## The deck engine (`services/deck/`)

Claude writes a typed slide spec with **references**, never figures:
- `{"metric": "finding", "finding_id": "F3"}` puts that finding's headline on a KPI card.
- `{"chart": "finding", "finding_id": "F3"}` draws that finding's chart.

The rest of the pipeline:
1. **Resolve** (`resolve.py`) looks up every reference in the findings and profile. A reference that can't be resolved degrades gracefully: the card is dropped, or the slide becomes text only.
2. **Fit** (`fit.py`) enforces the per-layout text budgets.
3. **Render** (`pptx_renderer.py`) draws a native, editable .pptx from code-defined theme tokens, with no template file:
   - Findings become native bar, column or line charts.
   - KPI values shrink to fit their card.
   - Every slide has speaker notes.

The web preview (`SlideView.tsx`) renders the same resolved slides with the renderer's geometry.

## Design decisions

- **Rows never leave the backend.** Claude only sees aggregates, from the profile, the findings and its tool results.
- **Bad files fail fast.** Parsing happens in `POST /jobs`, so invalid files get an immediate 400 or 413.
- **Jobs are resumable.**
  - Each stage saves its output on the job.
  - The dataset stays in the `DatasetStore` for the job's lifetime.
  - Retry resumes from the stage that failed. It needs the dataset only if the findings don't exist yet.
- **Deterministic statistics.** A seeded sample (at most 200k rows) is shared by the profile and the battery, so the same file always produces the same findings.

## Limits and known constraints

| Constraint | Why | Where to change it |
|---|---|---|
| Single uvicorn worker | Jobs, datasets and decks are held in memory, per process | Implement the stores on a database or object storage |
| Data kept for 1h after the job | Memory | `JOB_TTL_S` |
| 25 MB uploads | The request is buffered in memory | `MAX_UPLOAD_MB` and `NEXT_PUBLIC_MAX_UPLOAD_MB` |
| Up to 2 outcomes; ≤ 30-level dimensions | Keeps the battery fast (< 1 s on 5k rows) and the prompt small | `roles.py`, `battery.py` constants |
| Findings are associations | Observational data | Hypotheses carry suggested tests; the UI says so |
| Follow-up p-values aren't FDR-adjusted | They're chosen after seeing the data | Labelled in the UI and the prompt |
| First sheet of Excel files only | MVP scope | `loader._read_excel` |
| The deck font is referenced, not embedded | python-pptx can't embed fonts | `DECK_FONT` |

## Frontend

- **Upload:**
  - An optional question field.
  - An outcome selector, filled from the CSV header, which is parsed in the browser.
  - Example-dataset chips (`GET /samples`) that pre-fill the question and outcome.
- **Job page** (`JobView`, polling with React Query), in order:
  1. the progress tracker (5 stages)
  2. the deck card
  3. the slide preview and presenter mode
  4. the answer to the question
  5. insights with a grounding badge
  6. findings, each with a chart, strength, n and q, and linked from every citation
  7. the dataset profile
- **Contract:** zod schemas in `lib/api/types.ts` parse every response. Test fixtures are generated from the real backend by `apps/api/scripts/export_web_fixtures.py`.
