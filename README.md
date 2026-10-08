# media-monitor

Brand media-monitoring (Mention-style) MVP: ingests brand mentions from Google
News RSS, GDELT, Facebook Pages and an X/Twitter third-party provider, stores
them client-scoped in Postgres, and serves them over a FastAPI API with email
alerting.

## Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic Settings
- **Database**: PostgreSQL 16
- **Deploy**: Docker Compose (`db` / `api` / `worker`)

## Run with Docker

```bash
cp .env.example .env        # fill X_PROVIDER_API_KEY / FB_PAGES / SMTP_* as needed
docker compose up --build
```

- API: http://localhost:8000 (health check: `GET /health`)
- Migrations run automatically on API startup (`alembic upgrade head`).

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e . pytest httpx
# point DATABASE_URL (.env) at a local Postgres, then:
cd backend && alembic upgrade head
uvicorn app.main:app --reload
```

## Tests

```bash
pytest
```

## Layout

    backend/app/main.py       FastAPI app factory
    backend/app/config.py     pydantic-settings configuration (env-driven)
    backend/app/db.py         SQLAlchemy engine + session factory
    backend/app/models/       domain model: clients, keywords, mentions, alert_settings
    backend/app/ingest/       source adapters: base, google_news, gdelt, facebook_page,
                              twitter_x, matching (ES+EN regex), pipeline, rate_limit
    backend/app/sentiment/    SentimentAnalyzer interface + Laya engine + keyword baseline
    backend/app/api/          REST API routers — upcoming
    backend/app/alerts/       email alert engine — upcoming
    backend/app/worker.py     APScheduler ingest loop (INGEST_INTERVAL_MIN)
    backend/scripts/          eval_sentiment.py + eval_mentions_es.jsonl (50 hand-labeled)
    backend/migrations/       Alembic migrations

## Sentiment

Sentiment runs in the ingest pipeline right after keyword matching and fills
`mentions.sentiment` / `sentiment_score`. The engine is
[Laya](https://huggingface.co/convaiinnovations/laya) (Apache-2.0,
self-hosted typed-decision encoder, `pip install laya==0.3.4`), invoked
through its `choice` primitive with positive/neutral/negative options.
pysentimiento is intentionally NOT used (its Spanish model trains on the
TASS dataset, non-commercial license).

- The model (~421M params, multilingual checkpoint) downloads lazily on
  first analyze; tests always use a mock analyzer.
- `KeywordBaselineAnalyzer` is a trivial word-list fallback (ES+EN,
  accent-insensitive) kept so the pipeline stays testable without the model.

Evaluate the engine against 50 hand-labeled Mexican-Spanish mentions
(14 positive / 16 negative / 15 neutral / 5 sarcastic):

```bash
.venv/bin/python backend/scripts/eval_sentiment.py             # real Laya model
.venv/bin/python backend/scripts/eval_sentiment.py --baseline  # word-list floor
```

Latest results: Laya 82% accuracy (sarcasm subset 3/5) vs baseline 42%.

## X/Twitter provider

Ingest via a twitterapi.io-compatible provider (`X_PROVIDER_BASE_URL` is
configurable). Each search request is rate-limited client-side
(`X_PROVIDER_RATE_PER_MIN`, token bucket) and logged as one structured JSON
line with estimated cost at $0.15 per 1,000 tweets. With
`X_PROVIDER_API_KEY` unset the adapter is skipped and the worker logs it
once — everything else keeps running.

## Facebook Pages

Client-owned pages are polled through the Meta Graph API
(`GET /{version}/{page-id}/posts`, latest posts, `limit=100` — the API's
per-request maximum). Set `FB_PAGES` to a JSON array with one entry per
page; each page uses its own page access token:

```
FB_PAGES=[{"page_id":"1234567890","token":"EAAG...","label":"BUAP Oficial"}]
FB_GRAPH_API_VERSION=v26.0
```

Token setup:

1. Create an app on [developers.facebook.com](https://developers.facebook.com)
   (business type) and connect it to the Page.
2. Grant the app `pages_show_list` and `pages_read_engagement` for the Page.
3. Exchange a long-lived user token for a long-lived **page token**
   (`GET /me/accounts` with `pages_show_list`, or the
   `fb_exchange_token` grant) — page tokens do not expire alongside
   short-lived user tokens.
4. Put `page_id` + token into `FB_PAGES`. Unset or empty means the adapter
   is disabled: the worker logs it once and the rest of the pipeline
   keeps running.

**Third-party pages** (the client does not own/administer them) work through
this same adapter but require Meta's one-time **Page Public Content Access**
app review plus business verification — an ops/app-review task, no code
change. A scraper fallback (e.g. Apify) remains a phase-2 option.

No client-side rate limiting, by design: one request per page per ingest
cycle stays far below Graph's per-page throttles.
