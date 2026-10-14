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
from app.ingest.matching import fold_text
from app.ingest.pipeline import persist_raw_mentions
from app.models import Keyword
from app.models.base import Sentiment
from app import persons

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


def _client_with_keywords(session) -> tuple[Client, list[Keyword]]:
    from app.models import Keyword

    client = queries.get_or_create_client(session, "test")
    kws = [Keyword(client_id=client.id, text="BUAP", language="es")]
    session.add_all(kws)
    session.commit()
    return client, kws


def _raw(url: str) -> "RawMention":
    from app.ingest.base import RawMention

    return RawMention(
        source=MentionSource.news_rss,
        keyword="BUAP",
        url=url,
        title="BUAP noticia",
        lang="es",
        published_at=T0,
    )


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


# ------------------------------------------------------- resolve + persistence


class TestResolvePerson:
    def test_creates_with_folded_name_key(self, session) -> None:
        client_id = _client(session)
        person = persons.resolve_person(session, client_id=client_id, name="Xóchitl Gálvez")
        session.commit()
        assert person.name_key == "xochitl galvez"
        assert person.name == "Xóchitl Gálvez"
        assert person.aliases == []

    def test_reuses_across_case_and_accents(self, session) -> None:
        client_id = _client(session)
        first = persons.resolve_person(session, client_id=client_id, name="Xóchitl Gálvez")
        again = persons.resolve_person(session, client_id=client_id, name="XOCHITL GALVEZ")
        session.commit()
        assert again.id == first.id
        assert session.query(Person).count() == 1

    def test_alias_variant_recorded(self, session) -> None:
        client_id = _client(session)
        first = persons.resolve_person(session, client_id=client_id, name="Xóchitl Gálvez")
        persons.resolve_person(session, client_id=client_id, name="Xochitl")
        session.commit()
        assert first.aliases == ["Xochitl"]
        assert "xochitl" in first.alias_keys.split()
        # alias lookup resolves to the same row
        again = persons.resolve_person(session, client_id=client_id, name="XOCHITL")
        assert again.id == first.id

    def test_scoped_per_client(self, session) -> None:
        client_id = _client(session)
        other = Client(name="beta")
        session.add(other)
        session.commit()
        a = persons.resolve_person(session, client_id=client_id, name="Ana")
        b = persons.resolve_person(session, client_id=other.id, name="Ana")
        session.commit()
        assert a.id != b.id

    def test_touches_last_seen_and_fills_role_once(self, session) -> None:
        client_id = _client(session)
        now = datetime.now(tz=timezone.utc)
        first = persons.resolve_person(
            session, client_id=client_id, name="Ana", role="Rectora", org="BUAP", now=now
        )
        later = now + timedelta(hours=1)
        again = persons.resolve_person(
            session, client_id=client_id, name="Ana", role="Ex rectora", now=later
        )
        session.commit()
        assert again.id == first.id
        assert again.last_seen_at == later
        # fill-if-empty: once set, a role stays.
        assert again.role == "Rectora"
        assert again.org == "BUAP"

    def test_canonical_name_grows_to_longest_variant(self, session) -> None:
        client_id = _client(session)
        first = persons.resolve_person(session, client_id=client_id, name="Peña")
        longer = persons.resolve_person(session, client_id=client_id, name="Peña Nieto")
        session.commit()
        assert longer.id == first.id
        assert first.name == "Peña Nieto"


def _enrichment(persons_data: list[dict]) -> dict:
    return {
        "summary": "Resumen.",
        "sentiment": "positive",
        "sentiment_score": 0.8,
        "persons": persons_data,
        "topics": [],
    }


