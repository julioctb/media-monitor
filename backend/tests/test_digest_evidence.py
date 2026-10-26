"""Frozen publication inputs, exercised through offline facts and public builds."""

import copy
import json
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from app.models import Client, Event, Mention, MentionSource, make_url_hash
from app.summaries.builder import build_daily_summary, digest_prompt_view
from app.summaries.digest import build_digest_facts

DAY = date(2026, 10, 17)
NOON = datetime(2026, 10, 17, 18, tzinfo=UTC)


def client(session, name="Catalogue client"):
    row = Client(name=name)
    session.add(row)
    session.flush()
    return row


def publication(session, client_id, suffix, **fields):
    url = fields.pop("url", f"https://www.Medio.test/{suffix}")
    row = Mention(
        client_id=client_id,
        url=url,
        url_hash=make_url_hash(url),
        source=fields.pop("source", MentionSource.news_rss),
        published_at=fields.pop("published_at", NOON),
        title=fields.pop("title", f"Publicación institucional {suffix}"),
        **fields,
    )
    session.add(row)
    session.flush()
    return row


def facts_for(session, owner, **kwargs):
    return build_digest_facts(session, client_id=owner.id, day=DAY, tz="UTC", **kwargs)


def test_facts_freeze_exact_same_window_catalogue_and_story_membership(session):
    owner = client(session)
    event = Event(
        client_id=owner.id,
        title="Título global ajeno",
        title_tokens="global",
        first_seen_at=NOON,
        last_seen_at=NOON,
    )
    session.add(event)
    session.flush()
    loose = publication(session, owner.id, "loose", title="Nota suelta")
    article = publication(
        session,
        owner.id,
        "article",
        event_id=event.id,
        title="  Consulta aplazada · Ver más · Comentar ",
        author="Reportera A",
        summary="  " + "S" * 305 + "  ",
        content="  " + "E" * 305 + "  ",
        published_at=NOON,
    )
    showcase = publication(
        session,
        owner.id,
        "showcase",
        event_id=event.id,
        title="Esta es la PORTADA de @Diario: consulta y presupuesto",
        source=MentionSource.facebook_page,
    )
    cosmetic = publication(
        session,
        owner.id,
        "cosmetic",
        title="Actualizó su foto de perfil",
        source=MentionSource.facebook_page,
    )
    other = client(session, "Other client")
    publication(session, other.id, "foreign", title="Material de otro cliente")
    publication(session, owner.id, "old", published_at=NOON - timedelta(days=2))
    session.commit()
    session.expire_all()  # Actual SQLite naive-UTC roundtrip.

    facts = facts_for(session, owner)

    sources = facts["evidence"]["sources"]
    assert facts["evidence"]["version"] == 1
    assert [s["mention_id"] for s in sources] == [
        loose.id,
        article.id,
        showcase.id,
        cosmetic.id,
    ]
    assert [s["index"] for s in sources] == [0, 1, 2, 3]
    assert sources[1] == {
        "index": 1,
        "mention_id": article.id,
        "source": "news_rss",
        "url": article.url,
        "outlet": "medio.test",
        "author": "Reportera A",
        "title": "Consulta aplazada",
        "published_at": "2026-10-17T18:00:00+00:00",
        "summary": "S" * 300,
        "excerpt": "E" * 300,
    }
    assert sources[0]["summary"] is None
    assert sources[0]["excerpt"] is None
    assert facts["coverage"]["total"] == len(sources) == 4
    story = next(n for n in facts["noticias"] if n["event_id"] == event.id)
    assert story["source_refs"] == [1]  # Showcase is coverage, not membership.
    assert story["material_ref"] == 1
    assert [s["url"] for s in story["sources"]] == [article.url, showcase.url]
    assert next(n for n in facts["noticias"] if n["title"] == "Nota suelta")[
        "source_refs"
    ] == [0]


def test_injected_selected_rows_keep_empty_material_explicit_and_utc(session):
    owner = client(session)
    empty = publication(
        session,
        owner.id,
        "empty",
        title="   ",
        author=" ",
        summary=" ",
        content="",
        published_at=None,
    )
    aware = publication(
        session,
        owner.id,
        "aware",
        published_at=NOON.astimezone(timezone(timedelta(hours=-6))),
    )
    facts = facts_for(session, owner, mentions=[aware, empty])
    assert facts["evidence"]["sources"][0] == {
        "index": 0,
        "mention_id": empty.id,
        "source": "news_rss",
        "url": empty.url,
        "outlet": "medio.test",
        "author": None,
        "title": None,
        "published_at": None,
        "summary": None,
        "excerpt": None,
    }
    assert facts["evidence"]["sources"][1]["published_at"] == (
        "2026-10-17T18:00:00+00:00"
    )


def test_injected_facts_do_not_requery_publications(session):
    from sqlalchemy import event

    owner = client(session)
    article = publication(session, owner.id, "selected")
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(session.bind, "before_cursor_execute", capture)
    try:
        facts = facts_for(session, owner, mentions=[article])
    finally:
        event.remove(session.bind, "before_cursor_execute", capture)
    assert facts["evidence"]["sources"][0]["mention_id"] == article.id
    assert not any("FROM mentions" in statement for statement in statements)
