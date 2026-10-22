"""Scraper ingestion: per-site parsers, adapter, settings surface.

Fixture HTML files are trimmed captures of the real homepages (kept under
tests/fixtures/); httpx.MockTransport injects them, so no test touches the
network. The settings roundtrip mirrors test_api.py's dependency overrides.
"""

import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ingest.scrapers import (
    SCRAPER_REGISTRY,
    ScrapersAdapter,
    parse_diario_laredaccion,
    parse_e_consulta,
    parse_elpopular,
)
from app.models import Base, Client
from app.models.base import MentionSource

FIXTURES = Path(__file__).parent / "fixtures"

LAREDACCION_BASE = "https://diariolaredaccion.mx"
E_CONSULTA_BASE = "https://www.e-consulta.com"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def _path_segments(url: str) -> list[str]:
    from urllib.parse import urlsplit

    return [seg for seg in urlsplit(url).path.split("/") if seg]


class TestDiarioLaredaccionParser:
    def test_extracts_absolute_articles_with_titles(self) -> None:
        links = parse_diario_laredaccion(_fixture("diariolaredaccion_home.html"))
        assert len(links) >= 10
        expected = (
            f"{LAREDACCION_BASE}/politica/critica-alfredo-gomez-la-reeleccion-en-nueva-alianza-pero-es-militante-de-morena/",
            "Critica Alfredo Gómez la reelección en Nueva Alianza, pero es militante de Morena",
        )
        assert expected in links
        for url, title in links:
            assert url.startswith(f"{LAREDACCION_BASE}/")
            assert title.strip()

    def test_excludes_nav_category_and_static_links(self) -> None:
        links = parse_diario_laredaccion(_fixture("diariolaredaccion_home.html"))
        urls = [url for url, _ in links]
        assert len(urls) == len(set(urls))  # deduplicated
        for url in urls:
            segments = _path_segments(url)
            assert len(segments) >= 2  # real slug paths, never bare sections
            assert segments[0] not in {"seccion", "autores", "tag", "page"}
            assert not segments[-1].endswith((".css", ".js", ".png", ".jpg"))


class TestEConsultaParser:
    def test_decodes_entity_encoded_hrefs(self) -> None:
        # The homepage HTML-entity-encodes path separators (&#x2F;).
        links = parse_e_consulta(_fixture("econsulta_home.html"))
        expected = (
            f"{E_CONSULTA_BASE}/salud/trabajadores-de-imss-puebla-acusan-irregularidades-durante-consulta-salarial",
            "Trabajadores de IMSS Puebla acusan irregularidades durante consulta salarial",
        )
        assert expected in links

    def test_extracts_only_same_site_article_links(self) -> None:
        links = parse_e_consulta(_fixture("econsulta_home.html"))
        assert len(links) >= 10
        for url, title in links:
            assert url.startswith(f"{E_CONSULTA_BASE}/")
            segments = _path_segments(url)
            assert len(segments) >= 2
            assert segments[0] not in {"secciones", "fonts", "images", "directorio"}
            assert title.strip()


ELPOPULAR_BASE = "https://elpopular.mx"


class TestElPopularParser:
    def test_extracts_dated_articles_with_titles(self) -> None:
        # elpopular.mx: no feed; articles are /<taxo>[/<sub>]/YYYY/MM/DD/<slug>.
        links = parse_elpopular(_fixture("elpopular_home.html"))
        expected = (
            f"{ELPOPULAR_BASE}/gobierno/2026/10/22/gobierno-de-puebla-busca-financiar-mas-de-500-viviendas-para-sus-policias",
            "Gobierno de Puebla busca financiar más de 500 viviendas para sus policías",
        )
        assert expected in links
        assert len(links) >= 10
        for url, title in links:
            assert url.startswith(f"{ELPOPULAR_BASE}/")
            assert title.strip()

    def test_keeps_only_date_shaped_paths(self) -> None:
        links = parse_elpopular(_fixture("elpopular_home.html"))
        urls = [url for url, _ in links]
        assert len(urls) == len(set(urls))  # deduplicated
        for url in urls:
            segments = _path_segments(url)
            dated = any(
                re.fullmatch(r"\d{4}", segments[i])
                and re.fullmatch(r"\d{2}", segments[i + 1])
                and re.fullmatch(r"\d{2}", segments[i + 2])
                for i in range(len(segments) - 3)
            )
            assert dated, f"undated link leaked: {url}"

    def test_excludes_nav_reporteros_and_category_links(self) -> None:
        links = parse_elpopular(_fixture("elpopular_home.html"))
        urls = [url for url, _ in links]
        assert not any("/reporteros/" in url for url in urls)
        assert not any(url == f"{ELPOPULAR_BASE}/secciones/puebla" for url in urls)
        assert not any(
            re.fullmatch(rf"{re.escape(ELPOPULAR_BASE)}/[a-z-]+/?", url) for url in urls
        )

    def test_registry_entry_lists_home_and_puebla_section(self) -> None:
        spec = SCRAPER_REGISTRY["elpopular"]
        assert spec.base_url == ELPOPULAR_BASE
        assert spec.list_urls == (
            f"{ELPOPULAR_BASE}/",
            f"{ELPOPULAR_BASE}/secciones/puebla",
        )
        assert callable(spec.parse)


