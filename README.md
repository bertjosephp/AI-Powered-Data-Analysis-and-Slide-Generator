# AI-Powered Data Analysis & Slide Generator

Upload a CSV or Excel dataset. The app then:

1. runs deterministic exploratory data analysis (EDA) with Pandas,
2. has Claude turn the statistical profile (never the raw rows) into hypotheses, analytical questions and an executive summary, and
3. sends that narrative to Gamma to build a slide deck.

## Layout

```
apps/api   FastAPI backend (ingestion, EDA, LLM, Gamma, job pipeline)
apps/web   Next.js frontend (App Router, TypeScript, Tailwind)
docs/      Architecture and API contract
```

## Quick start

```bash
cp .env.example .env        # fill in ANTHROPIC_API_KEY and GAMMA_API_KEY
make install
make dev                    # API on :8000, web on :3000
```

Set `MOCK_EXTERNAL=true` to run the whole pipeline offline with fixture LLM and Gamma responses.

Run `make help` to see all targets.
