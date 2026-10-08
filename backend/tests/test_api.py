"""API tests: every endpoint through TestClient + temp SQLite.

The app's session/client-id dependencies are overridden to point at a
per-test SQLite database (Base.metadata.create_all + seed rows). Fully
offline: no Postgres, no SMTP, no provider calls.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_client_id
from app.db import get_db
from app.main import create_app
from app.models import (
    AlertDigest,
    Base,
    Client,
    Keyword,
    Mention,
    MentionSource,
    Sentiment,
    make_url_hash,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def db(tmp_path):
    """Fresh SQLite database per test, schema created, session exposed."""
    engine = create_engine(f"sqlite:///{tmp_path}/api.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api(db):
    """TestClient with session + client-scope dependencies overridden."""
    client_row = Client(name="acme")
    db.add(client_row)
    db.commit()

    app = create_app()

    def override_db():
        yield db

    def override_client_id():
        return client_row.id

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_client_id] = override_client_id
    with TestClient(app) as test_client:
        yield test_client


def seed_mention(
    db,
    client_id: int,
    url: str,
    *,
    source=MentionSource.news_rss,
    title: str | None = "t",
    content: str | None = None,
    sentiment=None,
    published: datetime | None = None,
    ingested: datetime | None = None,
    keyword_id: int | None = None,
    reach: int | None = None,
) -> Mention:
    mention = Mention(
        client_id=client_id,
        source=source,
        url=url,
        url_hash=make_url_hash(url),
        title=title,
        content=content,
        sentiment=sentiment,
        published_at=published,
        ingested_at=ingested or now_utc(),
        keyword_id=keyword_id,
        reach=reach,
    )
    db.add(mention)
    db.commit()
    return mention


def first_client_id(db) -> int:
    """The single client row created by the `api` fixture."""
    return db.scalar(select(Client.id).limit(1))


# ---------------------------------------------------------------- health


def test_api_health_ok(api) -> None:
    response = api.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------- mentions


def test_mentions_empty_state(api) -> None:
    response = api.get("/api/mentions")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


@pytest.fixture()
def mentions_seeded(db):
    """Three mentions: two classified, one with NULL sentiment."""
    client_id = first_client_id(db)
    kw = Keyword(client_id=client_id, text="acme", language="es")
    db.add(kw)
    db.commit()
    now = now_utc()
    m1 = seed_mention(
        db,
        client_id,
        "https://news.example.com/a",
        title="Acme lanza producto",
        content="noticia",
        sentiment=Sentiment.positive,
        published=now - timedelta(hours=3),
        ingested=now - timedelta(hours=2),
        keyword_id=kw.id,
    )
    m2 = seed_mention(
        db,
        client_id,
        "https://x.com/acme/2",
        source=MentionSource.x_twitter,
        title="Acme tweet",
        sentiment=Sentiment.negative,
        published=now - timedelta(hours=1),
        ingested=now - timedelta(hours=1),
        reach=42,
    )
    m3 = seed_mention(
        db,
        client_id,
        "https://gdelt.example/c",
        source=MentionSource.gdelt,
        title="zapatorio menciona a Acme",
        content="texto suelto",
        sentiment=None,
        published=now - timedelta(hours=2),
        ingested=now - timedelta(minutes=30),
    )
    return m1, m2, m3


def test_mentions_list_ordered_newest_first(api, mentions_seeded) -> None:
    m1, m2, m3 = mentions_seeded
    body = api.get("/api/mentions").json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [m2.id, m3.id, m1.id]
    item = body["items"][0]
    assert item["source"] == "x_twitter"
    assert item["sentiment"] == "negative"
    assert set(item) >= {
        "id",
        "keyword_id",
        "source",
        "url",
        "title",
        "content",
        "sentiment",
        "sentiment_score",
        "reach",
        "published_at",
        "ingested_at",
    }


def test_mentions_null_sentiment_serializes_null(api, mentions_seeded) -> None:
    m1, _m2, m3 = mentions_seeded
    items = {m["id"]: m for m in api.get("/api/mentions").json()["items"]}
    assert items[m3.id]["sentiment"] is None
    assert items[m1.id]["sentiment"] == "positive"


def test_mentions_filter_source_and_sentiment(api, mentions_seeded) -> None:
    m1, m2, m3 = mentions_seeded
    url = "/api/mentions"
    assert [i["id"] for i in api.get(url, params={"source": "x_twitter"}).json()["items"]] == [m2.id]
    assert (
        [i["id"] for i in api.get(url, params={"sentiment": "positive"}).json()["items"]]
        == [m1.id]
    )
    # "none" is the explicit NULL-sentiment filter.
    assert (
        [i["id"] for i in api.get(url, params={"sentiment": "none"}).json()["items"]]
        == [m3.id]
    )


def test_mentions_filter_keyword_and_window(api, mentions_seeded) -> None:
    m1, _m2, m3 = mentions_seeded
    now = now_utc()
    url = "/api/mentions"
    assert (
        [i["id"] for i in api.get(url, params={"keyword_id": m1.keyword_id}).json()["items"]]
        == [m1.id]
    )
    between = api.get(
        url,
        params={
            "since": (now - timedelta(hours=2, minutes=30)).isoformat(),
            "until": (now - timedelta(hours=1, minutes=30)).isoformat(),
        },
    ).json()
    assert [i["id"] for i in between["items"]] == [m3.id]


def test_mentions_q_searches_title_and_content(api, mentions_seeded) -> None:
    _m1, _m2, m3 = mentions_seeded
    by_content = api.get("/api/mentions", params={"q": "zapatorio"}).json()
    assert [i["id"] for i in by_content["items"]] == [m3.id]
    by_title = api.get("/api/mentions", params={"q": "ACME"}).json()
    assert by_title["total"] == 3  # case-insensitive match on every title


def test_mentions_pagination_and_limit_bounds(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    for i in range(60):
        seed_mention(
            db,
            client_id,
            f"https://example.com/p/{i}",
            published=now - timedelta(minutes=i),
        )
    default = api.get("/api/mentions").json()
    assert len(default["items"]) == 50  # default limit
    assert default["total"] == 60

    page = api.get("/api/mentions", params={"limit": 10, "offset": 55}).json()
    assert len(page["items"]) == 5
    assert page["total"] == 60

    assert api.get("/api/mentions", params={"limit": 200}).status_code == 200
    assert api.get("/api/mentions", params={"limit": 0}).status_code == 422
    assert api.get("/api/mentions", params={"limit": 201}).status_code == 422


# ---------------------------------------------------------------- keywords


def test_keywords_empty_then_create(api) -> None:
    assert api.get("/api/keywords").json() == []

    response = api.post(
        "/api/keywords", json={"text": "  acme  ", "language": "es"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["text"] == "acme"  # stripped
    assert body["is_active"] is True

    listed = api.get("/api/keywords").json()
    assert [k["text"] for k in listed] == ["acme"]


def test_keywords_create_validations(api) -> None:
    assert api.post("/api/keywords", json={"text": "   "}).status_code == 422
    assert (
        api.post("/api/keywords", json={"text": "x", "language": "fr"}).status_code
        == 422
    )


def test_keywords_create_duplicate_conflict(api) -> None:
    api.post("/api/keywords", json={"text": "acme"})
    response = api.post("/api/keywords", json={"text": "acme"})
    assert response.status_code == 409


def test_keyword_patch_rename_and_toggle(api) -> None:
    kw_id = api.post("/api/keywords", json={"text": "acme"}).json()["id"]
    response = api.patch(
        f"/api/keywords/{kw_id}", json={"text": "acme corp", "is_active": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "acme corp"
    assert body["is_active"] is False
    # inactive keywords remain listed (dashboard toggles them back on)
    assert any(k["id"] == kw_id for k in api.get("/api/keywords").json())


def test_keyword_patch_validations(api) -> None:
    kw_id = api.post("/api/keywords", json={"text": "acme"}).json()["id"]
    other_id = api.post("/api/keywords", json={"text": "rival"}).json()["id"]
    assert api.patch("/api/keywords/999999", json={"text": "x"}).status_code == 404
    # rename onto an existing text -> conflict
    assert (
        api.patch(f"/api/keywords/{kw_id}", json={"text": "rival"}).status_code == 409
    )
    assert (
        api.patch(f"/api/keywords/{other_id}", json={"text": " "}).status_code == 422
    )


def test_keyword_delete(api, db) -> None:
    client_id = first_client_id(db)
    kw_id = api.post("/api/keywords", json={"text": "lonely"}).json()["id"]
    assert api.delete(f"/api/keywords/{kw_id}").status_code == 204
    assert api.delete(f"/api/keywords/{kw_id}").status_code == 404

    used_id = api.post("/api/keywords", json={"text": "used"}).json()["id"]
    seed_mention(db, client_id, "https://x.com/1", keyword_id=used_id)
    seed_mention(db, client_id, "https://x.com/2", keyword_id=used_id)
    response = api.delete(f"/api/keywords/{used_id}")
    assert response.status_code == 409
    assert "mention" in response.json()["detail"]
    assert api.get("/api/keywords").json()[0]["id"] == used_id


# ---------------------------------------------------------------- stats


def test_stats_overview_shape(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    seed_mention(db, client_id, "https://a/1", sentiment=Sentiment.positive,
                 published=now - timedelta(minutes=10))
    seed_mention(db, client_id, "https://a/2", sentiment=Sentiment.negative,
                 source=MentionSource.x_twitter, published=now - timedelta(minutes=5))
    seed_mention(db, client_id, "https://a/3", sentiment=None,
                 source=MentionSource.gdelt, published=now - timedelta(hours=30))

    body = api.get("/api/stats/overview").json()
    assert body["total"] == 3
    assert body["by_sentiment"] == {
        "positive": 1,
        "negative": 1,
        "neutral": 0,
        "null": 1,
    }
    assert body["by_source"] == {
        "news_rss": 1,
        "gdelt": 1,
        "x_twitter": 1,
        "facebook_page": 0,
    }
    assert body["last_24h"] == 2
    assert body["last_7d"] == 3
    volume = body["daily_volume"]
    assert len(volume) == 30
    expected_today = sum(
        1 for offset in (10, 5) if (now - timedelta(minutes=offset)).date() == now.astimezone(timezone.utc).date()
    )
    assert volume[-1] == {"date": now.astimezone(timezone.utc).date().isoformat(), "count": expected_today}
    counts = [point["count"] for point in volume]
    assert sum(counts) == 3
    assert volume[0]["date"] < volume[-1]["date"]


def test_stats_overview_empty(api) -> None:
    body = api.get("/api/stats/overview").json()
    assert body["total"] == 0
    assert body["by_sentiment"]["null"] == 0
    assert body["last_24h"] == 0
    assert all(point["count"] == 0 for point in body["daily_volume"])
    assert len(body["daily_volume"]) == 30


# ---------------------------------------------------------------- alerts


def test_alert_settings_defaults_when_missing(api) -> None:
    body = api.get("/api/alerts/settings").json()
    assert body == {"digest": "instant", "recipient_email": None, "is_active": False}


def test_alert_settings_upsert_and_get(api) -> None:
    payload = {
        "digest": "daily",
        "recipient_email": "alerts@acme.com",
        "is_active": True,
    }
    assert api.put("/api/alerts/settings", json=payload).status_code == 200
    assert api.get("/api/alerts/settings").json() == {
        "digest": "daily",
        "recipient_email": "alerts@acme.com",
        "is_active": True,
    }

    updated = api.put(
        "/api/alerts/settings",
        json={"digest": "weekly", "recipient_email": "other@acme.com", "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["digest"] == "weekly"
    # exactly one row: the PUT updated, not duplicated
    rows = api.get("/api/alerts/settings").json()
    assert rows["recipient_email"] == "other@acme.com"


def test_alert_settings_validation(api) -> None:
    bad_digest = {"digest": "hourly", "recipient_email": "a@b.com", "is_active": True}
    assert api.put("/api/alerts/settings", json=bad_digest).status_code == 422
    bad_mail = {"digest": "daily", "recipient_email": "nope", "is_active": True}
    assert api.put("/api/alerts/settings", json=bad_mail).status_code == 422
