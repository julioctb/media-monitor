"""Backfill enrichment tests (F2c TE4): candidates, projection, apply."""

from app.enrich.llm import EnrichmentResult
from app.models import (
    Client,
    Mention,
    MentionPerson,
    MentionSource,
    Person,
    make_url_hash,
)
from app.models.base import Sentiment
from sqlalchemy import select, text


class TestBackfillEnrichment:
    """TE4: candidate selection, cost projection, apply path."""

    def test_candidate_ids_null_summary_and_force(self, session) -> None:
        from scripts.backfill_enrichment import candidate_ids

        client = Client(name="c")
        session.add(client)
        session.commit()

        def mk(summary, n):
            url = f"https://x.com/{n}"
            return Mention(
                client_id=client.id,
                source=MentionSource.news_rss,
                url=url,
                url_hash=make_url_hash(url),
                title=f"t{n}",
                summary=summary,
            )

        session.add_all([mk(None, 1), mk("s", 2), mk(None, 3)])
        session.commit()
        assert len(candidate_ids(session)) == 2
        forced = candidate_ids(session, force=True)
        assert len(forced) == 3
        assert candidate_ids(session, client_id=999) == []

    def test_projection_counts_tokens_without_llm_calls(self, session) -> None:
        from scripts.backfill_enrichment import (
            estimate_input_tokens,
            project_cost,
        )

        assert estimate_input_tokens("") > 0  # prompt overhead floor
        long = "palabra " * 400  # clipped at MAX_CONTENT_CHARS
        assert estimate_input_tokens(long) <= 1500 // 4 + 300

        client = Client(name="c")
        session.add(client)
        session.commit()
        url = "https://x.com/a"
        session.add(
            Mention(
                client_id=client.id,
                source=MentionSource.news_rss,
                url=url,
                url_hash=make_url_hash(url),
                title="titulo",
                content="texto",
            )
        )
        session.commit()
        stats = project_cost(session, [1], price_in=1.0, price_out=1.0)
        assert stats["mentions"] == 1
        assert stats["input_tokens"] > 0
        assert stats["output_tokens_est"] == 300
        assert stats["cost_usd_est"] == round(stats["input_tokens"] / 1e6, 4) + 300 / 1e6

    def test_backfill_applies_summary_and_overrides_stale_sentiment(self, session) -> None:
        """Canonical policy: enrichment sentiment replaces the stored value."""
        from scripts.backfill_enrichment import backfill

        client = Client(name="c")
        session.add(client)
        session.commit()
        url = "https://x.com/a"
        mention = Mention(
            client_id=client.id,
            source=MentionSource.news_rss,
            url=url,
            url_hash=make_url_hash(url),
            title="titulo",
            content="texto",
            sentiment=Sentiment.negative,
            sentiment_score=0.4,
        )
        session.add(mention)
        session.commit()

        calls = {"n": 0}

        class FakeEnricher:
            def enrich(self, text, lang="es"):
                calls["n"] += 1
                return EnrichmentResult(
                    summary="Resumen.",
                    sentiment=Sentiment.positive,
                    sentiment_score=0.9,
                    topics=["tema"],
                )

        stats = backfill(session, FakeEnricher())
        assert stats == {
            "enriched": 1,
            "failed": 0,
            "skipped_empty": 0,
            "canonical_overrides": 1,
            "persons_relinked": 1,
            "candidates": 1,
        }
        assert mention.summary == "Resumen."
        # Canonical: the enrichment verdict, not the stale stored value.
        assert mention.sentiment is Sentiment.positive
        assert mention.sentiment_score == 0.9
        rows = session.execute(
            text(
                "select classifier, label from mention_classifications"
                " where mention_id = 1"
            )
        ).all()
        assert ("topics", "tema") in rows

        # Idempotent: a forced re-run over agreeing values overrides nothing.
        stats = backfill(session, FakeEnricher(), force=True)
        assert stats["enriched"] == 1
        assert stats["canonical_overrides"] == 0
        assert calls["n"] == 2
        assert mention.sentiment is Sentiment.positive
        assert mention.sentiment_score == 0.9

    def test_backfill_counts_failures_and_skips_empty(self, session) -> None:
        from scripts.backfill_enrichment import backfill

        client = Client(name="c")
        session.add(client)
        session.commit()

        def mk(n, title, content):
            url = f"https://x.com/{n}"
            return Mention(
                client_id=client.id,
                source=MentionSource.news_rss,
                url=url,
                url_hash=make_url_hash(url),
                title=title,
                content=content,
            )

        session.add_all([mk(1, "t1", "texto"), mk(2, None, "   ")])
        session.commit()

        class Boom:
            def enrich(self, text, lang="es"):
                raise RuntimeError("down")

        stats = backfill(session, Boom())
        assert stats["failed"] == 1 and stats["enriched"] == 0
        assert stats["skipped_empty"] == 1

    def test_ids_file_pins_candidates_and_persists_raw_enrichment(
        self, session, tmp_path
    ) -> None:
        from scripts.backfill_enrichment import backfill, candidate_ids, load_ids_file

        client = Client(name="c")
        session.add(client)
        session.commit()

        def mk(n):
            url = f"https://x.com/{n}"
            return Mention(
                client_id=client.id,
                source=MentionSource.news_rss,
                url=url,
                url_hash=make_url_hash(url),
                title=f"t{n}",
                content="texto con entidad",
            )

        session.add_all([mk(1), mk(2), mk(3)])
        session.commit()

        ids_file = tmp_path / "ids.txt"
        ids_file.write_text("1\n\n# pinned by the content backfill\n3\n", encoding="utf-8")
        pinned = load_ids_file(str(ids_file))
        assert pinned == [1, 3]
        assert candidate_ids(session, force=True, ids=pinned) == [1, 3]
        # Without --force the pinned set still respects summary NULL.
        session.get(Mention, 1).summary = "ya"
        session.commit()
        assert candidate_ids(session, ids=pinned) == [3]

        class FakeEnricher:
            def enrich(self, text, lang="es"):
                return EnrichmentResult(
                    summary="Resumen.",
                    sentiment=Sentiment.positive,
                    sentiment_score=0.9,
                    persons=[{"name": "Ana Lopez", "stance": "neutral"}],
                )

        stats = backfill(session, FakeEnricher(), force=True, ids=pinned)
        assert stats["candidates"] == 2 and stats["enriched"] == 2
        rows = {m.id: m for m in session.query(Mention).all()}
        assert rows[2].summary is None  # not pinned -> untouched
        for mention_id in (1, 3):
            raw = rows[mention_id].raw_enrichment
            assert raw["summary"] == "Resumen."
            assert raw["persons"][0]["stance"] == "neutral"

    def test_relink_replaces_stale_person_links(self, session) -> None:
        from scripts.backfill_enrichment import backfill, candidate_ids

        client = Client(name="c")
        session.add(client)
        session.commit()
        url = "https://x.com/relink"
        mention = Mention(
            client_id=client.id,
            source=MentionSource.news_rss,
            url=url,
            url_hash=make_url_hash(url),
            title="titulo",
            content="texto",
        )
        old_person = Person(
            client_id=client.id, name="Viejo Incidental", name_key="viejo incidental"
        )
        session.add_all([mention, old_person])
        session.flush()
        session.add(
            MentionPerson(mention_id=mention.id, person_id=old_person.id)
        )
        session.commit()

        # --with-persons only candidates rows that already have a link.
        assert candidate_ids(session, force=True, with_persons=True) == [mention.id]

        class FakeEnricher:
            def enrich(self, text, lang="es"):
                return EnrichmentResult(
                    summary="Resumen.",
                    sentiment=Sentiment.neutral,
                    sentiment_score=0.5,
                    persons=[{"name": "Autoridad Central", "role": "Rectora"}],
                )

        stats = backfill(session, FakeEnricher(), force=True, with_persons=True)
        assert stats["persons_relinked"] == 1
        links = session.scalars(
            select(MentionPerson.person_id).where(
                MentionPerson.mention_id == mention.id
            )
        ).all()
        (person_id,) = links
        assert session.get(Person, person_id).name == "Autoridad Central"
        # The stale link did not survive the re-enrichment.
        assert old_person.id not in links
