"""Tests for app.ingest.article_fetch (article content fetcher)."""

import json

import httpx

from app.ingest import article_fetch
from app.models.base import MentionSource


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=1)


def test_regex_fallback_extracts_text_without_paragraph_tags():
    html = "<html><body><div>" + "Texto largo sin parrafos. " * 30 + "</div></body></html>"
    text = article_fetch.extract_article_text(html)
    assert text is not None
    assert "Texto largo" in text
    assert "<div>" not in text


def test_short_page_returns_none():
    assert article_fetch.extract_article_text("<p>too short</p>") is None
    assert article_fetch.extract_article_text("") is None
    assert article_fetch.extract_article_text(None) is None


def test_truncates_to_max_content_chars():
    body = "Palabra " * 1500  # ~12000 chars
    html = f"<article><p>{body}</p></article>"
    text = article_fetch.extract_article_text(html)
    assert text is not None
    assert len(text) <= article_fetch.MAX_CONTENT_CHARS


def test_fetch_article_returns_none_on_http_error():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    assert article_fetch.fetch_article("https://example.com/a", client=_client(handler)) is None


def test_fetch_article_extracts_publisher_page():
    html = "<html><body><article><p>" + "Cuerpo de la nota periodistica. " * 20 + "</p></article></body></html>"

    def handler(request):
        assert "user-agent" in request.headers
        return httpx.Response(200, text=html)

    text = article_fetch.fetch_article("https://example.com/nota", client=_client(handler))
    assert text is not None
    assert "Cuerpo de la nota" in text


def test_fetch_article_none_on_non_200():
    def handler(request):
        return httpx.Response(404, text="<html></html>")

    assert article_fetch.fetch_article("https://example.com/x", client=_client(handler)) is None


def test_fetch_article_resolves_google_news_redirect():
    article_html = "<html><body><article><p>" + "Nota completa del diario local. " * 20 + "</p></article></body></html>"

    def handler(request):
        url = str(request.url)
        if "batchexecute" in url:
            inner = json.dumps(["garturlres", "https://diario.com/nota-final"])
            body = ")]}'\n\n" + json.dumps([["wrb.fr", "Fbv4je", inner, "0"]])
            return httpx.Response(200, text=body)
        if request.url.path.startswith("/rss/articles/"):
            page = '<html><c-wiz><div jscontroller="x" data-n-a-sg="SG" data-n-a-ts="123"></div></c-wiz></html>'
            return httpx.Response(200, text=page)
        return httpx.Response(200, text=article_html)

    text = article_fetch.fetch_article(
        "https://news.google.com/rss/articles/ABC123?oc=5", client=_client(handler)
    )
    assert text is not None
    assert "Nota completa" in text



def test_extracts_article_paragraphs_and_strips_boilerplate():
    html = """
    <html><head><title>T</title></head><body>
    <nav><p>Menu item one</p></nav>
    <script>var x = 1;</script>
    <article>
      <p>Parrafo uno con contenido suficiente para el monitor de medios: la BUAP anunciada hoy la nueva inversion y el calendario de obra para el ciclo escolar.</p>
      <p>Parrafo dos tambien aporta contexto, supera el limite minimo y cita la cifra oficial de estudiantes beneficiados en el municipio.</p>
    </article>
    <footer><p>Derechos reservados dos mil veintiseis</p></footer>
    </body></html>
    """
    text = article_fetch.extract_article_text(html)
    assert text is not None
    assert "Parrafo uno" in text
    assert "Parrafo dos" in text
    assert "var x" not in text
    assert "Menu item" not in text
    assert "<p>" not in text


def test_registry_covers_every_source():
    assert set(article_fetch.CONTENT_FETCHERS) == set(MentionSource)
    for member in MentionSource:
        assert article_fetch.fetcher_for(member) is article_fetch.CONTENT_FETCHERS[member]


def test_news_sources_fetch_and_social_passthrough():
    assert callable(article_fetch.fetcher_for(MentionSource.news_rss))
    assert callable(article_fetch.fetcher_for(MentionSource.gdelt))
    assert callable(article_fetch.fetcher_for(MentionSource.rss_custom))
    # X/FB posts carry their text inline: registry says don't fetch.
    assert article_fetch.fetcher_for(MentionSource.x_twitter) is None
    assert article_fetch.fetcher_for(MentionSource.facebook_page) is None


def test_fetch_article_never_raises_on_garbage_url():
    # Empty / malformed URLs return None instead of raising.
    assert article_fetch.fetch_article("") is None
    assert article_fetch.fetch_article("not a url") is None


def test_extract_published_from_meta():
    html = '<html><head><meta property="article:published_time" content="2026-10-15T18:42:29-06:00"></head></html>'
    published = article_fetch.extract_published_at(html)
    assert published is not None
    assert published.year == 2026 and published.month == 10 and published.day == 15
    assert published.utcoffset().total_seconds() == -6 * 3600


def test_extract_published_from_jsonld():
    html = (
        '<html><head><script type="application/ld+json">'
        '{"datePublished": "2026-10-15T18:42:29+00:00"}'
        "</script></head></html>"
    )
    published = article_fetch.extract_published_at(html)
    assert published is not None and published.day == 15


def test_extract_published_from_time_tag_and_none_case():
    html = "<html><body><time datetime='2026-10-15T09:00:00Z'>hoy</time></body></html>"
    published = article_fetch.extract_published_at(html)
    assert published is not None and published.day == 15
    assert article_fetch.extract_published_at("<html><body>x</body></html>") is None
    assert article_fetch.extract_published_at("") is None


def test_fetch_article_content_carries_published_at(monkeypatch):
    html = '<html><head><meta property="article:published_time" content="2026-10-15T18:42:29-06:00"></head><body><p>' + "Parrafo con cuerpo suficiente. " * 20 + "</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    with _client(handler) as client:
        result = article_fetch.fetch_article_content("https://example.com/a", client)
    assert result.published_at is not None and result.published_at.day == 15
    assert result.text and "Parrafo" in result.text
