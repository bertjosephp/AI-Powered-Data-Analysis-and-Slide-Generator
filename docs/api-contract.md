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
| POST | `/jobs/{job_id}/retry` | 202 `JobCreated` | Resume a failed job from the stage that failed |

### `POST /jobs`

This endpoint takes `multipart/form-data` with two fields:
- `file` (required): a `.csv`, `.xlsx` or `.xls` file of at most `MAX_UPLOAD_MB` (default 25).
- `options` (optional): a JSON string of `AnalysisOptions`:

```json
{ "num_slides": 10, "tone": "executive", "audience": "business stakeholders",
  "theme_id": null, "export_as": "pdf" }
```

| Field | Values |
|---|---|
| `num_slides` | 4–25 |
| `tone` | `executive`, `technical` or `casual` |
| `audience` | Up to 200 characters |
| `theme_id` | A Gamma theme ID, or null |
| `export_as` | `pdf`, `pptx` or null |

The file is parsed synchronously, so invalid input is rejected here instead of becoming a failed job:

```
curl -F file=@sales.csv -F 'options={"num_slides":8}' localhost:8000/api/v1/jobs
→ 202 {"job_id": "7d0c…", "status": "queued"}
```

### `JobState`

```
job_id, filename, options, created_at, updated_at
status        queued | running | completed | failed
stages[4]     { key: ingest | profile | analyze | generate_deck,
                label, status: pending | running | done | failed,
                started_at, finished_at, message }
profile?      DatasetProfile   (set once profiling is done)
insights?     Insights         (set once analysis is done)
presentation? { gamma_generation_id, status: pending | completed | failed,
                gamma_url, export_url, credits_deducted, error, mock }
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

### `Insights`

This is Claude's structured output:

```
executive_summary
key_findings[{ title, detail, supporting_stats[] }]
hypotheses[{ statement, rationale, suggested_test, confidence: low | medium | high }]
analytical_questions[{ question, why_it_matters }]
data_quality_notes[], recommended_next_steps[]
slide_outline[{ title, bullets[] }]      one entry per slide, sent to Gamma
```

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
| 409 | `JOB_NOT_RETRYABLE`, `PROFILE_NOT_READY` | Wrong job state |
| 422 | `VALIDATION_ERROR` | Malformed request (`details` lists the fields) |

These codes appear in `JobState.error` when a stage fails. They never come back as HTTP errors:

| Code | Stage | Meaning |
|---|---|---|
| `LLM_ERROR` | analyze | Claude API error: bad key, rate limit, outage or refusal |
| `LLM_SCHEMA_ERROR` | analyze | Two attempts without a valid structured answer |
| `GAMMA_ERROR` | generate_deck | Gamma API error or failed generation |
| `GAMMA_TIMEOUT` | generate_deck | Still pending after `GAMMA_TIMEOUT_S`. Retry resumes the same generation |
| `INTERNAL_ERROR` | any | Unexpected server error (logged) |
