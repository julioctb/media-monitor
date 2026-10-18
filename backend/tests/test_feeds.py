"""Unit tests for RSS feed parsing (app.ingest.feeds)."""

from pathlib import Path

from app.ingest.feeds import parse_feed

FIXTURES = Path(__file__).parent / "fixtures"


def _rss_xml(description: str) -> str:
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<title>t</title><link>https://example.com</link><description>d</description>"
        "<item><title>Titular</title><link>https://example.com/a</link>"
        f"<description>{description}</description></item>"
        "</channel></rss>"
    )


def test_parse_feed_strips_html_from_description() -> None:
    """HTML embedded in the RSS description must not reach content verbatim."""
    xml = _rss_xml(
        "<p><img alt='foto' src='https://cdn.example/x.jpg' width='940' />"
        "Texto del artículo aquí</p>"
    )
    (mentions := parse_feed(xml, ["palabra"]))  # noqa: F841 - asserted below
    assert len(mentions) == 1
    content = mentions[0].content or ""
    assert "<img" not in content
    assert "<p>" not in content
    assert "Texto del artículo" in content


def test_parse_feed_captures_author() -> None:
    """Columnist byline from the feed lands on the mention (author tracking)."""
    xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<title>t</title><link>https://example.com</link><description>d</description>"
        "<item><title>Columna</title><link>https://example.com/columna</link>"
        "<description>Texto opinión</description>"
        "<dc:creator>Patricia Gutiérrez Rodríguez</dc:creator>"
        "</item></channel></rss>"
    )
    mentions = parse_feed(xml, ["palabra"])
    assert len(mentions) == 1
    assert mentions[0].author == "Patricia Gutiérrez Rodríguez"
