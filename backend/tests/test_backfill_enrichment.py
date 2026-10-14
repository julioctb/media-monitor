"""Backfill enrichment tests (F2c TE4): candidates, projection, apply."""

from sqlalchemy import text

from app.enrich.llm import EnrichmentResult
from app.models import Client, Mention, MentionSource, make_url_hash
from app.models.base import Sentiment

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

    def test_backfill_applies_summary_and_keeps_laya_sentiment(self, session) -> None:
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

        class FakeEnricher:
            def enrich(self, text, lang="es"):
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
            "candidates": 1,
        }
        assert mention.summary == "Resumen."
        # Existing laya sentiment survives: the TE5 comparison signal.
        assert mention.sentiment is Sentiment.negative
        rows = session.execute(
            text(
                "select classifier, label from mention_classifications"
                " where mention_id = 1"
            )
        ).all()
        assert ("topics", "tema") in rows

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
