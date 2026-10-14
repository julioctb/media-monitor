"""Persons (F3): models, dedupe, enrichment persistence, queries, backfill."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import (
    Client,
    Mention,
    MentionSource,
    Person,
    MentionPerson,
    queries,
)

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def _client(session) -> int:
    return queries.get_or_create_client(session, "acme").id


def _mention(session, client_id: int, n: int, **kwargs) -> Mention:
    mention = Mention(
        client_id=client_id,
        source=MentionSource.news_rss,
        url=f"https://example.com/{n}",
        url_hash=f"hash{n}",
        title=kwargs.pop("title", f"Nota {n}"),
        published_at=T0 + timedelta(minutes=n),
        **kwargs,
    )
    session.add(mention)
    session.flush()
    return mention


class TestPersonModels:
    def test_person_roundtrip_and_client_scope(self, session) -> None:
        client_id = _client(session)
        person = Person(
            client_id=client_id,
            name="Xóchitl Gálvez",
            name_key="xochitl galvez",
        )
        mention = _mention(session, client_id, 1)
        session.add(person)
        session.flush()
        link = MentionPerson(
            mention_id=mention.id,
            person_id=person.id,
            role="Senadora",
            org="PAN",
            context="Prometió reforzar la seguridad.",
        )
        session.add(person)
        session.add(link)
        session.commit()

        stored = session.scalar(select(Person).where(Person.id == person.id))
        assert stored.name == "Xóchitl Gálvez"
        assert stored.aliases == []
        assert stored.first_seen_at is not None
        assert stored.last_seen_at is not None
        assert stored.mention_links[0].context == "Prometió reforzar la seguridad."
        assert stored.mention_links[0].mention_id == mention.id

    def test_person_name_key_unique_per_client(self, session) -> None:
        from sqlalchemy.exc import IntegrityError

        client_id = _client(session)
        other = Client(name="beta")
        session.add(other)
        session.flush()
        session.add(Person(client_id=client_id, name="Ana", name_key="ana"))
        session.add(Person(client_id=other.id, name="Ana", name_key="ana"))
        session.commit()

        session.add(Person(client_id=client_id, name="Ana dup", name_key="ana"))
        with pytest.raises(IntegrityError):
            session.commit()

    def test_mention_person_unique_per_mention_and_person(self, session) -> None:
        from sqlalchemy.exc import IntegrityError

        client_id = _client(session)
        person = Person(client_id=client_id, name="Ana", name_key="ana")
        mention = _mention(session, client_id, 1)
        session.add(person)
        session.flush()
        session.add(MentionPerson(mention_id=mention.id, person_id=person.id))
        session.commit()
        session.add(MentionPerson(mention_id=mention.id, person_id=person.id))
        with pytest.raises(IntegrityError):
            session.commit()

    def test_stance_columns_nullable(self, session) -> None:
        client_id = _client(session)
        target = Person(client_id=client_id, name="Rectora", name_key="rectora")
        speaker = Person(client_id=client_id, name="Alcalde", name_key="alcalde")
        mention = _mention(session, client_id, 1)
        session.add_all([target, speaker])
        session.flush()
        link = MentionPerson(
            mention_id=mention.id,
            person_id=speaker.id,
            stance_target_id=target.id,
            stance_polarity=-1,
        )
        session.add(link)
        session.commit()
        assert link.stance_target_id == target.id
        assert link.stance_polarity == -1
