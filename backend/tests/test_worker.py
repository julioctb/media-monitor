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


def test_facebook_pages_disabled_without_config(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "fb_pages", [])
    monkeypatch.setattr(worker.settings, "x_provider_api_key", "")
    adapters = worker.build_adapters()
    assert [a.name for a in adapters] == ["google_news", "gdelt"]


def test_facebook_pages_enabled_with_config(monkeypatch) -> None:
    from app.config import FacebookPageCredentials

    monkeypatch.setattr(
        worker.settings,
        "fb_pages",
        [FacebookPageCredentials(page_id="1001", token="t", label="L")],
    )
    monkeypatch.setattr(worker.settings, "x_provider_api_key", "")
    adapters = worker.build_adapters()
    assert [a.name for a in adapters] == ["google_news", "gdelt", "facebook_page"]
    # Construction must not open connections; the URL carries the pin.
    assert (
        adapters[2].posts_url("1001")
        == "https://graph.facebook.com/v26.0/1001/posts"
    )
