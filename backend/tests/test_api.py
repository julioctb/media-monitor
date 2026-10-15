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
    Base,
    Client,
    Event,
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
    author: str | None = None,
    sentiment=None,
    published: datetime | None = None,
    ingested: datetime | None = None,
    keyword_id: int | None = None,
    reach: int | None = None,
    event_id: int | None = None,
) -> Mention:
    mention = Mention(
        client_id=client_id,
        source=source,
        url=url,
        url_hash=make_url_hash(url),
        title=title,
        content=content,
        author=author,
        sentiment=sentiment,
        published_at=published,
        ingested_at=ingested or now_utc(),
        keyword_id=keyword_id,
        reach=reach,
        event_id=event_id,
    )
    db.add(mention)
    db.commit()
    return mention


def first_client_id(db) -> int:
    """The single client row created by the `api` fixture."""
    return db.scalar(select(Client.id).limit(1))


# ---------------------------------------------------------------- events


def seed_event(db, client_id: int, title: str, first, last, **counts) -> Event:
    event = Event(
        client_id=client_id,
        title=title,
        title_tokens=title,
        first_seen_at=first,
        last_seen_at=last,
        **counts,
    )
    db.add(event)
    db.commit()
    return event


def test_events_empty_and_404(api, db) -> None:
    client_id = first_client_id(db)
    assert api.get(f"/api/clients/{client_id}/events").json() == []
    assert api.get("/api/clients/999999/events").status_code == 404
    assert api.get("/api/clients/999999/events/1").status_code == 404


