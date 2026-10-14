"""Tests for scripts.backfill_content (content-less mention backfill)."""

import pytest

from app.models import Client, Mention, MentionSource, make_url_hash


def _mention(client_id: int, n: int, source=MentionSource.news_rss, content=None):
    url = f"https://example.com/{n}"
    return Mention(
        client_id=client_id,
        source=source,
        url=url,
        url_hash=make_url_hash(url),
        title=f"t{n}",
        content=content,
    )


class TestBackfillContent:
    def test_fetches_only_contentless_fetchable_mentions(self, session, monkeypatch) -> None:
        from scripts import backfill_content as mod

        calls: list[str] = []

        def fake_fetch(url: str) -> str:
            calls.append(url)
            return "Cuerpo completo de la nota con datos suficientes. " * 5

        monkeypatch.setattr(
            mod, "CONTENT_FETCHERS",
            {MentionSource.news_rss: fake_fetch, MentionSource.x_twitter: None},
        )
        client = Client(name="c")
        session.add(client)
        session.commit()
        session.add_all(
            [
                _mention(client.id, 1),  # fetched
                _mention(client.id, 2, content="ya tiene texto"),  # skipped
                _mention(client.id, 3, source=MentionSource.x_twitter),  # no fetcher
            ]
        )
        session.commit()

        totals = mod.backfill_missing(session, dry_run=False)
        assert totals == {"fetched": 1, "failed": 0, "skipped_has_content": 1}
        assert calls == ["https://example.com/1"]
        m1 = session.query(Mention).filter(Mention.title == "t1").one()
        assert m1.content is not None and m1.content.startswith("Cuerpo completo")

    def test_dry_run_writes_nothing(self, session, monkeypatch) -> None:
        from scripts import backfill_content as mod

        monkeypatch.setattr(
            mod, "CONTENT_FETCHERS",
            {MentionSource.news_rss: lambda url: "Cuerpo de la nota. " * 10},
        )
        client = Client(name="c")
        session.add(client)
        session.commit()
        session.add(_mention(client.id, 1))
        session.commit()

        totals = mod.backfill_missing(session, dry_run=True)
        assert totals["fetched"] == 1
        (mention,) = session.query(Mention).all()
        assert mention.content is None

    def test_fetch_failure_counts_as_failed(self, session, monkeypatch) -> None:
        from scripts import backfill_content as mod

        def broken(url: str) -> str:
            raise RuntimeError("down")

        monkeypatch.setattr(mod, "CONTENT_FETCHERS", {MentionSource.news_rss: broken})
        client = Client(name="c")
        session.add(client)
        session.commit()
        session.add(_mention(client.id, 1))
        session.commit()

        totals = mod.backfill_missing(session, dry_run=False)
        assert totals["failed"] == 1
        (mention,) = session.query(Mention).all()
        assert mention.content is None

    def test_limit_caps_pending(self, session, monkeypatch) -> None:
        from scripts import backfill_content as mod

        monkeypatch.setattr(
            mod, "CONTENT_FETCHERS",
            {MentionSource.news_rss: lambda url: "Cuerpo de la nota larga. " * 10},
        )
        client = Client(name="c")
        session.add(client)
        session.commit()
        session.add_all([_mention(client.id, n) for n in (1, 2, 3)])
        session.commit()

        totals = mod.backfill_missing(session, limit=2, dry_run=False)
        assert totals["fetched"] == 2
        assert session.query(Mention).filter(Mention.content.is_(None)).count() == 1

    def test_real_registry_covers_news_sources(self) -> None:
        from app.ingest.article_fetch import CONTENT_FETCHERS

        for source in (MentionSource.news_rss, MentionSource.gdelt, MentionSource.rss_custom):
            assert callable(CONTENT_FETCHERS[source])
