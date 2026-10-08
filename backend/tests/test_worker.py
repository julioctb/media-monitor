"""Worker adapter-wiring tests (no scheduler start, no network)."""

from app import worker


def test_x_provider_disabled_without_key(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "x_provider_api_key", "")
    adapters = worker.build_adapters()
    names = [a.name for a in adapters]
    assert names == ["google_news", "gdelt"]


def test_x_provider_enabled_with_key(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "x_provider_api_key", "secret")
    monkeypatch.setattr(
        worker.settings, "x_provider_base_url", "https://api.twitterapi.io"
    )
    monkeypatch.setattr(worker.settings, "x_provider_rate_per_min", 5.0)
    adapters = worker.build_adapters()
    names = [a.name for a in adapters]
    assert names == ["google_news", "gdelt", "x_twitter"]
    # Construction must not open connections.
    assert adapters[2].search_url == "https://api.twitterapi.io/twitter/tweet/advanced_search"
