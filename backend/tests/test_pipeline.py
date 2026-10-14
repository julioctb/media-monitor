"""Pipeline tests: matching re-validation, dedupe, sentiment fill, scoping."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.ingest import article_fetch
from app.ingest.base import RawMention, SourceAdapter
from app.ingest import pipeline
from app.ingest.pipeline import persist_raw_mentions, run_ingest_cycle
from app.models import Client, Keyword, Mention, MentionSource, queries
from app.models.base import Sentiment


class FakeAdapter(SourceAdapter):
    name = "fake"

    def __init__(self, items: list[RawMention]) -> None:
        self.items = items

    def fetch(self, keywords, since=None) -> list[RawMention]:
        return self.items


@dataclass
class MockAnalyzer:
    label: Sentiment = Sentiment.positive
    score: float = 0.9
    calls: list = field(default_factory=list)

    def analyze(self, text: str, lang: str):
        self.calls.append((text, lang))
        from dataclasses import dataclass as _dc

        @dataclass
        class R:
            label: Sentiment
            score: float

        return R(self.label, self.score)


def _raw(url: str, keyword: str = "BUAP", title: str | None = "BUAP noticia") -> RawMention:
    return RawMention(
        source=MentionSource.news_rss,
        keyword=keyword,
        url=url,
        title=title,
        lang="es",
        published_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
    )


def _client_with_keywords(session) -> tuple[Client, list[Keyword]]:
    client = queries.get_or_create_client(session, "test")
    kws = [
        Keyword(client_id=client.id, text="BUAP", language="es"),
        Keyword(client_id=client.id, text="Tecnológico", language="es"),
    ]
    session.add_all(kws)
    session.commit()
    return client, kws


class TestPersistRawMentions:
    def test_inserts_matching_mention_with_keyword_id(self, session) -> None:
        client, kws = _client_with_keywords(session)
        inserted = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[_raw("https://example.com/1")],
            keyword_by_text={"buap": kws[0], "tecnologico": kws[1]},
            all_keyword_texts=["BUAP", "Tecnológico"],
        )
        assert inserted == 1
        m = session.query(Mention).one()
        assert m.keyword_id == kws[0].id
        assert m.source is MentionSource.news_rss

    def test_assigns_canonical_event_on_insert(self, session) -> None:
        client, kws = _client_with_keywords(session)
        inserted = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[
                _raw("https://example.com/e1", title="BUAP inaugura edificio en Zacapoaxtla"),
                _raw(
                    "https://example.com/e2",
                    title="Edificio inaugurado en Zacapoaztla por la BUAP",
                ),
            ],
            keyword_by_text={"buap": kws[0], "tecnologico": kws[1]},
            all_keyword_texts=["BUAP", "Tecnológico"],
        )
        assert inserted == 2
        mentions = session.query(Mention).all()
        event_ids = {m.event_id for m in mentions}
        assert len(event_ids) == 1 and None not in event_ids
        event = mentions[0].event
        assert event.mention_count == 2

    def test_mention_without_title_has_no_event(self, session) -> None:
        client, kws = _client_with_keywords(session)
        item = _raw("https://example.com/noTitle", title=None)
        item.content = "BUAP en el texto"
        inserted = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[item],
            keyword_by_text={"buap": kws[0], "tecnologico": kws[1]},
            all_keyword_texts=["BUAP", "Tecnológico"],
        )
        assert inserted == 1
        (mention,) = session.query(Mention).all()
        assert mention.event_id is None

    def test_drops_non_matching_item(self, session) -> None:
        client, _ = _client_with_keywords(session)
        inserted = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[_raw("https://example.com/2", title="Otra historia sin marca")],
            keyword_by_text={"buap": None},
            all_keyword_texts=["BUAP"],
        )
        assert inserted == 0
        assert session.query(Mention).count() == 0

    def test_dedupes_same_url_across_cycles(self, session) -> None:
        client, kws = _client_with_keywords(session)
        first = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[_raw("https://example.com/3")],
            keyword_by_text={"buap": kws[0]},
            all_keyword_texts=["BUAP"],
        )
        second = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[_raw("https://example.com/3?utm_source=rss")],
            keyword_by_text={"buap": kws[0]},
            all_keyword_texts=["BUAP"],
        )
        assert (first, second) == (1, 0)
        assert session.query(Mention).count() == 1

    def test_falls_back_to_other_tracked_keyword(self, session) -> None:
        """Source rewrote the title: fetch keyword absent, other keyword present."""
        client, kws = _client_with_keywords(session)
        inserted = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[
                _raw(
                    "https://example.com/4",
                    keyword="BUAP",
                    title="El Tecnológico de Puebla inaugura edificio",
                )
            ],
            keyword_by_text={"buap": kws[0], "tecnologico": kws[1]},
            all_keyword_texts=["BUAP", "Tecnológico"],
        )
        assert inserted == 1
        m = session.query(Mention).one()
        assert m.keyword_id == kws[1].id

    def test_sentiment_filled_when_analyzer_given(self, session) -> None:
        client, kws = _client_with_keywords(session)
        analyzer = MockAnalyzer(label=Sentiment.negative, score=0.71)
        persist_raw_mentions(
            session,
            client_id=client.id,
            items=[_raw("https://example.com/5")],
            keyword_by_text={"buap": kws[0]},
            all_keyword_texts=["BUAP"],
            sentiment_analyzer=analyzer,
        )
        m = session.query(Mention).one()
        assert m.sentiment is Sentiment.negative
        assert m.sentiment_score == 0.71
        assert analyzer.calls and analyzer.calls[0][1] == "es"

    def test_sentiment_failure_does_not_block_insert(self, session) -> None:
        client, kws = _client_with_keywords(session)

        class Broken:
            def analyze(self, text, lang):
                raise RuntimeError("model exploded")

        inserted = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[_raw("https://example.com/6")],
            keyword_by_text={"buap": kws[0]},
            all_keyword_texts=["BUAP"],
            sentiment_analyzer=Broken(),
        )
        assert inserted == 1
        m = session.query(Mention).one()
        assert m.sentiment is None

    def test_accented_text_matches_unaccented_keyword(self, session) -> None:
        client, kws = _client_with_keywords(session)
        inserted = persist_raw_mentions(
            session,
            client_id=client.id,
            items=[_raw("https://example.com/7", title="Gran día para la BÜAP")],
            keyword_by_text={"buap": kws[0]},
            all_keyword_texts=["BUAP"],
        )
        assert inserted == 1


class NamedFakeAdapter(SourceAdapter):
    def __init__(self, name: str, items: list[RawMention]) -> None:
        self.name = name
        self.items = items

    def fetch(self, keywords, since=None) -> list[RawMention]:
        return self.items


class TestRunIngestCycle:
    def test_runs_all_adapters_and_counts(self, session) -> None:
        client, kws = _client_with_keywords(session)
        stats = run_ingest_cycle(
            session,
            client_id=client.id,
            keywords=kws,
            adapters=[
                NamedFakeAdapter("rss", [_raw("https://example.com/a")]),
                NamedFakeAdapter(
                    "gdelt",
                    [_raw("https://example.com/b", keyword="Tecnológico", title="Tecnológico abre")],
                ),
            ],
        )
        assert stats == {"rss": 1, "gdelt": 1}
        assert session.query(Mention).count() == 2

    def test_adapter_crash_does_not_kill_cycle(self, session) -> None:
        client, kws = _client_with_keywords(session)

        class Exploding(SourceAdapter):
            name = "exploding"

            def fetch(self, keywords, since=None):
                raise ConnectionError("boom")

        good = NamedFakeAdapter("fake", [_raw("https://example.com/c")])
        stats = run_ingest_cycle(
            session,
            client_id=client.id,
            keywords=kws,
            adapters=[Exploding(), good],
        )
        assert stats["exploding"] == 0
        assert stats["fake"] == 1

    def test_inactive_keywords_skipped(self, session) -> None:
        client, kws = _client_with_keywords(session)
        kws[1].is_active = False
        session.commit()
        adapter = NamedFakeAdapter(
            "fake",
            [_raw("https://example.com/d", keyword="Tecnológico", title="Tecnológico abre")],
        )
        stats = run_ingest_cycle(
            session,
            client_id=client.id,
            keywords=kws,
            adapters=[adapter],
        )
        # Item's keyword is inactive AND text does not contain BUAP -> dropped
        assert stats == {"fake": 0}
        assert session.query(Mention).count() == 0


class TestArticleFetchWiring:
    """F2c-article-fetch: pipeline fetches bodies before enrichment."""

    def _run(self, session, items, **kwargs):
        client, kws = _client_with_keywords(session)
        return client, persist_raw_mentions(
            session,
            client_id=client.id,
            items=items,
            keyword_by_text={"buap": kws[0]},
            all_keyword_texts=["BUAP"],
            **kwargs,
        )

    def test_fetch_fills_content_and_feeds_enrichment(self, session, monkeypatch) -> None:
        body = "Cuerpo completo de la nota periodistica con datos oficiales. " * 5
        calls: list[str] = []

        def fake_fetcher(url: str) -> str:
            calls.append(url)
            return body

        monkeypatch.setattr(pipeline, "fetcher_for", lambda source: fake_fetcher)
        analyzer = MockAnalyzer()
        self._run(
            session,
            [_raw("https://example.com/f1")],
            sentiment_analyzer=analyzer,
        )
        (mention,) = session.query(Mention).all()
        assert mention.content == body.strip()
        assert calls == ["https://example.com/f1"]
        # The LLM/analyzer sees title + fetched body, not the bare title.
        assert "BUAP noticia" in analyzer.calls[0][0]
        assert "Cuerpo completo" in analyzer.calls[0][0]

    def test_fetch_limit_caps_calls_per_cycle(self, session, monkeypatch) -> None:
        calls: list[str] = []

        def fake_fetcher(url: str) -> str:
            calls.append(url)
            return "Cuerpo suficiente para contar como articulo completo. " * 5

        monkeypatch.setattr(pipeline, "fetcher_for", lambda source: fake_fetcher)
        _, inserted = self._run(
            session,
            [
                _raw("https://example.com/g1", title="BUAP nota uno"),
                _raw("https://example.com/g2", title="BUAP nota dos"),
            ],
            fetch_limit=1,
        )
        assert inserted == 2
        assert len(calls) == 1
        contents = [m.content for m in session.query(Mention).order_by(Mention.id)]
        assert contents[0] and contents[1] is None

    def test_fetch_failure_leaves_content_empty_and_inserts(self, session, monkeypatch) -> None:
        def broken_fetcher(url: str) -> str:
            raise RuntimeError("site down")

        monkeypatch.setattr(pipeline, "fetcher_for", lambda source: broken_fetcher)
        _, inserted = self._run(session, [_raw("https://example.com/h1")])
        assert inserted == 1
        (mention,) = session.query(Mention).all()
        assert mention.content is None

    def test_existing_content_is_not_refetched(self, session, monkeypatch) -> None:
        calls: list[str] = []

        def fake_fetcher(url: str) -> str:
            calls.append(url)
            return "nuevo"

        monkeypatch.setattr(pipeline, "fetcher_for", lambda source: fake_fetcher)
        item = _raw("https://example.com/i1")
        item.content = "El texto ya viene inline"
        self._run(session, [item])
        (mention,) = session.query(Mention).all()
        assert calls == []
        assert mention.content == "El texto ya viene inline"

    def test_social_source_skips_fetch_registry(self, session, monkeypatch) -> None:
        # Real registry: x_twitter has no fetcher -> no call, no stub needed.
        called: list[str] = []

        def spy(source):
            fetcher = article_fetch.fetcher_for(source)
            if fetcher is None:
                return None

            def wrapped(url: str) -> str | None:
                called.append(url)
                return fetcher(url)

            return wrapped

        monkeypatch.setattr(pipeline, "fetcher_for", spy)
        item = RawMention(
            source=MentionSource.x_twitter,
            keyword="BUAP",
            url="https://x.com/u/status/1",
            title="BUAP post",
            lang="es",
        )
        _, inserted = self._run(session, [item])
        assert inserted == 1
        assert called == []
