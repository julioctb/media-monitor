"""Full-result Feed metrics through public requests and independent fixture facts."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import product

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_client_id
from app.db import get_db
from app.main import create_app
from app.models import (
    Base,
    Client,
    Event,
    Keyword,
    Mention,
    MentionPerson,
    MentionSource,
    Person,
    Sentiment,
    make_url_hash,
)
from app.models.classification import MentionClassification

START = datetime(2026, 10, 14, 6, tzinfo=timezone.utc)
END = START + timedelta(days=1) - timedelta(seconds=1)


def seed_feed(session):
    """Synthetic fixture is reusable by an isolated runtime, without test imports."""
    clients = [
        Client(name="Synthetic feed tenant one"),
        Client(name="Synthetic feed tenant two"),
    ]
    session.add_all(clients)
    session.flush()
    keywords = [
        Keyword(client_id=clients[0].id, text=t, language="es", created_at=START)
        for t in ["budget", "meeting"]
    ]
    session.add_all(keywords)
    events = [
        Event(
            id=i,
            client_id=clients[0].id,
            title=f"Synthetic event {i}",
            title_tokens=f"event {i}",
            first_seen_at=START,
            last_seen_at=END,
        )
        for i in range(1, 10)
    ]
    session.add_all(events)
    session.flush()
    rows = []
    sources = [
        MentionSource.news_rss,
        MentionSource.gdelt,
        MentionSource.x_twitter,
        MentionSource.field_report,
    ]
    tones = [Sentiment.negative, Sentiment.neutral, Sentiment.positive, None]
    for i in range(96):
        source = sources[i % 4]
        tone = tones[(i // 4) % 4]
        host = [
            "alpha.example",
            "www.alpha.example",
            "alpha.example.mx",
            "beta.example",
        ][(i // 3) % 4]
        published = [
            START,
            END,
            END + timedelta(microseconds=1),
            START - timedelta(microseconds=1),
            None,
            START + timedelta(hours=12),
        ][(i // 5) % 6]
        url = f"https://{host}/item/{i}"
        outlet = host.removeprefix("www.")
        author = None
        # Legacy identity includes field hosts, author fallback, unknown and relays.
        if i in [4, 5]:
            url, author, outlet = (
                f"legacy:{i}",
                "  Synthetic author  ",
                "Synthetic author",
            )
        if i == 6:
            url, outlet = "legacy:unknown", "unknown"
        if i == 7:
            url, outlet = "https://news.google.com/item/7", "news.google.com"
        # Mention 1 is loose, colliding numerically with event 1 on other rows.
        event_id = 9 if i == 95 else (None if i % 5 == 0 else 1 + i % 8)
        title = f"{'Budget' if i % 3 else 'Meeting'} synthetic publication {i}"
        content = "documented allocation" if i % 5 else "other text"
        keyword_id = keywords[i % 2].id
        mention = Mention(
            client_id=clients[0].id,
            source=source,
            url=url,
            url_hash=make_url_hash(url),
            title=title,
            content=content,
            author=author,
            sentiment=tone,
            keyword_id=keyword_id,
            published_at=published,
            ingested_at=START,
            event_id=event_id,
        )
        session.add(mention)
        session.flush()
        classified = i % 2 == 0
        if classified:
            session.add_all(
                [
                    MentionClassification(
                        mention_id=mention.id,
                        classifier="political",
                        label="political",
                        score=0.9,
                    ),
                    MentionClassification(
                        mention_id=mention.id,
                        classifier="topic",
                        label="budget",
                        score=0.8,
                    ),
                ]
            )
        rows.append(
            dict(
                id=mention.id,
                source=source.value,
                sentiment=tone.value if tone else None,
                keyword_id=keyword_id,
                title=title,
                content=content,
                outlet=outlet,
                host=outlet if url.startswith("https://") else None,
                published=published,
                classified=classified,
                event_id=event_id,
                url=url,
                author=author,
            )
        )
    session.add(
        Mention(
            client_id=clients[1].id,
            source=MentionSource.news_rss,
            url="https://foreign.example/item",
            url_hash=make_url_hash("https://foreign.example/item"),
            title="Budget foreign publication",
            content="documented allocation",
            sentiment=Sentiment.negative,
            published_at=START,
            ingested_at=START,
        )
    )
    person = Person(
        client_id=clients[0].id,
        name="Synthetic observer",
        name_key="synthetic observer",
        first_seen_at=START,
        last_seen_at=START,
    )
    session.add(person)
    session.flush()
    session.add(
        MentionPerson(
            mention_id=rows[0]["id"],
            person_id=person.id,
            context="Synthetic recorded occurrence",
        )
    )
    session.commit()
    return clients, keywords, rows


def expected_metrics(rows):
    sources = {s.value: 0 for s in MentionSource}
    sources.update(Counter(r["source"] for r in rows))
    tones = {s.value: 0 for s in Sentiment} | {"none": 0}
    tones.update(Counter(r["sentiment"] or "none" for r in rows))
    return dict(
        total=len(rows),
        by_source=sources,
        by_sentiment=tones,
        news_medium_count=len(
            {
                r["outlet"]
                for r in rows
                if r["source"] not in {"x_twitter", "facebook_page"}
            }
        ),
        result_group_count=len(
            {
                ("event", r["event_id"])
                if r["event_id"] is not None
                else ("mention", r["id"])
                for r in rows
            }
        ),
    )


@pytest.fixture()
def feed():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        clients, keywords, rows = seed_feed(session)
        app = create_app()
        app.dependency_overrides[get_db] = lambda: session
        app.dependency_overrides[get_client_id] = lambda: clients[0].id
        with TestClient(app) as api:
            yield api, session, clients, keywords, rows
    engine.dispose()


def test_metrics_cover_full_tenant_result_not_page_or_event_rows(feed):
    api, _, _, _, rows = feed
    response = api.get("/api/stats/feed")
    assert response.status_code == 200, response.text
    assert response.json() == expected_metrics(rows)
    full = api.get("/api/mentions", params={"limit": 500}).json()
    assert {r["id"] for r in full["items"]} == {r["id"] for r in rows}
    assert full["total"] == response.json()["total"] == 96
    assert response.json()["result_group_count"] == 28
    assert len(api.get("/api/mentions").json()["items"]) == 50


def test_source_union_uses_distinct_sets_and_intersects_explicit_source(feed):
    api, _, _, _, rows = feed
    for sources, source in [
        (["news_rss", "gdelt"], None),
        (["news_rss", "gdelt", "news_rss"], None),
        (["news_rss", "gdelt"], "news_rss"),
        (["news_rss"], "gdelt"),
        ([], None),
    ]:
        params = [("sources", s) for s in sources]
        if source:
            params.append(("source", source))
        expected = [
            r
            for r in rows
            if (not sources or r["source"] in sources)
            and (source is None or r["source"] == source)
        ]
        response = api.get("/api/stats/feed", params=params)
        assert response.status_code == 200, response.text
        assert response.json() == expected_metrics(expected)
        ids = set()
        for tag in set(sources) if sources else {r["source"] for r in rows}:
            page = api.get("/api/mentions", params={"source": tag, "limit": 500}).json()
            if source is None or tag == source:
                ids.update(r["id"] for r in page["items"])
        assert ids == {r["id"] for r in expected}


def test_tones_include_null_only_and_never_self_exclude(feed):
    api, _, _, _, rows = feed
    for tone in ["negative", "neutral", "positive", "none"]:
        expected = [r for r in rows if (r["sentiment"] or "none") == tone]
        response = api.get("/api/stats/feed", params={"sentiment": tone})
        assert response.status_code == 200
        assert response.json() == expected_metrics(expected)
        full = api.get("/api/mentions", params={"sentiment": tone, "limit": 500}).json()
        assert {r["id"] for r in full["items"]} == {r["id"] for r in expected}
        assert response.json()["by_sentiment"][tone] == full["total"]


@pytest.mark.parametrize(
    "params",
    [
        {"source": "invalid"},
        {"sources": "invalid"},
        {"sources": ""},
        {"sentiment": "uncertain"},
        {"sentiment": "null"},
        {"since": "invalid"},
        {"until": "invalid"},
        {"since": "2026-02-30"},
        {"keyword_id": "no"},
        {"medium": "x" * 201},
    ],
)
def test_strict_public_422_validation(feed, params):
    response = feed[0].get("/api/stats/feed", params=params)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_empty_reversed_and_boundary_results_are_measured_zero_safe(feed):
    api, _, _, _, rows = feed
    for params in [
        {"q": "absent text"},
        {"keyword_id": 0},
        {"since": END.isoformat(), "until": START.isoformat()},
    ]:
        assert api.get("/api/stats/feed", params=params).json() == expected_metrics([])
        assert api.get("/api/mentions", params=params).json() == {
            "items": [],
            "total": 0,
        }
    for since, until in [
        (START, START),
        (END, END),
        (START - timedelta(microseconds=1), START),
        (END, END + timedelta(microseconds=1)),
    ]:
        params = {"since": since.isoformat(), "until": until.isoformat()}
        expected = [
            r
            for r in rows
            if r["published"] is not None and since <= r["published"] <= until
        ]
        assert api.get("/api/stats/feed", params=params).json() == expected_metrics(
            expected
        )
        assert {
            r["id"]
            for r in api.get("/api/mentions", params={**params, "limit": 500}).json()[
                "items"
            ]
        } == {r["id"] for r in expected}


def test_legacy_outlet_units_and_classification_exists_do_not_multiply(feed):
    api, session, _, _, rows = feed
    for params, expected in [
        (
            {"source": "field_report"},
            [r for r in rows if r["source"] == "field_report"],
        ),
        ({"q": "legacy"}, []),
        (
            {"q": "documented"},
            [r for r in rows if r["content"] == "documented allocation"],
        ),
        ({"q": "Bud%et"}, [r for r in rows if "Budget" in r["title"]]),
        ({"classifier": "political"}, [r for r in rows if r["classified"]]),
        ({"label": "budget"}, [r for r in rows if r["classified"]]),
        (
            {"medium": "alpha.example.mx"},
            [r for r in rows if r["outlet"] == "alpha.example.mx"],
        ),
        ({"q": "  "}, rows),
    ]:
        response = api.get("/api/stats/feed", params=params)
        assert response.status_code == 200, response.text
        assert response.json() == expected_metrics(expected)
        full = api.get("/api/mentions", params={**params, "limit": 500}).json()
        assert {r["id"] for r in full["items"]} == {r["id"] for r in expected}
    # Two different classifiers share the label: a multiplying join would double rows.
    for row in rows[:3]:
        session.add(
            MentionClassification(
                mention_id=row["id"], classifier="other", label="political", score=0.9
            )
        )
    session.commit()
    expected = [
        r for r in rows if r["classified"] or r["id"] in {r["id"] for r in rows[:3]}
    ]
    assert api.get(
        "/api/stats/feed", params={"label": "political"}
    ).json() == expected_metrics(expected)


def test_client_dependency_is_authoritative_not_request_override(feed):
    api, _, clients, _, rows = feed
    assert api.get(
        "/api/stats/feed", params={"client_id": clients[1].id}
    ).json() == expected_metrics(rows)
    api.app.dependency_overrides[get_client_id] = lambda: clients[1].id
    response = api.get("/api/stats/feed").json()
    assert (
        response["total"]
        == response["news_medium_count"]
        == response["result_group_count"]
        == 1
    )
    assert response["by_sentiment"]["negative"] == 1
    assert (
        api.get("/api/mentions").json()["items"][0]["title"]
        == "Budget foreign publication"
    )


def test_scalar_projection_executes_one_query_without_hydrating_relationships(feed):
    from sqlalchemy import event

    api, session, _, _, _ = feed
    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(session.bind, "before_cursor_execute", record)
    try:
        response = api.get("/api/stats/feed", params={"classifier": "political"})
        assert response.status_code == 200
        assert len(statements) == 1
        assert "EXISTS" in statements[0]
    finally:
        event.remove(session.bind, "before_cursor_execute", record)


def test_all_scalar_filter_combinations_match_complete_public_list(feed):
    api, _, _, keywords, rows = feed
    for source, tone, keyword, text, since, until, political, medium in product(
        [False, True], repeat=8
    ):
        params = {}
        if source:
            params["source"] = "news_rss"
        if tone:
            params["sentiment"] = "negative"
        if keyword:
            params["keyword_id"] = keywords[0].id
        if text:
            params["q"] = "budget"
        if since:
            params["since"] = START.isoformat()
        if until:
            params["until"] = END.isoformat()
        if political:
            params.update(classifier="political", label="political")
        if medium:
            params["medium"] = "WWW.ALPHA.EXAMPLE"
        expected = [
            r
            for r in rows
            if (not source or r["source"] == "news_rss")
            and (not tone or r["sentiment"] == "negative")
            and (not keyword or r["keyword_id"] == keywords[0].id)
            and (not text or "budget" in (r["title"] + r["content"]).lower())
            and (not since or r["published"] is not None and r["published"] >= START)
            and (not until or r["published"] is not None and r["published"] <= END)
            and (not political or r["classified"])
            and (not medium or r["host"] == "alpha.example")
        ]
        response = api.get("/api/stats/feed", params=params)
        assert response.status_code == 200, response.text
        assert response.json() == expected_metrics(expected), params
        full = api.get("/api/mentions", params={**params, "limit": 500}).json()
        assert full["total"] == len(expected)
        assert {r["id"] for r in full["items"]} == {r["id"] for r in expected}
        for limit, offset in [(1, 0), (7, 7), (50, 50)]:
            page = api.get(
                "/api/mentions", params={**params, "limit": limit, "offset": offset}
            )
            assert page.status_code == 200
            assert page.json()["total"] == len(expected)
            assert len(page.json()["items"]) == min(
                limit, max(0, len(expected) - offset)
            )
            assert {r["id"] for r in page.json()["items"]} <= {
                r["id"] for r in expected
            }
            assert (
                api.get(
                    "/api/stats/feed",
                    params={
                        **params,
                        "limit": limit,
                        "offset": offset,
                        "sort": "ignored",
                    },
                ).json()
                == response.json()
            )
