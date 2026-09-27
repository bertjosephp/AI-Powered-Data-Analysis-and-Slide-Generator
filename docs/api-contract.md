# API contract

- **Base URL:** `/api/v1`. All requests and responses are JSON (snake_case) except the upload.
- **Source of truth:** the Pydantic models in `apps/api/app/schemas/`, served as OpenAPI at `/docs`.
- **Mirror:** `apps/web/lib/api/types.ts` has matching zod schemas. When a schema changes, run `apps/api/scripts/export_web_fixtures.py` to regenerate the web fixtures, and the web contract tests will catch any drift.

## Endpoints

| Method | Path | Success | Purpose |
|---|---|---|---|
| GET | `/health` | 200 | Liveness, plus whether keys are configured and mock mode is on |
| POST | `/jobs` | 202 `JobCreated` | Upload a dataset and start the pipeline |
| GET | `/jobs/{job_id}` | 200 `JobState` | Poll progress and results |
| GET | `/jobs/{job_id}/profile` | 200 `DatasetProfile` | The profile alone (409 until it's ready) |
| GET | `/jobs/{job_id}/deck.pptx` | 200 `.pptx` file | The rendered deck, as an attachment (409 until it's ready) |
| POST | `/jobs/{job_id}/retry` | 202 `JobCreated` | Resume a failed job from the stage that failed |
| GET | `/samples` | 200 `Sample[]` | Bundled example datasets, with a suggested question and outcome |
| GET | `/samples/{name}.csv` | 200 CSV | Download an example dataset |

### `POST /jobs`

This endpoint takes `multipart/form-data` with two fields:
- `file` (required): a `.csv`, `.xlsx` or `.xls` file of at most `MAX_UPLOAD_MB` (default 25).
- `options` (optional): a JSON string of `AnalysisOptions`:

```json
{ "num_slides": 10, "tone": "executive", "audience": "business stakeholders",
  "question": "Why do customers churn?", "target_column": "churned" }
```

| Field | Values |
|---|---|
| `num_slides` | 4–25 |
| `tone` | `executive`, `technical` or `casual` |
| `audience` | Up to 200 characters |
| `question` | Optional, up to 300 characters. The report answers it first |
| `target_column` | Optional outcome column. Matched case-insensitively and rejected with 400 `INVALID_OPTIONS` if the file doesn't have it. When omitted, the outcome is inferred |

The file is parsed synchronously, so invalid input is rejected here instead of becoming a failed job:

```
curl -F file=@sales.csv -F 'options={"num_slides":8}' localhost:8000/api/v1/jobs
→ 202 {"job_id": "7d0c…", "status": "queued"}
```

### `JobState`

```
job_id, filename, options, created_at, updated_at
status        queued | running | completed | failed
stages[5]     { key: ingest | profile | explore | analyze | generate_deck,
                label, status: pending | running | done | failed,
                started_at, finished_at, message }
profile?      DatasetProfile   (set once profiling is done)
roles?        { time, measures[], dimensions[], binaries[], entity, value_measure, targets[] }
findings?     Finding[]        (set by explore; Claude's follow-ups are appended during analyze)
insights?     Insights         (set once analysis is done)
grounding?    { checked, unverified[{ location, value, context }] }
deck?         ResolvedSlide[]  (set once the deck is rendered; drives the web preview)
presentation? { format: "pptx", slide_count, size_bytes, download_path }
error?        { stage, code, message }
```

### `DatasetProfile`

- **Dataset level:**
  - Size: `n_rows`, `n_cols`, `memory_bytes`, `duplicate_rows`
  - Missing data: `missing_cells_total`, `missing_pct_total` (a percentage from 0 to 100)
  - Sampling: `sampled`, `sample_rows`
- **`columns[]`:**
  - Always present: `name`, `inferred_type` (`numeric`, `categorical`, `datetime`, `boolean`, `text` or `id`), `dtype`, `missing_count`, `missing_pct`, `unique_count`
  - Numeric columns: `mean`, `std`, `min`, `p25`, `median`, `p75`, `max`, `skew`, `outlier_count` (IQR method), `infinite_count`
  - Categorical and boolean columns: `top_values[{value, count}]` (at most 10)
  - Datetime columns: `min_date`, `max_date` (ISO format)
- **Correlations:**
  - `correlation`: `{method: "pearson", columns[], matrix[][]}` or null (a symmetric matrix, with null where it's undefined)
  - `top_correlations[{a, b, r}]`: pairs with |r| ≥ 0.5, sorted by |r|
- **`warnings[]`:** human-readable data quality notes.

Values that can't be represented, such as NaN or ±inf, are always `null`.

### `Finding`

This is evidence computed by the analysis engine. Every number in it comes from Pandas or SciPy.

```
id            F1, F2, … (ranked; follow-ups continue the sequence)
kind          segment | bins | trend | concentration | crosstab | drivers
title, summary, headline     templated from the computed numbers
target, dimension, agg       what was analyzed (dimension = the grouping column or driver)
effect        { name, value, strength: negligible | weak | moderate | strong }
p_value, q_value, n, significant
chart         { kind: bars | line | ranking, categories[], values[], value_format,
                reference?, reference_label?, counts? }
caveats[], filter?, source: battery | follow_up, score, facts{}
```

- **Effect names:**
  - `rate ratio`: the highest group or band rate divided by the lowest.
  - `epsilon squared`: from Kruskal-Wallis.
  - `Spearman rho` and `rank-biserial r`.
  - `Cramer's V`.
  - `seasonal ratio`: the peak month average divided by the trough month average.
  - `top-20% share`.
- **`q_value`:** Benjamini-Hochberg across every test the battery ran. Follow-ups carry only `p_value`.

### `Insights`

This is Claude's structured output. Claims cite evidence through `finding_ids`:

```
executive_summary
key_findings[{ title, detail, finding_ids[] }]
questions_answered[{ question, answer, finding_ids[], confidence }]   the user's question first
open_questions[{ question, why_it_matters }]
hypotheses[{ statement, rationale, test, finding_ids[], confidence }]
recommended_actions[], data_quality_notes[]
slides[]      SlideSpec: layout + prose + references, never figures (see below)
```

### Slides: `SlideSpec` (what Claude writes) and `ResolvedSlide` (what is rendered)

Each slide has a `layout`. Claude writes the prose and *references* to numbers. The backend resolves those references against the profile, trims text to per-layout budgets, and renders the result.

| layout | Written by Claude | Added when resolved |
|---|---|---|
| `title` | `title`, `subtitle` | `meta` (dataset name, rows × columns, date) |
| `executive_summary` | `headline`, `takeaways[{title, text}]` (3) | — |
| `kpi_cards` | `title`, `kpis[{label, metric: MetricRef}]` (3–4) | `kpis[{label, value, caption}]` |
| `chart_insight` | `title`, `bullets[]` (≤ 3), `chart: ChartRef` | `chart: {kind, caption, categories[], values[], value_format}` or null |
| `hypotheses` | `title`, `items[{statement, test, confidence}]` (2–3) | — |
| `next_steps` | `title`, `steps[]` (3–4) | — |

- **`MetricRef`** is `{metric, column, finding_id}`. Set unused fields to null.
  - `metric: "finding"` with a `finding_id` shows that finding's `headline`. This is the preferred form.
  - Dataset metrics take `column: null`: `rows`, `columns`, `missing_cells_pct` and `duplicate_rows`.
  - Column metrics name a column: `mean`, `median`, `min`, `max` and `std` (numeric columns only), plus `unique_count`, `missing_pct` and `top_value_share`.
- **`ChartRef`** is `{chart, column, finding_id}`:
  - `chart: "finding"` with a `finding_id` draws that finding's chart: bars for segments, columns for bands and concentration, a line for trends. This is the preferred form.
  - `correlations` and `missing_values` take `column: null`.
  - `top_values` needs a categorical or boolean column.
  - `numeric_summary` needs a numeric column.
- **References that can't be resolved** degrade instead of failing: the KPI card is dropped, or `chart` becomes `null` and the slide renders as text only.

## Errors

Every non-2xx response has this shape:

```json
{ "error": { "code": "INVALID_FILE", "message": "Could not parse the CSV: …", "details": null } }
```

| HTTP | Code | When |
|---|---|---|
| 400 | `INVALID_FILE`, `EMPTY_DATASET`, `INVALID_OPTIONS` | Upload validation |
| 413 | `FILE_TOO_LARGE` | Upload over the limit |
| 404 | `JOB_NOT_FOUND` | Unknown or expired job |
| 409 | `JOB_NOT_RETRYABLE`, `PROFILE_NOT_READY`, `DECK_NOT_READY` | Wrong job state |
| 404 | `SAMPLE_NOT_FOUND` | Unknown example dataset |
| 422 | `VALIDATION_ERROR` | Malformed request (`details` lists the fields) |

These codes appear in `JobState.error` when a stage fails. They never come back as HTTP errors:

| Code | Stage | Meaning |
|---|---|---|
| `LLM_ERROR` | analyze | Claude API error: bad key, rate limit, outage or refusal |
| `LLM_SCHEMA_ERROR` | analyze | Two attempts without a valid structured answer |
| `DATASET_EXPIRED` | profile, explore | The in-memory dataset expired before these stages ran. Upload again |
| `DECK_RENDER_ERROR` | generate_deck | The deck couldn't be rendered (logged). Retry renders it again and keeps the insights |
| `INTERNAL_ERROR` | any | Unexpected server error (logged) |
