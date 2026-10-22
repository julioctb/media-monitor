"""Parser tests run against the committed real-page fixture (T2).

The live logged-out wall (2026-10-22) renders permalinks as
``permalink.php?story_fbid=...`` and carries no ``data-utime`` — the
fixture locks that reality in; the synthetic cases below cover the
utime/relative fallbacks so none of the timestamp paths is untested.
"""

from datetime import datetime, timezone
from pathlib import Path

from app.ingest.facebook_public import extract_posts

FIXTURE = Path(__file__).parent / "fixtures" / "facebook_page_public.html"


def _articles():
    return extract_posts(FIXTURE.read_text())


def test_extracts_some_posts():
    posts = _articles()
    assert 1 <= len(posts) <= 15


def test_every_post_has_permalink_and_text():
    for p in _articles():
        assert p["url"].startswith("https://www.facebook.com/")
        assert (
            "/posts/" in p["url"]
            or "/permalink/" in p["url"]
            or "/videos/" in p["url"]
            or "permalink.php" in p["url"]
        )
        assert len(p["text"]) >= 1


def test_external_id_from_permalink():
    posts = _articles()
    assert all(p["external_id"] for p in posts)


def test_created_at_tz_aware_or_none():
    for p in _articles():
        if p["created_at"] is None:
            continue
        assert p["created_at"].tzinfo is not None


def test_dedupes_nested_articles_by_url():
    urls = [p["url"] for p in _articles()]
    assert len(urls) == len(set(urls))


def test_utime_parsed_when_present():
    html = '<div role="article"><a href="https://www.facebook.com/foo/posts/123">x</a>' \
        '<span data-utime="1700000000">t</span><span dir="auto">Un texto suficientemente largo</span></div>'
    (post,) = extract_posts(html)
    assert post["created_at"] is not None
    assert post["created_at"].tzinfo is not None


def test_relative_label_fallback(monkeypatch):
    from app.ingest.facebook_public import _parse_relative

    now = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)
    assert _parse_relative("hace 2 horas", now) == datetime(2026, 10, 22, 13, 0, tzinfo=timezone.utc)
    assert _parse_relative("hace 30 min", now) == datetime(2026, 10, 22, 14, 30, tzinfo=timezone.utc)
    relative = _parse_relative("hace 3 días", now)
    assert relative is not None and relative.day == 19
    assert _parse_relative("mañana", now) is None


def test_to_raw_mentions_maps_fields():
    from app.ingest.facebook_public import to_raw_mentions

    posts = [
        {
            "url": "https://www.facebook.com/foo/posts/123",
            "external_id": "123",
            "text": "La BUAP anuncio algo",
            "created_at": None,
        }
    ]
    rows = to_raw_mentions(posts, "42", "Pagina X", ["BUAP"])
    assert rows[0].source.value == "facebook_page"
    assert rows[0].keyword == "BUAP"
    assert rows[0].author == "Pagina X"
    assert rows[0].url.endswith("/posts/123")
    assert rows[0].external_id == "123"
    assert rows[0].title == "La BUAP anuncio algo"
    assert rows[0].raw == {"page_id": "42", "src": "public_html"}
