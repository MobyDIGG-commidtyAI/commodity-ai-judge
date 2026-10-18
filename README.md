# Commodity AI — news judge

Reads this month's hardware news and scores the **price pressure** it implies for next month's DDR5 and consumer GPU
retail prices, using an LLM with an eight-dimension rubric (supply, demand, disruption, scope, duration, category,
certainty, impact confidence). The daily job writes `export/judge.json` to the shared bucket, and
[commodity-ai-backend](https://github.com/MobyDIGG-commidtyAI/commodity-ai-backend) shows it next to the price evidence.

The score is signed (positive = upward pressure) with a direction: `UP` at +0.5 or more, `DOWN` at −0.5 or less, otherwise
`FLAT` (abstain). **It is not a calibrated price forecast**; the backtests in [docs/research.md](docs/research.md) do not yet
show predictive accuracy. The rubric and its sources: [docs/rubric.md](docs/rubric.md).

## Architecture

```mermaid
flowchart LR
  shopper(["Shopper on<br/>Shopee / Lazada"]) --> extension["commodity-ai-extension<br/>Chrome extension (developer mode)"]
  extension -->|HTTPS /api/v2/assessment| api
  browser(["Browser"]) -->|/dashboard| api

  subgraph gcp["Google Cloud · asia-southeast1"]
    scheduler["Cloud Scheduler<br/>09:00 Asia/Bangkok"] --> job["Cloud Run Job<br/>commodity-ai-caller"]
    scheduler --> judge["Cloud Run Job<br/>commodity-ai-judge (this repo)"]
    job -->|export/news_feed.csv · read-write| bucket[("Cloud Storage<br/>private · versioned bucket<br/>tank.db · export/")]
    bucket -->|read-only mount| api["Cloud Run service<br/>commodity-ai-backend · public"]
    job -->|write| sql[("Cloud SQL<br/>application database")]
    sql -->|read| api
    bucket -->|news feed + price contract| judge
    judge -->|export/judge.json| bucket
  end

  job --> sources["TrendForce · Reddit<br/>RSS · price indexes"]
  judge -->|DDR5 chat rubric and GPU article decisions| openrouter["OpenRouter"]
```

## One daily run (`scripts/cloud_job.sh`)

1. Copy `judgments.sqlite3` and the article cache from the bucket (`$DATA_MOUNT/judge/`) to local disk.
2. `python -m hardware_signal.cli daily`:
   - **DDR5:** the month's RAM headlines from the live news feed (up to `MAX_ARTICLES`), one chat call to `OPENROUTER_MODEL`.
   - **GPU:** fetch up to 40 linked GPU articles (cached), keep dated readable text, judge the newest 8 with the GPU Jev rubric
     (one Decisions API call each).
3. Write `judge.json` (schema below) to `$DATA_MOUNT/export/`; save the database and cache back.
4. Exit 3 when one category failed (the other is still published), so the job execution shows the failure.

```json
{"schema_version": 1, "generated_at": "...", "news_month": "2026-10",
 "items": {"DDR5": {"status": "SCORED", "as_of_month": "2026-10", "target_month": "2026-11", "direction": "FLAT",
                    "pressure": 0.21, "articles_considered": 20, "articles_judged": 20, "model": "...",
                    "evidence": [{"title": "...", "source": "...", "date": "...", "url": "...", "contribution": 0.12}]},
           "GPU": {"status": "NO_TEXT", "...": "..."}},
 "limitations": ["..."]}
```

`status` is `SCORED`, `NO_NEWS` / `NO_TEXT` (nothing to judge) or `ERROR` (details in the job log).

## Configuration

| Variable | Cloud Run Job | Local default |
|---|---|---|
| `OPENROUTER_API_KEY` | Secret Manager secret | `.env` |
| `OPENROUTER_MODEL` | e.g. the team's chosen `author/model` slug | `.env` |
| `DATA_MOUNT` | `/mnt/tank` (bucket mount, read-write) | unset: plain local run |
| `DATA_DIR` | `$DATA_MOUNT/partner/chin-2026-10-15` (set by the job script) | `dataset/chin` |
| `NEWS_FEED` | `$DATA_MOUNT/export/news_feed.csv` (set by the job script) | `dataset/ohm/news_feed.csv` |
| `MAX_ARTICLES` | `20` | `20` |

The job needs no third-party Python packages. The local test environment uses
Python 3.12.15 and pinned test tools in `environment.yml` and `requirements-dev.txt`.

## Local environment

```bash
CONDA_PKGS_DIRS=./.conda/pkgs conda env create --prefix ./.conda/codex/dev --file environment.yml
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate "./.conda/codex/dev" && python -m pip install -r requirements-dev.txt
```

## Run locally

```bash
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate "./.conda/codex/dev"
cp .env.example .env    # add OPENROUTER_API_KEY and OPENROUTER_MODEL; point DATA_DIR / NEWS_FEED at local copies
PYTHONPATH=src python -m hardware_signal.cli daily --output output/judge.json
```

The research commands (case export, backtests, evaluation, HTTP API) are described in [docs/research.md](docs/research.md).

## Test

```bash
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate "./.conda/codex/dev" && PYTHONPATH=src python -m pytest -q
```

Tests that need the team dataset (a teammate's price contract and news archive, kept private) are skipped unless
`DATA_DIR` / `NEWS_FEED` point at a copy.

## Deploy (Google Cloud)

This image runs as a **Cloud Run Job**, not a Cloud Run Service. Build and push it
to an Artifact Registry repository, then deploy the image as a job:

```bash
export PROJECT_ID=your-project-id
export REPO=your-repository-name
export REGION=asia-southeast1
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/commodity-ai-judge:latest"
gcloud builds submit --tag "$IMAGE" .
gcloud run jobs deploy commodity-ai-judge --region "$REGION" --image "$IMAGE" \
  --set-env-vars DATA_MOUNT=/mnt/tank,OPENROUTER_MODEL=<author/model> \
  --set-secrets OPENROUTER_API_KEY=<secret-name>:latest \
  --add-volume name=tank,type=cloud-storage,bucket=<BUCKET> --add-volume-mount volume=tank,mount-path=/mnt/tank \
  --memory 512Mi --cpu 1 --task-timeout 30m --max-retries 0
```

Do not use a Cloud Run Service source-deploy trigger for this image: it does not
listen on `PORT=8080`. Schedule the judge after the caller job has finished and
published `export/news_feed.csv`. Cost: about 1 chat call plus up to 8 Jev calls a day.

## License

MIT
