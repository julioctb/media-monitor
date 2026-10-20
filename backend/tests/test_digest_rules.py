"""Deterministic digest rules: confidence from source count, gaps from silence."""

from app.summaries.digest import confidence_for, gaps_for


def test_confidence_by_independent_sources() -> None:
    assert confidence_for(3) == "alta"
    assert confidence_for(4) == "alta"
    assert confidence_for(2) == "media"
    assert confidence_for(1) == "baja"
    assert confidence_for(0) == "baja"


def test_gaps_list_silent_social_sources() -> None:
    gaps = gaps_for(
        counts={"x": 0, "facebook_page": 0, "news_rss": 5},
        social={"x", "facebook_page"},
        labels={"x": "X (Twitter)", "facebook_page": "Facebook"},
    )
    assert gaps == [
        "Facebook sin cobertura en la ventana",
        "X (Twitter) sin cobertura en la ventana",
    ]


def test_gaps_empty_when_social_covered() -> None:
    assert (
        gaps_for(counts={"x": 2}, social={"x"}, labels={"x": "X (Twitter)"}) == []
    )
