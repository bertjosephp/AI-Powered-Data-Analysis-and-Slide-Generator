# AI-Powered Data Analysis & Slide Generator

Upload a CSV or Excel dataset. The app then:

1. **Profiles** the file with Pandas: column types, missing values, descriptive statistics and correlations.
2. **Analyzes** the profile with Claude. Claude sees statistics, never your rows, and writes findings, hypotheses, analytical questions and an executive summary.
3. **Presents** the story as a native, editable PowerPoint deck with real charts. Every figure on a slide is computed from your data, never written by the model. The dashboard also shows the deck in the browser, with a full-screen presenter mode.

The dashboard shows progress for each step and displays results as soon as each step finishes.

## Layout

```
apps/api   FastAPI backend: ingestion, EDA, Claude analyst, deck engine (python-pptx), job pipeline
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

Open <http://localhost:3000> and upload `apps/api/tests/fixtures/sample.csv` to try it.

**Mock mode** (`MOCK_EXTERNAL=true`) replaces Claude with a deterministic analyst that works from the real profile. The deck is still rendered for real, so you get a genuine .pptx with no API key and no cost.

The web app reads `NEXT_PUBLIC_API_BASE_URL`, which defaults to `http://localhost:8000/api/v1`. To point it elsewhere in development, set the variable in `apps/web/.env.local`.

### Docker

```bash
cp .env.example .env && docker compose up --build
```

## Development

| Command | What it does |
|---|---|
| `make test` | Backend pytest and web vitest |
| `make e2e` | Playwright end to end against the real API in mock mode. It uses your installed Chrome; stop `make dev` first |
| `make lint` | ruff and mypy (strict) for the backend, eslint for the web app |
| `cd apps/web && pnpm typecheck` | Next route types and tsc |
| `apps/api/.venv/bin/python apps/api/scripts/smoke_llm.py` | Real Claude call on the sample file; writes `deck.pptx` |
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
