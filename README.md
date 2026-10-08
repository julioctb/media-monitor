# media-monitor

Brand media-monitoring (Mention-style) MVP: ingests brand mentions from Google
News RSS, GDELT and an X/Twitter third-party provider, stores them client-scoped
in Postgres, and serves them over a FastAPI API with email alerting.

## Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic Settings
- **Database**: PostgreSQL 16
- **Deploy**: Docker Compose (`db` / `api` / `worker`)

## Run with Docker

```bash
cp .env.example .env        # fill X_PROVIDER_API_KEY / SMTP_* as needed
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
    backend/app/ingest/       source adapters (RSS, GDELT, X provider) — upcoming
    backend/app/api/          REST API routers — upcoming
    backend/app/alerts/       email alert engine — upcoming
    backend/app/worker.py     ingest worker entrypoint (placeholder loop)
    backend/migrations/       Alembic migrations
