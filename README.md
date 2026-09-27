# AI-Powered Data Analysis & Slide Generator

Upload a CSV or Excel dataset and, optionally, ask what you want to learn ("Why are customers churning?"). The app then:

1. **Tests.** A findings engine runs real analyses on the data: segment comparisons, driver rankings, threshold bands, trends and seasonality, and Pareto concentration.
   - Every result carries an effect size and false-discovery-controlled significance.
   - Obvious relationships, formula components of the outcome and noise are filtered out.
2. **Explains.** Claude reads the ranked findings, never your rows. It digs deeper with up to 8 follow-up analyses on the server-side data, then answers your question, citing the findings behind every claim.
   - A grounding check verifies that every figure in the text traces back to the analysis.
3. **Presents.** The story becomes a native, editable PowerPoint deck with real charts, and every figure on a slide is computed from your data.
   - The dashboard also shows the deck in the browser, with a full-screen presenter mode.

**Example datasets.** Four are included: e-commerce orders, SaaS churn, HR attrition and hospital readmissions. Each has known patterns planted in it, and an eval checks that the engine finds every one without flagging the noise columns.

The dashboard shows progress for each step and displays results as soon as each step finishes.

## Layout

```
apps/api   FastAPI backend: ingestion, profiling, findings engine (SciPy), Claude analyst with tools,
           deck engine (python-pptx), job pipeline; sample datasets in app/sample_data
apps/web   Next.js 16 frontend: App Router, TypeScript, Tailwind v4, React Query, zod
docs/      architecture.md, api-contract.md
```

## Requirements

- Python 3.12
- Node 22+ with pnpm 9
- An [Anthropic API key](https://console.anthropic.com), unless you use mock mode. No other services or subscriptions are needed.

## Quick start

```bash
cp .env.example .env     # add ANTHROPIC_API_KEY, or set MOCK_EXTERNAL=true
make install             # backend venv at apps/api/.venv, and pnpm install for the web app
make dev                 # API on :8000 (OpenAPI docs at /docs), web on :3000
```

Open <http://localhost:3000> and click one of the example datasets. It fills in a suggested question and outcome.

**Mock mode** (`MOCK_EXTERNAL=true`) replaces Claude with a deterministic analyst that builds the story from the real findings. The findings and the deck are still computed for real, with no API key and no cost.

**Cost with Claude:** a run is a handful of calls (exploration rounds plus one report) with prompt caching, typically a few cents with the default `claude-sonnet-5`.

The web app reads `NEXT_PUBLIC_API_BASE_URL`, which defaults to `http://localhost:8000/api/v1`. To point it elsewhere in development, set the variable in `apps/web/.env.local`.

### Docker

```bash
cp .env.example .env && docker compose up --build
```

## Development

| Command | What it does |
|---|---|
| `make test` | Backend pytest (including the insight-recall eval) and web vitest |
| `make e2e` | Playwright end to end against the real API in mock mode. It uses your installed Chrome; stop `make dev` first |
| `make lint` | ruff and mypy (strict) for the backend, eslint for the web app |
| `cd apps/web && pnpm typecheck` | Next route types and tsc |
| `apps/api/.venv/bin/python apps/api/scripts/smoke_llm.py app/sample_data/saas_churn.csv --question "Why do customers churn?" --target churned` | Real Claude run: findings, follow-ups, grounding report, and `deck.pptx` |
| `apps/api/.venv/bin/python apps/api/scripts/generate_datasets.py` | Regenerate the sample datasets and their planted-pattern manifests (deterministic) |
| `apps/api/.venv/bin/python apps/api/scripts/export_web_fixtures.py` | Regenerate the web contract fixtures after a schema change |

Run the scripts from `apps/api`.

## Configuration

All settings live in `.env`; `.env.example` lists every one. The ones you're most likely to change:

| Variable | Default | Notes |
|---|---|---|
| `LLM_MODEL` | `claude-sonnet-5` | Any Claude model that supports structured outputs |
| `DECK_FONT` | `Aptos` | Font used in the .pptx. Aptos ships with current Office; other viewers substitute a font |
| `MAX_UPLOAD_MB` | `25` | Keep it in sync with `NEXT_PUBLIC_MAX_UPLOAD_MB` for the web app |
| `JOB_TTL_S` | `3600` | Jobs are kept in memory, so run a single API worker |

See [docs/architecture.md](docs/architecture.md) for the design and its limits, and [docs/api-contract.md](docs/api-contract.md) for the HTTP API.
