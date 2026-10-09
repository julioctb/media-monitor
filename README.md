# media-monitor

Brand media-monitoring (Mention-style) MVP: ingests brand mentions from Google
News RSS, GDELT, X/Twitter (via a third-party provider) and Facebook Pages,
scores their Spanish/English sentiment locally, stores them client-scoped in
Postgres, and serves them through a FastAPI API and a SvelteKit dashboard with
email alerting (instant or digest). Single-tenant by configuration, but every
row carries a `client_id`, so it can grow into a multi-tenant SaaS.

## Architecture

```
 Google News RSS ─┐
 GDELT DOC API ───┤   ┌───────────────────────────────┐
 X/Twitter prov ──┼──▶│ ingest worker (APScheduler,   │
 Facebook Pages ──┘   │ every INGEST_INTERVAL_MIN)    │
                      │ keyword match (ES/EN, accent- │
                      │ insensitive) → url_hash dedupe│
                      │ → sentiment (Laya, local)     │
                      └──────────────┬────────────────┘
                                     ▼ insert
   ┌─────────────────────────────────────────────┐
   │                PostgreSQL 16                │
   └──────────┬───────────────────────┬──────────┘
              │                       │ reads new mentions
              │                       ▼
    ┌─────────▼──────────┐   ┌──────────────────────────────────┐
    │ FastAPI  :8000     │   │ alert engine (runs inside the    │
    │ /api/mentions      │   │ worker after every cycle + cron) │
    │ /api/stats         │   │ instant email per cycle, or      │
    │ /api/keywords      │   │ daily/weekly digest 08:00        │
    │ /api/alerts        │   │ America/Mexico_City              │
    └─────────▲──────────┘   └──────────────┬───────────────────┘
              │ JSON (server-side only)     ▼
    ┌─────────┴────────────────┐    SMTP email — or, when SMTP_HOST
    │ SvelteKit :3000 SSR      │    is unset, a log-only line with
    │ feed·stats·keywords·     │    the full message (dev mode)
    │ alerts; filters, forms   │
    └──────────────────────────┘
```

- Google News RSS and GDELT need no credentials. The X provider and Facebook
  Pages adapters are skipped with one log line each when their keys are unset.
- The API has no CORS surface: the dashboard talks to it server-side only.
- Migrations (`alembic upgrade head`) run automatically on API container start.

## Quickstart (Docker)

```bash
cp .env.example .env        # fill in whatever keys you have; empty = disabled
docker compose up --build -d
```

| Service     | URL                          |
| ----------- | ---------------------------- |
| Dashboard   | http://localhost:3000        |
| API         | http://localhost:8000 (`GET /health`, `GET /api/health`) |
| Postgres    | localhost:5432 (`media`/`media`, db `mediamonitor`)      |

Then register a keyword and let the worker ingest:

```bash
curl -X POST localhost:8000/api/keywords -H 'Content-Type: application/json' \
  -d '{"text":"BUAP","language":"es"}'
# first ingest cycle runs within INGEST_INTERVAL_MIN; the worker log shows
# per-adapter fetched/inserted counts and the alert pass
```

## Local development (no Docker)

```bash
# 1. schema (the single migration is cross-db: sqlite + postgres)
DATABASE_URL=sqlite:///dev.db PYTHONPATH=backend .venv/bin/alembic \
  -c backend/alembic.ini upgrade head

# 2. API with hot reload
DATABASE_URL=sqlite:///dev.db PYTHONPATH=backend .venv/bin/python \
  -m uvicorn app.main:app --reload --port 8000

# 3. dashboard
cd frontend && npm run dev    # API_BASE_URL=http://localhost:8000
```

Canonical sqlite URLs are `sqlite:///relative` and `sqlite:////absolute`;
common shorthand (`sqlite:./x`, `sqlite:/x`) is healed by
`normalize_database_url`. The test suites build the schema via
`create_all` and never touch alembic.

## Configuration

