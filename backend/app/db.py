"""SQLAlchemy engine and session factory."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def normalize_database_url(url: str) -> str:
    """Map bare postgres:// URLs onto the psycopg driver dialect and heal
    common sqlite shorthand to parseable forms.

    sqlite:./rel  -> sqlite:///rel    (relative path)
    sqlite:/abs   -> sqlite:////abs   (absolute path, slash kept)
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    # sqlite:./x is the intuitive-but-invalid relative form.
    if url.startswith("sqlite:./"):
        return "sqlite:///" + url[len("sqlite:./") :]
    # sqlite:/x (single slash) is the intuitive absolute form; keep the
    # leading slash so the result has four slashes total.
    if url.startswith("sqlite:/") and not url.startswith("sqlite://"):
        return "sqlite:////" + url[len("sqlite:/") :]
    return url


engine = create_engine(
    normalize_database_url(settings.database_url),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
