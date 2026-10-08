"""URL normalization tests for dedupe (fbclid/gclid added in T3)."""

from app.models.mention import make_url_hash


def test_fbclid_gclid_stripped() -> None:
    assert make_url_hash("https://example.com/a?fbclid=abc123") == make_url_hash(
        "https://example.com/a"
    )
    assert make_url_hash("https://example.com/a?gclid=xyz") == make_url_hash(
        "https://example.com/a"
    )


def test_other_params_kept() -> None:
    assert make_url_hash("https://example.com/a?id=7") != make_url_hash(
        "https://example.com/a"
    )


def test_utm_still_stripped() -> None:
    assert make_url_hash("https://example.com/a?utm_medium=rss") == make_url_hash(
        "https://example.com/a"
    )