class TestPersistPersonsFromEnrichment:
    def test_links_persons_from_raw_enrichment(self, session) -> None:
        client_id = _client(session)
        mention = _mention(
            session,
            client_id,
            1,
            raw_enrichment=_enrichment(
                [
                    {"name": "Juan Pérez", "role": "rector", "org": "BUAP",
                     "statement": "Dijo algo.", "stance": "favorable"},
                    {"name": "María López"},
                ]
            ),
        )
        created = persons.persist_persons_from_enrichment(session, mention)
        session.commit()
        assert created == 2
        links = sorted(mention.person_links, key=lambda l: l.person.name)
        assert links[0].person.name == "Juan Pérez"
        assert links[0].role == "rector"
        assert links[0].context == "Dijo algo."
        assert links[1].person.name == "María López"
        assert links[1].context is None

    def test_idempotent_relink(self, session) -> None:
        client_id = _client(session)
        mention = _mention(
            session, client_id, 1, raw_enrichment=_enrichment([{"name": "Juan"}])
        )
        assert persons.persist_persons_from_enrichment(session, mention) == 1
        assert persons.persist_persons_from_enrichment(session, mention) == 0
        session.commit()
        assert len(mention.person_links) == 1

    def test_caps_at_five_persons(self, session) -> None:
        client_id = _client(session)
        many = [{"name": f"Persona {i}"} for i in range(8)]
        mention = _mention(session, client_id, 1, raw_enrichment=_enrichment(many))
        created = persons.persist_persons_from_enrichment(session, mention)
        session.commit()
        assert created == persons.PERSONS_PER_MENTION == 5

    def test_skips_nameless_and_handles_missing_payload(self, session) -> None:
        client_id = _client(session)
        mention = _mention(
            session,
            client_id,
            1,
            raw_enrichment=_enrichment([{"name": ""}, {"role": "sin nombre"}]),
        )
        assert persons.persist_persons_from_enrichment(session, mention) == 0
        bare = _mention(session, client_id, 2)
        assert persons.persist_persons_from_enrichment(session, bare) == 0
        assert session.query(MentionPerson).count() == 0

    def test_dedupe_across_mentions_and_mentions_counter(self, session) -> None:
        client_id = _client(session)
        m1 = _mention(session, client_id, 1, raw_enrichment=_enrichment([{"name": "Juan Pérez"}]))
        m2 = _mention(session, client_id, 2, raw_enrichment=_enrichment([{"name": "Juan Perez"}]))
        persons.persist_persons_from_enrichment(session, m1)
        persons.persist_persons_from_enrichment(session, m2)
        session.commit()
        (person,) = session.query(Person).all()
        assert len(person.mention_links) == 2


# ----------------------------------------------------------------- queries


class TestListPersons:
    def _seed(self, session) -> tuple[int, dict[str, Person]]:
        client_id = _client(session)
        data = [
            ("Ana Torres", "Governadora", 3),
            ("Beto Ibarra", "Alcalde", 1),
        ]
        people: dict[str, Person] = {}
        n = 0
        for name, role, n_mentions in data:
            for _ in range(n_mentions):
                n += 1
                m = _mention(
                    session, client_id, n,
                    raw_enrichment=_enrichment([{"name": name, "role": role}]),
                )
                persons.persist_persons_from_enrichment(session, m)
            people[name] = session.scalar(
                select(Person).where(
                    Person.client_id == client_id,
                    Person.name_key == fold_text(name),
                )
            )
        session.commit()
        return client_id, people

    def test_sort_by_mentions_desc(self, session) -> None:
        client_id, people = self._seed(session)
        rows = queries.list_persons(session, client_id, sort="mentions")
        counts = {row["name"]: row["mention_count"] for row in rows}
        assert counts == {"Ana Torres": 3, "Beto Ibarra": 1}
        assert rows[0]["name"] == "Ana Torres"

    def test_sort_by_recent(self, session) -> None:
        client_id, _ = self._seed(session)
        beto = session.scalar(select(Person).where(Person.name_key == "beto ibarra"))
        beto.last_seen_at = datetime.now(tz=timezone.utc) + timedelta(hours=2)
        session.commit()
        rows = queries.list_persons(session, client_id, sort="recent")
        assert rows[0]["name"] == "Beto Ibarra"

    def test_q_filter_folded_and_aliases(self, session) -> None:
        client_id, _ = self._seed(session)
        # folded substring of the canonical name
        rows = queries.list_persons(session, client_id, q="ana tor")
        assert [r["name"] for r in rows] == ["Ana Torres"]
        # alias key: "beto" resolves via alias_keys after a variant link
        m = _mention(session, client_id, 99, raw_enrichment=_enrichment([{"name": "Beto"}]))
        persons.persist_persons_from_enrichment(session, m)
        session.commit()
        rows = queries.list_persons(session, client_id, q="beto")
        assert [r["name"] for r in rows] == ["Beto Ibarra"]

    def test_scoped_to_client(self, session) -> None:
        client_id, _ = self._seed(session)
        other = Client(name="beta")
        session.add(other)
        session.commit()
        assert queries.list_persons(session, other.id) == []

    def test_invalid_sort_raises(self, session) -> None:
        client_id = _client(session)
        with pytest.raises(ValueError):
            queries.list_persons(session, client_id, sort="nope")


