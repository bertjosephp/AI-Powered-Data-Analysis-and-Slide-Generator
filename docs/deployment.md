# Deployment

The web app runs on **Vercel** and the API on **Render's free tier**. Production deploys go through GitHub Actions and run only after CI passes on `main`.

```
push to main ──► CI (tests, eval, e2e, Docker) ──► Deploy
                                                   ├─ API: Render deploy hook, then wait until /health reports the new commit
                                                   └─ Web: vercel build + deploy --prod, then smoke-check the domain
pull request ──► CI + a Vercel preview deploy
```

## How the free tier behaves

- **Cold start.** A free Render service sleeps after about 15 minutes idle, and the next request wakes it, which takes 30–60 s.
  - The web app pings `/health` on load. If the ping is slow or fails, a banner explains the cold start and shows an elapsed timer.
  - The upload button waits until the server answers.
- **Memory.** A free instance has 512 MB, so the blueprint caps uploads at 10 MB and profiles at most 50,000 rows.
- **State is in memory.** Jobs, results and demo counters reset whenever the service sleeps or redeploys.
  - Results last an hour at most anyway.
  - Keep it to one instance and one worker.

## Public-demo limits

Real Claude runs are capped. Past any limit, a run still completes on the offline, rule-based analyst, and the page says why.

| Setting | Default | Meaning |
|---|---|---|
| `DEMO_RUNS_PER_HOUR` | 3 | Claude runs per visitor IP per rolling hour |
| `DAILY_BUDGET_USD` | 3 | Spend cap, reset at 00:00 UTC; the actual token cost of each run is charged |
| `MAX_CONCURRENT_ANALYSES` | 2 | Claude runs in flight at once |

Also set a monthly spend limit in the Anthropic Console as a second safety net.

## One-time setup

### 1. Render (API)

1. Sign in at [render.com](https://render.com) with GitHub.
2. Go to **New → Blueprint**, pick this repository, and apply `render.yaml`. This creates `data-to-deck-api` on the free plan.
3. When prompted, fill in the unsynced variables:
   - `ANTHROPIC_API_KEY`: from the [Anthropic Console](https://console.anthropic.com/settings/keys). Use a dedicated key for the demo.
   - `CORS_ORIGINS`: the Vercel production URL from step 2, e.g. `https://data-to-deck.vercel.app`. You can fill it in after step 2.
   - `CORS_ORIGIN_REGEX` (optional): lets preview deploys call the API, e.g. `https://data-to-deck-[a-z0-9-]+-yourname\.vercel\.app`.
4. Wait for the first deploy, then open `https://<service>.onrender.com/api/v1/health`. It should return `"status":"ok"` and a `demo` block.
5. Under **Settings → Deploy Hook**, copy the URL. It is a secret.

Auto-deploy is off, so Render deploys only when the workflow calls the hook, which happens after CI passes.

### 2. Vercel (web)

1. Sign in at [vercel.com](https://vercel.com) with GitHub.
2. Go to **Add New → Project** and import this repository.
3. Set **Root Directory** to `apps/web`. The framework (Next.js) and pnpm are detected automatically.
4. Add these environment variables for Production and Preview:
   - `NEXT_PUBLIC_API_BASE_URL` = `https://<service>.onrender.com/api/v1`
   - `NEXT_PUBLIC_MAX_UPLOAD_MB` = `10`
5. Deploy. `apps/web/vercel.json` turns off Vercel's own deploys of `main`, so production goes through the workflow. Pull requests still get preview URLs.
6. Collect the IDs the workflow needs:
   - **Account Settings → Tokens:** create a token.
   - **Project → Settings → General:** the **Project ID**.
   - **Account (or Team) Settings → General:** your user or team ID. This is the org ID.

### 3. GitHub

In **Settings → Secrets and variables → Actions**, add the following.

| Kind | Name | Value |
|---|---|---|
| Secret | `RENDER_DEPLOY_HOOK` | Render deploy hook URL |
| Secret | `VERCEL_TOKEN` | Vercel token |
| Secret | `VERCEL_ORG_ID` | Vercel user or team ID |
| Secret | `VERCEL_PROJECT_ID` | Vercel project ID |
| Variable | `API_URL` | `https://<service>.onrender.com` (no path) |
| Variable | `WEB_URL` | `https://<project>.vercel.app` |

Then protect `main`:
1. Go to **Settings → Branches → Add rule** and set the pattern to `main`.
2. Require a pull request.
3. Require these status checks: *API · lint, types, tests & insight eval*, *Web · lint, types, tests & build*, *End-to-end (Playwright, mock mode)*, and *Docker images build and boot*.

Run **Actions → Deploy → Run workflow** once to confirm both halves go green.

## Day to day

- **Ship:** open a pull request. CI runs and Vercel posts a preview. Merge, and the Deploy workflow releases both halves.
- **Redeploy without a change:** **Actions → Deploy → Run workflow**.
- **Rotate the Claude key:** create a new key in the Console, update `ANTHROPIC_API_KEY` in Render (this redeploys), then revoke the old key.
- **Pause Claude spending:** set `DAILY_BUDGET_USD=0` in Render. Every run then uses the offline analyst.
- **Check spend:** `/api/v1/health` reports the budget left today. Each job's `usage` field has its token counts and cost.

## Running the containers locally

```bash
docker compose up --build   # API on :8000, web on :3000
```

The API image listens on `$PORT` (default 8000), which is how Render routes to it.
