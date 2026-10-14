"""align_sentiment: idempotent canonical re-alignment from raw_enrichment."""

from app.models import Client, Mention, MentionSource, make_url_hash
from app.models.base import Sentiment
from scripts.align_sentiment import align_sentiment


def _mention(client_id: int, n: int, **kwargs) -> Mention:
    url = f"https://x.com/{n}"
    return Mention(
        client_id=client_id,
        source=MentionSource.news_rss,
        url=url,
        url_hash=make_url_hash(url),
        title=f"t{n}",
        content="texto",
        **kwargs,
    )


class TestAlignSentiment:
    def test_repairs_stale_value_from_raw_enrichment(self, session) -> None:
        client = Client(name="c")
        session.add(client)
        session.commit()
        mention = _mention(
            client.id,
            1,
            sentiment=Sentiment.negative,  # stale laya verdict
            sentiment_score=0.4,
        )
        mention.raw_enrichment = {"sentiment": "positive", "sentiment_score": 0.8}
        session.add(mention)
        session.commit()

        stats = align_sentiment(session, apply=True)
        assert stats["aligned"] == 1
        assert mention.sentiment is Sentiment.positive
        assert mention.sentiment_score == 0.8

        # Idempotent: the second pass finds nothing to fix.
        session.expire_all()
        stats = align_sentiment(session, apply=True)
        assert stats["aligned"] == 0
        (m,) = session.query(Mention).all()
        assert m.sentiment is Sentiment.positive
        assert m.sentiment_score == 0.8

    def test_dry_run_reports_without_writing(self, session) -> None:
        client = Client(name="c")
        session.add(client)
        session.commit()
        mention = _mention(
            client.id,
            1,
            sentiment=Sentiment.negative,
            sentiment_score=0.4,
        )
        mention.raw_enrichment = {"sentiment": "positive", "sentiment_score": 0.8}
        session.add(mention)
        session.commit()

        stats = align_sentiment(session, apply=False)
        assert stats["would_align"] == 1
        assert stats["aligned"] == 0
        session.expire_all()
        (m,) = session.query(Mention).all()
        assert m.sentiment is Sentiment.negative  # untouched

    def test_skips_rows_without_usable_enrichment_and_scopes_client(
        self, session
    ) -> None:
        client_a = Client(name="a")
        client_b = Client(name="b")
        session.add_all([client_a, client_b])
        session.commit()

        no_enrichment = _mention(client_a.id, 1, sentiment=Sentiment.neutral)
        bad_label = _mention(client_a.id, 2, sentiment=Sentiment.neutral)
        bad_label.raw_enrichment = {"sentiment": "whatever"}
        other_client = _mention(client_b.id, 3, sentiment=Sentiment.negative)
        other_client.raw_enrichment = {"sentiment": "positive", "sentiment_score": 0.7}
        session.add_all([no_enrichment, bad_label, other_client])
        session.commit()

        stats = align_sentiment(session, client_id=client_a.id, apply=True)
        assert stats["skipped_no_enrichment"] == 2
        assert stats["aligned"] == 0  # b's stale row is out of scope
        session.expire_all()
        rows = {m.id: m for m in session.query(Mention).all()}
        assert rows[other_client.id].sentiment is Sentiment.negative

        stats = align_sentiment(session, apply=True)
        assert stats["aligned"] == 1
        session.expire_all()
        rows = {m.id: m for m in session.query(Mention).all()}
        assert rows[other_client.id].sentiment is Sentiment.positive