All variables live in `.env` (see `.env.example`). Backend variables are read
by `backend/app/config.py` (pydantic-settings); the last two belong to the
frontend.

| Variable | Meaning | Default |
| -------- | ------- | ------- |
| `DATABASE_URL` | Postgres connection string (psycopg; bare `postgres://` is normalized) | `postgresql+psycopg://media:media@localhost:5432/mediamonitor` |
| `DEFAULT_CLIENT_ID` | Client scope for API and workers (id 1 `default` is seeded by migration 0001) | `1` |
| `INGEST_INTERVAL_MIN` | Minutes between worker ingest cycles | `15` |
| `X_PROVIDER_API_KEY` | Bearer token for the twitterapi.io-compatible search API; unset disables the adapter | _(empty)_ |
| `X_PROVIDER_BASE_URL` | Base URL of the X provider (any compatible API) | `https://api.twitterapi.io` |
| `X_PROVIDER_RATE_PER_MIN` | Client-side token bucket: max search requests/minute | `10` |
| `FB_PAGES` | JSON array of `{"page_id","token","label"}`, one page token per page; unset/empty disables the adapter | _(empty)_ |
| `FB_GRAPH_API_VERSION` | Pinned Meta Graph API version | `v26.0` |
| `SMTP_HOST` | Alert relay host; unset = log-only transport (email printed to the worker log) | _(empty)_ |
| `SMTP_PORT` | SMTP port — 587 uses STARTTLS, 465 implicit TLS | `587` |
| `SMTP_USER` | SMTP login (empty = no auth) | _(empty)_ |
| `SMTP_PASSWORD` | SMTP password | _(empty)_ |
| `ALERT_FROM` | `From:` header on alert emails | `alerts@example.com` |
| `API_BASE_URL` | API base URL used by the dashboard **server-side** (SSR load/form actions) | `http://localhost:8000`; the compose `dashboard` service pins `http://api:8000` |
| `ORIGIN` | Public origin of the dashboard, used by adapter-node for the CSRF/form-action check — must match the URL users browse to, or form POSTs 403 | compose pins `http://localhost:3000` |

`docker compose` pins `API_BASE_URL`/`ORIGIN` for the `dashboard` service; to
change them, edit `docker-compose.yml` (or run the dashboard natively with
your own env).

## Source setup

### X / Twitter (third-party provider)

1. Create an account on [twitterapi.io](https://twitterapi.io) (or any
   compatible provider) and copy the API key from its dashboard.
2. Set `X_PROVIDER_API_KEY` (and `X_PROVIDER_BASE_URL` if not
   twitterapi.io). Every search request is rate-lined client-side to
   `X_PROVIDER_RATE_PER_MIN` and logged as one structured JSON line with its
   estimated cost at $0.15 per 1,000 tweets.
3. With the key unset the adapter is skipped and the rest of the pipeline
   keeps running.

### Facebook Pages (client-owned pages)

