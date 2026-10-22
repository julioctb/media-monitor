FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY pyproject.toml README.md ./
COPY backend ./backend

RUN pip install --no-cache-dir .

# Headless Chromium for the Facebook public-page adapter (no tokens).
RUN python -m playwright install --with-deps chromium

# Keep the working directory on backend/ so `app`, `alembic.ini`
# and `migrations/` resolve without extra path configuration.
WORKDIR /srv/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
