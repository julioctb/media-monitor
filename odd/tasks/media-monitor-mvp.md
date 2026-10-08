# media-monitor — Feature Document

**Status**: IN PROGRESS · **Created**: 2026-10-08 · **Route**: delegated direct

## Objective
Build a media monitoring app (Mention-style) for Julio's client: track brand
mentions across news/web + X/Twitter, with dashboard, alerts, and Spanish
sentiment analysis. Single-tenant deliverable with multi-tenant-ready data
model (client_id on all rows) so it can evolve into a SaaS.

## Problem
Client needs to know when their brand is mentioned online (news, blogs, X).
Commercial tools (Mention, Brandwatch) are expensive; the viable path is
building on free/cheap sources: Google News RSS + GDELT (news/web, $0) and
X via economic third-party provider (~$0.15/1,000 reads). Facebook/Instagram
is API-restricted (Meta Content Library = approved research only) — deferred
to phase 2 with client negotiation.

## Source Decisions (verified 2026-10-08)
- X API official: pay-per-use $0.005/read since Feb 2026, streaming $5k+/mo,
  full-archive = legacy Pro/Enterprise only. NOT viable for MVP.
- X via third-party (e.g. twitterapi.io): ~$0.15/1,000 reads, 7-day+ archive.
- News/web: Google News RSS (free), GDELT (free), NewsAPI (optional $0–50/mo).
- Reddit/YouTube: free APIs, out of MVP scope, architecture allows adding.
- FB/IG: restricted; phase 2.

## Architecture
```
Ingest workers (Python, APScheduler):
  google_news.py  — RSS poll every 15 min
  gdelt.py        — GDELT 2.0 doc API poll every 15 min
  twitter_x.py    — provider API poll (pluggable: twitterapi.io compatible)
       ↓
Processing: dedupe (URL hash + simhash), keyword/brand matching (ES + EN),
  sentiment (pysentimiento, runs locally, Spanish-first)
       ↓
Postgres: mentions, alerts, keywords, sources, clients
       ↓
FastAPI: REST API (/mentions, /stats, /alerts, /keywords)
Dashboard: SvelteKit 2 + Tailwind (feed, filters, charts, alert config)
Deploy: Docker Compose (api, worker, db, dashboard) on a VPS
```

## Tasks
- [x] T1: Project scaffold — repo structure, pyproject, docker-compose, README
      (commit 136273a; 14 tests green; venv at .venv, uv absent)
- [x] T2: Domain model + migrations — clients, keywords, sources, mentions,
      alerts tables (SQLAlchemy + Alembic), all rows carry client_id
      (commit fad8613; offline SQL up/down verified; queries.py contract:
      insert_mention dedupes on url_hash, all reads client-scoped)
- [ ] T3: Ingest core — source adapter interface + Google News RSS adapter +
      GDELT adapter, dedupe pipeline, keyword matching (regex, ES+EN)
- [ ] T4: X/Twitter adapter — pluggable provider interface, twitterapi.io-
      compatible client, rate limiting, cost tracking per query
- [ ] T5: Sentiment — pysentimiento integration, runs on ingest, es + en
- [ ] P1: FastAPI app — /mentions, /stats, /keywords, /alerts endpoints
- [ ] P2: Alert engine — email alerts on new matching mentions (SMTP),
      digest mode (daily/weekly), per-keyword alert config
- [ ] P3: Dashboard — SvelteKit feed with filters (source, sentiment, date),
      stats charts, keyword management, alert settings
- [ ] T6: E2E verification — docker compose up, ingest real data for a test
      keyword, verify mentions in dashboard, alert email sent
- [ ] T7: Docs — README with setup, .env.example, architecture doc

## Phase 2 (future, not in MVP scope)
- **Flutter mobile app** (iOS + Android) consuming the same FastAPI API:
  push notifications for instant alerts, feed, and stats. Decided 2026-10-08:
  web MVP stays SvelteKit (DOM is right for dashboards, user prefers SvelteKit
  for maintainability); Flutter is the right tool when native mobile + push
  is required. Backend is client-agnostic — zero rework needed.
- **Facebook/Instagram sources** — requires Meta access negotiation
  (Content Library API is research-only) or third-party providers.
- **Reddit + YouTube sources** — free APIs, easy to add via source adapter.
- **Full-archive X search / streaming** — enterprise-tier features.

## Acceptance Criteria
- Ingests news (RSS+GDELT) and X mentions for configured keywords
- Dashboard shows feed with filters and sentiment badges
- Email alert when new mention matches keyword (or digest)
- All data scoped by client_id (multi-tenant ready)
- docker compose up runs the whole stack

## Constraints
- Python 3.13 available locally (/usr/local/bin/python3)
- X access via economic third-party provider, cost tracked per query
- No Facebook/Instagram in MVP
- Budget: ~$30/mes VPS + ~$20-50/mes X provider credits

## Progress Log
- 2026-10-08: Feature doc created. Sources verified (X API pricing 2026,
  Meta restrictions). Scope agreed with user: news/web + X, FB/IG phase 2.