1. Create an app on [developers.facebook.com](https://developers.facebook.com)
   (Business type) and connect it to the Page.
2. Grant the app `pages_show_list` and **`pages_read_engagement`** for the
   Page.
3. Exchange a short-lived user token for a long-lived **page token** (`GET
   /me/accounts` with `pages_show_list`, or the `fb_exchange_token` grant);
   page tokens do not expire with the user session.
4. Put `page_id` + token into `FB_PAGES`:
   `FB_PAGES=[{"page_id":"123","token":"EAAG...","label":"Client Page"}]`.

**Third-party pages** (the client does not administer them) work through the
same adapter but require Meta's one-time **Page Public Content Access** app
review plus business verification — an ops/app-review task, no code change.
A scraper fallback (e.g. Apify) remains a phase-2 option.

## Alerts

Configured via the dashboard (or `PUT /api/alerts/settings`) with `digest` =
`instant` | `daily` | `weekly`, a recipient and `is_active`. Instant sends one
batched email per ingest cycle (capped at 20 mentions); daily/weekly mark
pending state during cycles and send at 08:00 America/Mexico_City (daily, and
Mondays weekly), with totals, sentiment breakdown and the latest mentions.
With `SMTP_HOST` unset the transport is log-only: the full email is printed by
the worker (`[dev] SMTP_HOST unset; email logged only — to=… subject=…`), so
the pipeline is testable with zero infrastructure.

## Sentiment

Sentiment is scored during ingest (failures leave it NULL, visible as
“Sin clasificar” and filterable with `sentiment=none`). The engine is
[Laya](https://huggingface.co/convaiinnovations/laya) (Apache-2.0,
self-hosted typed-decision encoder, `laya==0.3.4`) via its `choice` primitive;
the **multilingual** checkpoint handles Spanish (the root checkpoint is
English-only). The model (~322M params) downloads on first analyze. The
`KeywordBaselineAnalyzer` word-list fallback exists for tests/offline runs;
pysentimiento was rejected for license reasons (TASS, non-commercial).

Evaluated against 50 hand-labeled Mexican-Spanish mentions
(`backend/scripts/eval_mentions_es.jsonl`): **Laya 82% accuracy**
(sarcasm 3/5) vs 42% keyword baseline. Re-run:

```bash
.venv/bin/python backend/scripts/eval_sentiment.py             # real Laya model
.venv/bin/python backend/scripts/eval_sentiment.py --baseline  # word-list floor
```

Rows left with NULL sentiment (analyzer hiccups) can be re-scored anytime:

```bash
.venv/bin/python backend/scripts/backfill_sentiment.py         # uses DATABASE_URL
```

## Testing

```bash
.venv/bin/python -m pytest backend/tests/ -q        # backend (132 tests)
cd frontend && npm run check                        # svelte-check, 0 errors
cd frontend && npm run test                         # vitest
cd frontend && npm run build                        # adapter-node production build
```

## Project structure

```
backend/
  app/
    api/          REST routers: mentions, stats, keywords, alerts, deps
    alerts/       alert engine + SMTP/log transport
    ingest/       source adapters (google_news, gdelt, twitter_x, facebook_page),
                  keyword matching, pipeline, rate limit
    models/       SQLAlchemy models + queries (client-scoped, url_hash dedupe)
    sentiment/    SentimentAnalyzer interface, Laya engine, keyword baseline
    config.py     pydantic-settings (every env var above)
    db.py         engine (pool_pre_ping) + session factory
    main.py       FastAPI app factory (/health, /api/*)
    worker.py     APScheduler: ingest cycle + alert hook + digest crons
  migrations/     Alembic (0001 initial schema, cross-db: sqlite + postgres)
  scripts/        eval_sentiment.py (+ 50-row eval set), backfill_sentiment.py
  tests/          pytest suite
frontend/
  src/routes/     feed (/), stats, keywords, alerts (+page.server.ts SSR)
  src/lib/        typed API client, formatters
  Dockerfile      multi-stage build → adapter-node runtime
docker-compose.yml  db + api + worker + dashboard
```

## Deploy (VPS)

- Any 2–4 GB VPS: `git clone`, `cp .env.example .env`, fill secrets, `docker
  compose up -d`. Data persists in the `pgdata` volume; put a reverse proxy
  (Caddy/Nginx + TLS) in front of the dashboard and the API.
- **Set `ORIGIN` to the public dashboard URL** — adapter-node defaults to
  https origin-checking, and a mismatch makes every form action 403.
- Keep `SMTP_*`, `X_PROVIDER_API_KEY` and `FB_PAGES` in `.env` (never
  committed). Budget reference: ~$30/mo VPS + ~$20–50/mo X provider credits.
- Single-compose-node deployment; the data model is already multi-tenant if
  this grows into a SaaS.

## Roadmap

Phase 2 (see `odd/tasks/media-monitor-mvp.md`): Flutter mobile app on the same
API (push alerts), Instagram via Graph/linked-Facebook-page, Reddit + YouTube
sources, full-archive X search/streaming.