def test_events_ordered_by_last_seen_with_since_filter(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    old = seed_event(db, client_id, " vieja", now - timedelta(days=3), now - timedelta(days=3))
    new = seed_event(db, client_id, "nueva", now - timedelta(hours=1), now)
    body = api.get(f"/api/clients/{client_id}/events").json()
    assert [e["id"] for e in body] == [new.id, old.id]

    since = now - timedelta(minutes=30)
    filtered = api.get(
        f"/api/clients/{client_id}/events", params={"since": since.isoformat()}
    ).json()
    assert [e["id"] for e in filtered] == [new.id]


def test_events_scoped_to_client(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    seed_event(db, client_id, "mia", now, now)
    other = Client(name="otro")
    db.add(other)
    db.commit()
    seed_event(db, other.id, "suya", now, now)
    mine = api.get(f"/api/clients/{client_id}/events").json()
    assert len(mine) == 1 and mine[0]["title"] == "mia"


def test_events_min_mentions_filter(api, db) -> None:
    """The eco view: only events with real multi-source coverage."""
    client_id = first_client_id(db)
    now = now_utc()
    big = seed_event(
        db, client_id, "Cobertura amplia", now, now, mention_count=4, source_count=3
    )
    seed_event(db, client_id, "Singleton", now, now, mention_count=1, source_count=1)

    body = api.get(f"/api/clients/{client_id}/events", params={"min_mentions": 2}).json()
    assert [e["id"] for e in body] == [big.id]

    all_rows = api.get(f"/api/clients/{client_id}/events").json()
    assert len(all_rows) == 2


def test_event_detail_orders_mentions_by_reach(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    event = seed_event(
        db, client_id, "BUAP noticia", now, now, mention_count=2, source_count=2
    )
    low = seed_mention(db, client_id, "https://example.com/low", reach=10, event_id=event.id)
    high = seed_mention(db, client_id, "https://example.com/high", reach=99, event_id=event.id)
    body = api.get(f"/api/clients/{client_id}/events/{event.id}").json()
    assert body["id"] == event.id
    assert [m["id"] for m in body["mentions"]] == [high.id, low.id]
    assert body["mention_count"] == 2


def test_event_detail_404_for_other_client(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    event = seed_event(db, client_id, "mia", now, now)
    other = Client(name="otro")
    db.add(other)
    db.commit()
    assert api.get(f"/api/clients/{other.id}/events/{event.id}").status_code == 404


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


def test_mentions_carry_linked_persons(api, db, mentions_seeded) -> None:
    """F3 chips: the feed payload names the persons linked to each mention."""
    from app.models import MentionPerson, Person

    m1, _m2, _m3 = mentions_seeded
    client_id = first_client_id(db)
    person = Person(client_id=client_id, name="Lilia Cedillo", name_key="lilia cedillo")
    db.add(person)
    db.flush()
    db.add(MentionPerson(mention_id=m1.id, person_id=person.id))
    db.commit()

    items = {m["id"]: m for m in api.get("/api/mentions").json()["items"]}
    assert items[m1.id]["persons"] == [{"id": person.id, "name": "Lilia Cedillo"}]
    assert items[_m2.id]["persons"] == []


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
        "rss_custom": 0,
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
    assert body == {
        "digest": "instant",
        "recipient_email": None,
        "is_active": False,
        "sentiment_shift_enabled": True,
        "sentiment_shift_threshold": 10.0,
    }


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
        "sentiment_shift_enabled": True,
        "sentiment_shift_threshold": 10.0,
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


# --------------------------------------------------------------- coverage


class TestEventCoverage:
    def test_counts_distinct_outlets_per_source(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        event = seed_event(db, client_id, "e", now, now, mention_count=3, source_count=2)
        seed_mention(db, client_id, "https://a.com/1", event_id=event.id)
        seed_mention(
            db, client_id, "https://a.com/2", source=MentionSource.gdelt, event_id=event.id
        )
        seed_mention(db, client_id, "https://b.com/1", event_id=event.id)
        body = api.get(f"/api/clients/{client_id}/events/{event.id}/coverage").json()
        assert body["event_id"] == event.id
        assert body["mention_count"] == 3
        assert body["outlet_count"] == 2
        by_source = {row["source"]: row for row in body["by_source"]}
        assert by_source["news_rss"]["n_mentions"] == 2
        assert by_source["news_rss"]["outlets"] == 2
        assert by_source["gdelt"]["n_mentions"] == 1
        assert by_source["gdelt"]["outlets"] == 1

    def test_zeroed_when_event_has_no_mentions(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        event = seed_event(db, client_id, "empty", now, now)
        body = api.get(f"/api/clients/{client_id}/events/{event.id}/coverage").json()
        assert body["mention_count"] == 0
        assert body["outlet_count"] == 0
        assert body["by_source"] == []

    def test_404_for_other_client(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        event = seed_event(db, client_id, "mia", now, now)
        other = Client(name="otro")
        db.add(other)
        db.commit()
        assert api.get(f"/api/clients/{other.id}/events/{event.id}/coverage").status_code == 404

    def test_author_fallback_when_url_has_no_host(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        event = seed_event(db, client_id, "e", now, now, mention_count=2, source_count=2)
        seed_mention(db, client_id, "not-a-url", author="@fuente", event_id=event.id)
        seed_mention(db, client_id, "https://b.com/1", event_id=event.id)
        body = api.get(f"/api/clients/{client_id}/events/{event.id}/coverage").json()
        assert body["outlet_count"] == 2


class TestClientCoverageSummary:
    def test_repetition_index_per_day(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        today = now.replace(hour=12, minute=0, second=0, microsecond=0)
        ev_a = seed_event(db, client_id, "a", today, today, mention_count=2, source_count=2)
        ev_b = seed_event(db, client_id, "b", today, today, mention_count=1, source_count=1)
        seed_mention(db, client_id, "https://a.com/1", event_id=ev_a.id, published=today)
        seed_mention(db, client_id, "https://b.com/1", event_id=ev_a.id, published=today)
        seed_mention(db, client_id, "https://a.com/2", event_id=ev_b.id, published=today)
        # Older window plus a foreign-client row that must not leak in.
        old_ev = seed_event(db, client_id, "old", now, now, mention_count=1, source_count=1)
        seed_mention(
            db,
            client_id,
            "https://old.com/1",
            event_id=old_ev.id,
            published=now - timedelta(days=3),
        )
        other = Client(name="otro")
        db.add(other)
        db.commit()
        other_ev = seed_event(db, other.id, "suyo", now, now)
        seed_mention(db, other.id, "https://x.com/1", event_id=other_ev.id, published=now)

        body = api.get(f"/api/clients/{client_id}/coverage/summary").json()
        today_row = next(row for row in body if row["date"] == today.date().isoformat())
        assert today_row["events"] == 2  # ev_a, ev_b (the old event is another day)
        assert today_row["mentions"] == 3
        assert today_row["multi_source_events"] == 1  # only ev_a spans two outlets
        assert today_row["repetition_pct"] == 50.0
        older = [row for row in body if row["date"] != today.date().isoformat()]
        assert len(older) == 1 and older[0]["events"] == 1
        # Client scope: the other client's event never shows up.
        assert all(row["events"] <= 2 for row in body)

    def test_days_window_clamped_1_90(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        event = seed_event(db, client_id, "old", now, now)
        seed_mention(
            db,
            client_id,
            "https://old.com/1",
            event_id=event.id,
            published=now - timedelta(days=3),
        )
        # days=0 -> clamped to 1: the 3-day-old mention drops out.
        tight = api.get(
            f"/api/clients/{client_id}/coverage/summary", params={"days": 0}
        ).json()
        assert tight == []
        wide = api.get(
            f"/api/clients/{client_id}/coverage/summary", params={"days": 999}
        ).json()
        assert len(wide) == 1 and wide[0]["events"] == 1

    def test_empty_client_returns_empty_list(self, api, db) -> None:
        client_id = first_client_id(db)
        body = api.get(f"/api/clients/{client_id}/coverage/summary").json()
        assert body == []
        assert api.get("/api/clients/999999/coverage/summary").status_code == 404


# ---------------------------------------------------------------- persons (F3)


def seed_person_mention(db, client_id: int, url: str, persons_data: list[dict], **kw) -> Mention:
    """Mention with a raw_enrichment payload, linked through the F3 hook."""
    from app import persons as persons_mod

    mention = seed_mention(db, client_id, url, sentiment=Sentiment.positive, **kw)
    mention.raw_enrichment = {
        "summary": "s",
        "sentiment": "positive",
        "sentiment_score": 0.9,
        "persons": persons_data,
        "topics": [],
    }
    persons_mod.persist_persons_from_enrichment(db, mention)
    db.commit()
    return mention


class TestPersonsAPI:
    def _seed_two(self, db, client_id: int) -> None:
        for i in range(3):
            seed_person_mention(
                db, client_id, f"https://a.com/{i}",
                [{"name": "Xóchitl Gálvez", "role": "Senadora", "org": "PAN",
                  "statement": "Dijo algo."}],
            )
        seed_person_mention(
            db, client_id, "https://b.com/1", [{"name": "Beto", "role": "Alcalde"}]
        )

    def test_list_empty_and_scoped(self, api, db) -> None:
        client_id = first_client_id(db)
        assert api.get(f"/api/clients/{client_id}/persons").json() == []
        assert api.get("/api/clients/999999/persons").status_code == 404

    def test_list_sorted_by_mentions_with_counts(self, api, db) -> None:
        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        body = api.get(f"/api/clients/{client_id}/persons").json()
        assert [p["name"] for p in body] == ["Xóchitl Gálvez", "Beto"]
        assert body[0]["mention_count"] == 3
        assert body[0]["role"] == "Senadora"

    def test_list_sort_recent_and_validation(self, api, db) -> None:
        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        body = api.get(f"/api/clients/{client_id}/persons", params={"sort": "recent"}).json()
        assert {p["name"] for p in body} == {"Xóchitl Gálvez", "Beto"}
        assert api.get(
            f"/api/clients/{client_id}/persons", params={"sort": "nope"}
        ).status_code == 422

    def test_list_q_filter(self, api, db) -> None:
        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        body = api.get(f"/api/clients/{client_id}/persons", params={"q": "xochitl gal"}).json()
        assert [p["name"] for p in body] == ["Xóchitl Gálvez"]

    def test_detail_timeline(self, api, db) -> None:
        from app.models import Person

        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        person = db.query(Person).filter_by(name_key="xochitl galvez").one()
        body = api.get(f"/api/clients/{client_id}/persons/{person.id}").json()
        assert body["name"] == "Xóchitl Gálvez"
        assert body["mention_count"] == 3
        assert len(body["timeline"]) == 3
        assert all(i["context"] == "Dijo algo." for i in body["timeline"])
        assert body["timeline"][0]["url"].startswith("https://a.com/")
        assert body["timeline"][0]["event_title"] is None
        assert body["timeline"][0]["political_label"] is None

    def test_detail_404_other_client_and_missing(self, api, db) -> None:
        from app.models import Person

        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        person = db.query(Person).first()
        other = Client(name="otro")
        db.add(other)
        db.commit()
        assert api.get(f"/api/clients/{other.id}/persons/{person.id}").status_code == 404
        assert api.get(f"/api/clients/{client_id}/persons/999999").status_code == 404
