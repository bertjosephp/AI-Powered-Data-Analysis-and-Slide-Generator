# Architecture

## Overview

```
Browser (Next.js, apps/web)
  │  POST /jobs (multipart)   GET /jobs/{id} every 2s   GET /jobs/{id}/deck.pptx
  ▼
FastAPI (apps/api)
  ├─ ingest    loader.load_dataset        bytes → DataFrame           (in the upload request)
  ├─ profile   profiler.build_profile     DataFrame → DatasetProfile  (thread pool)
  ├─ analyze   ClaudeAnalyst.generate     DatasetProfile → Insights   (Claude, structured output)
  └─ deck      resolve → fit → render     Insights.slides → .pptx     (local, thread pool)
               ▲
               └─ Pipeline (orchestrator.py) records each stage on the job in the JobStore
```

The only external call is to Claude. Everything else, including the slide deck, runs locally and deterministically. There are no subscriptions, and mock mode needs no API key at all.

## The deck engine

The deck goes through three steps: Claude writes a slide *spec*, the backend *resolves* it against the profile, and the renderers *draw* it.

1. **Spec** (`schemas/deck.py`, `SlideSpec`). Claude chooses one of six layouts per slide and writes the prose: `title`, `executive_summary`, `kpi_cards`, `chart_insight`, `hypotheses` or `next_steps`.
   - It never writes a figure. It writes **references**, for example `{"metric": "median", "column": "revenue"}` or `{"chart": "top_values", "column": "region"}`.
   - The spec is a discriminated union sent as a structured-output schema. Each layout name is pinned with a one-item `enum`, because the SDK turns `const` into plain description text and the API wouldn't enforce it.
2. **Resolve** (`services/deck/resolve.py`). Every reference is looked up in the `DatasetProfile`, so the figures come from Pandas.
   - A reference Claude got wrong (an unknown column, or a metric that doesn't fit the column type) degrades instead of failing: the KPI card is dropped, or the chart slide becomes text only.
3. **Fit** (`services/deck/fit.py`). Text budgets per layout are enforced by trimming on a word boundary. Structured outputs can't enforce `maxLength`: the SDK validates it on the client and would reject the whole answer. So the prompt states the budgets and this step guarantees them.
4. **Render.**
   - `services/deck/pptx_renderer.py` draws a native, editable .pptx from scratch, with no template file. Layouts are placed on a 16:9 grid from the `Theme` tokens in `theme.py`. Charts are real PowerPoint charts with their data embedded, and every slide has speaker notes.
   - `apps/web/components/presentation/SlideView.tsx` renders the *same* resolved slides in the browser using the renderer's geometry, converted to container-query units. The thumbnails and presenter mode therefore match the file.

**Tests for the deck engine:**
- The resolver's numbers equal the profile's values.
- The renderer's output reopens with python-pptx, and its chart data equals the profile's values.
- A worst-case deck, with every field at its text budget, is checked so that no shape leaves the slide and every text box fits its estimated line count.

## Design decisions

**Raw rows never leave the backend.** Claude only receives the `DatasetProfile`. The upload is parsed during the request, the bytes are dropped before it ends, and the DataFrame is dropped once the profile exists.

**Services are plain modules.** `services/ingestion`, `services/eda`, `services/llm` and `services/deck` take typed input and return typed output, and none of them import FastAPI. `pipeline/orchestrator.py` is the only code that knows the stage order, and `services/container.py` builds the object graph.

**Bad files fail fast.** Ingest runs in `POST /jobs`, so a corrupt, empty, oversized or unsupported file gets an immediate 400 or 413 instead of becoming a failed job.

**Jobs are resumable.** Each stage saves its output on the job (`profile`, `insights`, `deck` and `presentation`). `POST /jobs/{id}/retry` re-runs the pipeline and skips any stage whose output already exists. Rendering is local and idempotent, so a failed deck stage just renders again without calling Claude a second time.

**Retries are safe.** The Anthropic SDK retries transient errors, 3 times in our configuration. If the structured output is invalid, the analyst asks once more.

**The profile is deterministic.** Sampling uses a fixed seed, and every float is rounded and made JSON-safe: NaN and ±inf become `null`, and infinities are counted and left out of the statistics.

## Mock mode

`MOCK_EXTERNAL=true` swaps Claude for `MockAnalyst`. It builds a deterministic spec from the real profile that uses every layout. The deck is still rendered for real, so the demo produces a genuine .pptx without an API key.

## Limits and known constraints

| Constraint | Why | Where to change it |
|---|---|---|
| Single uvicorn worker | Jobs and deck files are held in memory, per process | Implement `JobStore` and `ArtifactStore` on a database or object storage |
| Jobs and decks expire 1h after they finish | Memory | `JOB_TTL_S` |
| 25 MB uploads | The request is buffered in memory | `MAX_UPLOAD_MB` (backend) and `NEXT_PUBLIC_MAX_UPLOAD_MB` (web) |
| Profiles use at most 200k rows | CPU time (~4s for 200k rows) | `PROFILE_SAMPLE_ROWS` |
| First 200 columns, 15 correlation columns | Keeps the prompt small | `profiler.py` constants |
| First sheet of Excel files only | MVP scope | `loader._read_excel` |
| The deck font is referenced, not embedded | python-pptx can't embed fonts. Aptos ships with current Office, and other viewers substitute a font | `DECK_FONT` |
| The preview is a faithful rendering of the same spec, not the .pptx | Pixel-exact thumbnails would need LibreOffice on the server | `SlideView.tsx` |

## Frontend

- **Routes:** `app/page.tsx` holds the upload form. `app/jobs/[jobId]/page.tsx` renders `JobView`, which polls with React Query and stops when the job is `completed` or `failed`.
- **Contract:** `lib/api/types.ts` holds zod schemas that mirror `apps/api/app/schemas`. Every response is parsed, so contract drift fails loudly with `BAD_RESPONSE`. The test fixtures are generated from the backend models by `apps/api/scripts/export_web_fixtures.py`.
- **Rendering order:** the profile appears as soon as the profile stage finishes, insights appear after analyze, and the deck card and slide preview appear last. Presenter mode supports arrow keys and Esc, and returns focus to where it was.
- **Dashboard charts:** plain HTML and SVG with CSS tokens (`--viz-*` in `globals.css`) for light and dark mode.
  - The correlation heatmap uses a validated blue↔red diverging scale with a grey midpoint.
  - Every chart has a non-colour reading path: direct labels, an aria-label on every cell, and a table view.
