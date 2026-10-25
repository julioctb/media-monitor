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


def test_strip_fb_chrome_removes_ui_tail():
    from app.ingest.facebook_public import strip_fb_chrome

    dirty = (
        "Verdades Buap CRS actualizó su foto de portada. "
        "hace 14 minutos 14 min · Compartido con: Público "
        "Todas las reacciones: 1 Me gusta Comentar"
    )
    assert strip_fb_chrome(dirty) == "Verdades Buap CRS actualizó su foto de portada."


def test_strip_fb_chrome_is_idempotent_and_keeps_clean_titles():
    from app.ingest.facebook_public import strip_fb_chrome

    clean = "La BUAP anuncio algo"
    assert strip_fb_chrome(clean) == clean
    dirty = "Verdades Buap CRS actualizó su foto de portada. hace 33 minutos 33 min · Compartido con: Público Todas las reacciones: 1 Me gusta Comentar"
    once = strip_fb_chrome(dirty)
    assert strip_fb_chrome(once) == once


def test_strip_fb_chrome_variants():
    from app.ingest.facebook_public import strip_fb_chrome

    # Dash-separated chrome without the middot.
    assert (
        strip_fb_chrome("BUAP emite comunicado hace 2 horas 2 h - Compartido con: Público")
        == "BUAP emite comunicado"
    )
    # Reactions block alone.
    assert (
        strip_fb_chrome("Nota universitaria Todas las reacciones: 12 Me gusta Comentar")
        == "Nota universitaria"
    )
    assert strip_fb_chrome("") == ""
    assert strip_fb_chrome(None) is None


def test_to_raw_mentions_strips_chrome_from_title():
    from app.ingest.facebook_public import to_raw_mentions

    posts = [
        {
            "url": "https://www.facebook.com/foo/posts/1",
            "external_id": "1",
            "text": "Verdades Buap CRS actualizó su foto de portada. hace 5 min 5 min · Compartido con: Público Todas las reacciones: 1 Me gusta Comentar",
            "created_at": None,
        }
    ]
    (row,) = to_raw_mentions(posts, "42", "Pagina", ["BUAP"])
    assert row.title == "Verdades Buap CRS actualizó su foto de portada."


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