class TestPersonTimeline:
    def test_rows_carry_quote_event_and_political_label(self, session) -> None:
        from app.models import Event

        client_id = _client(session)
        event = Event(
            client_id=client_id,
            title="Evento canónico",
            title_tokens="evento canonico",
            mention_count=1,
            source_count=1,
            first_seen_at=T0,
            last_seen_at=T0,
        )
        session.add(event)
        session.flush()
        m1 = _mention(
            session, client_id, 1, event_id=event.id,
            raw_enrichment=_enrichment(
                [{"name": "Ana Torres", "role": "Governadora",
                  "statement": "Voy por todo."}]
            ),
        )
        m2 = _mention(
            session, client_id, 2,
            raw_enrichment=_enrichment([{"name": "ana torres"}]),
        )
        persons.persist_persons_from_enrichment(session, m1)
        persons.persist_persons_from_enrichment(session, m2)
        queries.upsert_classification(
            session, mention_id=m1.id, classifier="political", label="MORENA", score=0.9
        )
        session.commit()
        person = session.query(Person).one()

        rows = queries.person_timeline(session, person_id=person.id, client_id=client_id)
        assert len(rows) == 2
        newest, oldest = rows
        # m2 published later → first
        assert newest["mention_id"] == m2.id
        assert newest["political_label"] is None
        assert oldest["mention_id"] == m1.id
        assert oldest["context"] == "Voy por todo."
        assert oldest["event_title"] == "Evento canónico"
        assert oldest["political_label"] == "MORENA"
        assert oldest["url"] == m1.url

    def test_scoped_and_404ish_empty(self, session) -> None:
        client_id = _client(session)
        m = _mention(session, client_id, 1, raw_enrichment=_enrichment([{"name": "Ana"}]))
        persons.persist_persons_from_enrichment(session, m)
        session.commit()
        (person,) = session.query(Person).all()
        other = Client(name="beta")
        session.add(other)
        session.commit()
        assert queries.person_timeline(
            session, person_id=person.id, client_id=other.id
        ) == []

    def test_respects_limit(self, session) -> None:
        client_id = _client(session)
        for i in range(4):
            m = _mention(session, client_id, i + 1, raw_enrichment=_enrichment([{"name": "Ana"}]))
            persons.persist_persons_from_enrichment(session, m)
        session.commit()
        (person,) = session.query(Person).all()
        assert len(queries.person_timeline(
            session, person_id=person.id, client_id=client_id, limit=2
        )) == 2


# ----------------------------------------------------------------- backfill


class TestBackfillPersons:
    def test_dry_run_counts_without_writes(self, session) -> None:
        from scripts.backfill_persons import backfill_persons

        client_id = _client(session)
        _mention(session, client_id, 1, raw_enrichment=_enrichment([{"name": "Ana"}]))
        _mention(session, client_id, 2)  # no enrichment: not a candidate
        session.commit()

        stats = backfill_persons(session, client_id=client_id, apply=False)
        assert stats["candidates"] == 1
        assert stats["distinct_names"] == 1
        assert session.query(Person).count() == 0
        assert session.query(MentionPerson).count() == 0

    def test_apply_populates_and_is_idempotent(self, session) -> None:
        from scripts.backfill_persons import backfill_persons

        client_id = _client(session)
        _mention(session, client_id, 1, raw_enrichment=_enrichment(
            [{"name": "Ana Torres"}, {"name": "Beto"}]
        ))
        _mention(session, client_id, 2, raw_enrichment=_enrichment([{"name": "ana torres"}]))
        _mention(session, client_id, 3, raw_enrichment=_enrichment([]))
        session.commit()

        first = backfill_persons(session, client_id=client_id, apply=True)
        assert first["links_created"] == 3
        assert first["persons_created"] == 2
        # Re-run: everything already linked, nothing new.
        second = backfill_persons(session, client_id=client_id, apply=True)
        assert second["links_created"] == 0
        assert second["persons_created"] == 0
        assert session.query(Person).count() == 2

    def test_scoped_to_client(self, session) -> None:
        from scripts.backfill_persons import backfill_persons

        client_id = _client(session)
        other = Client(name="beta")
        session.add(other)
        session.commit()
        _mention(session, other.id, 1, raw_enrichment=_enrichment([{"name": "Ana"}]))
        session.commit()
        stats = backfill_persons(session, client_id=client_id, apply=True)
        assert stats["candidates"] == 0


class TestPipelinePersonsHook:
    def test_persist_raw_mentions_persists_persons(self, session) -> None:
        from app.enrich.llm import EnrichmentResult

        class FakeEnricher:
            def enrich(self, text: str, lang: str = "es") -> EnrichmentResult:
                return EnrichmentResult(
                    summary="Resumen.",
                    sentiment=Sentiment.positive,
                    sentiment_score=0.9,
                    persons=[{"name": "Juan Pérez", "role": "rector"}],
                    topics=["tema"],
                )

        client, kws = _client_with_keywords(session)
        inserted = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[_raw("https://example.com/p1")],
            keyword_by_text={"buap": kws[0]},
            all_keyword_texts=["BUAP"],
            enricher=FakeEnricher(),
        )
        assert inserted == 1
        (mention,) = session.query(Mention).all()
        assert [link.person.name for link in mention.person_links] == ["Juan Pérez"]
        assert mention.person_links[0].person.name_key == "juan perez"

    def test_enrichment_failure_still_ingests_without_persons(self, session) -> None:
        class BoomEnricher:
            def enrich(self, text: str, lang: str = "es") -> None:
                raise RuntimeError("llm down")

        client, kws = _client_with_keywords(session)
        inserted = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[_raw("https://example.com/p2")],
            keyword_by_text={"buap": kws[0]},
            all_keyword_texts=["BUAP"],
            enricher=BoomEnricher(),
        )
        assert inserted == 1
        assert session.query(MentionPerson).count() == 0
