# Architecture

## Overview

```
Browser (Next.js, apps/web)
  │  POST /jobs (multipart)        GET /jobs/{id} every 2s
  ▼
FastAPI (apps/api)
  ├─ ingest    loader.load_dataset           bytes → DataFrame        (in the upload request)
  ├─ profile   profiler.build_profile        DataFrame → DatasetProfile (thread pool)
  ├─ analyze   ClaudeAnalyst.generate        DatasetProfile → Insights  (Claude, structured output)
  └─ deck      GammaClient create + poll     Insights → Presentation    (Gamma v1.0 API)
               ▲
               └─ Pipeline (orchestrator.py) records each stage on the job in the JobStore
```

The browser talks only to FastAPI. Claude and Gamma are called from the backend, and the API keys never reach the client.

## Design decisions

**Raw rows never leave the backend.** Claude receives only the `DatasetProfile`: column types, summary statistics, top category values, correlations and warnings. The upload is parsed during the request, the bytes are dropped before the request ends, and the DataFrame is dropped once the profile exists.

**Services are plain modules.** `services/ingestion`, `services/eda`, `services/llm` and `services/gamma` take typed input and return typed output, and none of them import FastAPI. `pipeline/orchestrator.py` is the only code that knows the stage order. `services/container.py` builds the object graph and picks real or mock clients.

**Bad files fail fast.** Ingest runs in `POST /jobs`, so a corrupt, empty, oversized or unsupported file gets an immediate 400 or 413 instead of becoming a failed job.

**Jobs are resumable.** Each stage saves its output on the job (`profile`, `insights`, `presentation`). `POST /jobs/{id}/retry` re-runs `Pipeline.run`, which skips any stage whose output already exists. The deck stage saves the Gamma `generationId` before it starts polling:
- If a job times out, retry resumes polling the same generation, so there's no duplicate deck and no extra credits.
- If Gamma reports the generation as `failed`, retry creates a new one.

**Retries are safe.** The Anthropic SDK retries transient errors, 3 times in our configuration. If the schema output is invalid, the analyst asks once more. Gamma polling retries on transport errors and on 429 and 5xx responses. Gamma creation retries only on connection failures and 429, because a 5xx may already have started a billable generation.

**The profile is deterministic.** Sampling uses a fixed seed, and every float is rounded and made JSON-safe: NaN and ±inf become `null`, and infinities are counted and left out of the statistics. The same file always produces the same profile.

## Mock mode

With `MOCK_EXTERNAL=true`, `MockAnalyst` builds insights from the real profile and `MockGammaClient` returns a placeholder deck URL with `mock: true`. No keys are needed and no credits are spent. The UI labels mock decks.

## Limits and known constraints

| Constraint | Why | Where to change it |
|---|---|---|
| Single uvicorn worker | `InMemoryJobStore` is per process | Implement `JobStore` on SQLite or Postgres |
| Jobs expire 1h after they finish | Memory | `JOB_TTL_S` |
| 25 MB uploads | The request is buffered in memory | `MAX_UPLOAD_MB` (backend) and `NEXT_PUBLIC_MAX_UPLOAD_MB` (web) |
| Profiles use at most 200k rows | CPU time (~4s for 200k rows) | `PROFILE_SAMPLE_ROWS` |
| First 200 columns, 15 correlation columns | Keeps the prompt small | `profiler.py` constants |
| First sheet of Excel files only | MVP scope | `loader._read_excel` |
| `exportUrl` is shown to the browser | Gamma treats it as a secret with ~1 week expiry. That's acceptable for a local single user; proxy it before any shared deployment | `DeckCard.tsx` |

## Frontend

- **Routes:** `app/page.tsx` holds the upload form. `app/jobs/[jobId]/page.tsx` renders `JobView`, which polls with React Query and stops when the job is `completed` or `failed`.
- **Contract:** `lib/api/types.ts` holds zod schemas that mirror `apps/api/app/schemas`. Every response is parsed, so contract drift fails loudly with `BAD_RESPONSE`.
- **Rendering order:** the profile appears as soon as the profile stage finishes, insights appear after analyze, and the deck card appears last.
- **Charts:** plain HTML and SVG with CSS tokens (`--viz-*` in `globals.css`) for light and dark mode.
  - The correlation heatmap uses a validated blue↔red diverging scale with a grey midpoint.
  - Every chart has a non-colour reading path: direct labels, an aria-label on every cell, and a table view.