class TestScrapersAdapter:
    def _adapter(self, names, handler) -> ScrapersAdapter:
        return ScrapersAdapter(names, client=_mock_client(handler))

    def test_fetch_emits_scraper_mentions_with_keyword_match(self) -> None:
        payloads = {
            f"{LAREDACCION_BASE}/": _fixture("diariolaredaccion_home.html"),
            f"{E_CONSULTA_BASE}/": _fixture("econsulta_home.html"),
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=payloads[str(request.url)])

        adapter = self._adapter(["diario_laredaccion", "e_consulta"], handler)
        mentions = adapter.fetch(["IMSS", "BUAP"])
        assert mentions, "fixture pages must yield matches for both keywords"
        assert {m.source for m in mentions} == {MentionSource.scraper}
        by_url = {m.url: m for m in mentions}
        imss = by_url[
            f"{E_CONSULTA_BASE}/salud/trabajadores-de-imss-puebla-acusan-irregularidades-durante-consulta-salarial"
        ]
        assert imss.keyword == "IMSS"
        assert imss.title and "IMSS" in imss.title
        buap = by_url[
            f"{LAREDACCION_BASE}/educacion/el-estadio-de-atletismo-de-la-buap-lleva-un-ano-sin-terminarse/"
        ]
        assert buap.keyword == "BUAP"
        # Scraper pages expose no body text or publish dates: None, like the spec.
        assert imss.content is None
        assert imss.published_at is None

    def test_unknown_names_are_skipped(self) -> None:
        adapter = self._adapter(["does_not_exist"], lambda request: httpx.Response(200))
        assert adapter.fetch(["anything"]) == []

    def test_failing_site_is_skipped_not_raised(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(LAREDACCION_BASE):
                return httpx.Response(500)
            return httpx.Response(200, text=_fixture("econsulta_home.html"))

        adapter = self._adapter(["diario_laredaccion", "e_consulta"], handler)
        mentions = adapter.fetch(["IMSS"])
        assert mentions
        assert all(m.url.startswith(E_CONSULTA_BASE) for m in mentions)


class TestScraperSettingsApi:
    @pytest.fixture()
    def api(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path}/api.db")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, expire_on_commit=False)()
        client_row = Client(name="acme")
        db.add(client_row)
        db.commit()

        from app.api.deps import get_client_id
        from app.db import get_db
        from app.main import create_app

        app = create_app()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_client_id] = lambda: client_row.id
        with TestClient(app) as client:
            yield client, client_row.id
        db.close()
        engine.dispose()

    def test_settings_roundtrip_persists_scrapers(self, api) -> None:
        client, client_id = api
        stored = client.put(
            "/api/settings", json={"client_name": "acme", "scrapers": ["e_consulta"]}
        )
        assert stored.status_code == 200
        assert stored.json()["scrapers"] == ["e_consulta"]
        fetched = client.get("/api/settings")
        assert fetched.status_code == 200
        assert fetched.json()["scrapers"] == ["e_consulta"]

    def test_scrapers_validation(self, api) -> None:
        client, _ = api
        # Not a list -> 422 via the queries validator.
        bad = client.put("/api/settings", json={"scrapers": "e_consulta"})
        assert bad.status_code == 422
        # Empty names and duplicates are normalized away.
        dupes = client.put(
            "/api/settings", json={"scrapers": ["e_consulta", "e_consulta", "  "]}
        )
        assert dupes.status_code == 200
        assert dupes.json()["scrapers"] == ["e_consulta"]

    def test_scrapers_available_lists_registry(self, api) -> None:
        client, client_id = api
        response = client.get(f"/api/clients/{client_id}/scrapers/available")
        assert response.status_code == 200
        available = response.json()
        assert {entry["name"] for entry in available} == set(SCRAPER_REGISTRY)
        for entry in available:
            assert entry["base_url"].startswith("https://")
            spec = SCRAPER_REGISTRY[entry["name"]]
            assert entry["base_url"] == spec.base_url


class TestWorkerScrapers:
    def test_scrapers_enabled_from_settings(self, monkeypatch) -> None:
        from app import worker
        from app.settings_runtime import EffectiveSettings

        monkeypatch.setattr(worker.settings, "x_provider_api_key", "")
        effective = EffectiveSettings(
            client_id=1, scrapers=("e_consulta", "unknown_scraper")
        )
        adapters = worker.build_adapters(effective)
        scrapers = [a for a in adapters if a.name == "scraper"]
        assert len(scrapers) == 1
        assert scrapers[0]._names == ["e_consulta"]  # unknown filtered, logged

    def test_scrapers_absent_leaves_adapter_out(self, monkeypatch) -> None:
        from app import worker
        from app.settings_runtime import EffectiveSettings

        monkeypatch.setattr(worker.settings, "x_provider_api_key", "")
        adapters = worker.build_adapters(EffectiveSettings(client_id=1))
        assert all(a.name != "scraper" for a in adapters)
