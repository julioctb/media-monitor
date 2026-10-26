"""S7: measured frozen media diversity is not factual confidence."""

from datetime import timedelta

import pytest

from app.models import Event, MentionSource
from app.summaries.digest import build_digest_facts, render_plain_text, validate_digest
from app.summaries.evidence import freeze_sources, resolved_provenance
from app.summaries.builder import SYSTEM_PROMPT, build_daily_summary
from tests.test_digest_facts import DAY, NOON, TZ, _client, _mention


def _event(session, owner, title):
    event = Event(
        client_id=owner, title=title, title_tokens=title,
        first_seen_at=NOON, last_seen_at=NOON,
    )
    session.add(event)
    session.flush()
    return event


def test_legacy_card_projection_does_not_add_new_note_or_indicator_fields():
    from app.summaries.builder import build_tarjetas
    legacy = {"title": "Antigua", "summary": "Reseña.", "confidence_note": "Nota histórica.", "sources": []}
    card = build_tarjetas([legacy])[0]
    assert "confidence_note" not in card
    assert "media_diversity" not in card
    assert "veracity" not in card


def test_legacy_adapter_order_saturates_at_three_and_remains_stable(session):
    owner = _client(session)
    events = []
    adapters = (MentionSource.news_rss, MentionSource.gdelt, MentionSource.rss_custom, MentionSource.scraper)
    for variety in (4, 1, 3, 2):
        event = _event(session, owner, f"Variedad {variety}")
        events.append(event)
        for index in range(4):
            _mention(session, owner, f"https://same.test/{variety}/{index}", event_id=event.id, source=adapters[index % variety])
    facts = build_digest_facts(session, client_id=owner, day=DAY, tz=TZ)
    assert [item["event_id"] for item in facts["noticias"]] == [events[i].id for i in (0, 2, 3, 1)]
    assert all(item["media_diversity"] == {"identified_outlet_count": 1} for item in facts["noticias"])


def test_media_author_fallback_is_a_registered_label_not_an_independence_claim(session):
    owner = _client(session)
    publication = _mention(session, owner, "")
    publication.author = "Medio registrado"
    session.commit()
    facts = build_digest_facts(session, client_id=owner, day=DAY, tz=TZ)
    assert facts["noticias"][0]["media_diversity"] == {"identified_outlet_count": 1}
    assert facts["evidence"] == freeze_sources([publication])


def test_mixed_new_metadata_prevents_legacy_export_even_without_root_version():
    content = {"noticias": [{"title": "Antigua", "confidence": "alta"},
                            {"title": "Nueva", "veracity": "not_evaluated"}]}
    plain = render_plain_text(content, "Titular")
    assert plain.count("Diversidad de medios: no disponible") == 2
    assert "[alta]" not in plain


def test_facts_count_outlets_not_adapters_preserving_legacy_tie_and_catalogue(session):
    owner = _client(session)
    # Insert the one-adapter story first: the old saturated adapter tiebreak
    # must still place the three-adapter story first, not rank by diversity.
    diverse = _event(session, owner, "Tres medios")
    repeated = _event(session, owner, "Un medio")
    publications = []
    for index, host in enumerate(("one.test", "two.test", "three.test")):
        publications.append(_mention(session, owner, f"https://{host}/{index}", event_id=diverse.id))
    for index, (host, source) in enumerate(zip(
        ("same.test", "www.same.test", "SAME.test"),
        (MentionSource.news_rss, MentionSource.gdelt, MentionSource.rss_custom),
    )):
        publications.append(_mention(session, owner, f"https://{host}/{index}", event_id=repeated.id, source=source))
    frozen = freeze_sources(publications)

    facts = build_digest_facts(session, client_id=owner, day=DAY, tz=TZ)

    assert facts["indicators_version"] == 1
    assert [item["event_id"] for item in facts["noticias"]] == [repeated.id, diverse.id]
    assert [item["media_diversity"] for item in facts["noticias"]] == [
        {"identified_outlet_count": 1}, {"identified_outlet_count": 3},
    ]
    assert all(item["veracity"] == "not_evaluated" and "confidence" not in item for item in facts["noticias"])
    assert facts["evidence"] == frozen
    assert facts["coverage"]["total"] == 6
    assert [item["source_refs"] for item in facts["noticias"]] == [[3, 4, 5], [0, 1, 2]]
    assert [item["material_ref"] for item in facts["noticias"]] == [5, 2]


@pytest.mark.parametrize("url,source", [
    ("https://social.test/post", MentionSource.x_twitter),
    ("field://report/1", MentionSource.field_report),
    ("", MentionSource.news_rss),
    ("https://news.google.com/rss/articles/abc", MentionSource.news_rss),
    ("https://news.google.com/articles/abc", MentionSource.gdelt),
    ("https://WWW.BIT.LY/abc", MentionSource.scraper),
    ("https://x.com/author/status/1", MentionSource.news_rss),
    ("https://m.facebook.com/page/posts/1", MentionSource.rss_custom),
])
def test_zero_is_not_low_truth_for_unidentified_non_newsroom_or_relay(session, url, source):
    owner = _client(session)
    publication = _mention(session, owner, url, source=source)
    facts = build_digest_facts(session, client_id=owner, day=DAY, tz=TZ)
    item = facts["noticias"][0]
    assert item["media_diversity"] == {"identified_outlet_count": 0}
    assert item["veracity"] == "not_evaluated"
    assert item["source_refs"] == [0]
    assert facts["evidence"] == freeze_sources([publication])


def test_diversity_excludes_aggregate_foreign_story_tenant_and_window(session):
    owner = _client(session)
    event = _event(session, owner, "Historia propia")
    own = _mention(session, owner, "https://own.test/1", event_id=event.id)
    aggregate = _mention(session, owner, "https://portada.test/1", event_id=event.id,
                         title="Esta es la PORTADA de @Medio")
    other = _mention(session, owner, "https://other.test/1")
    _mention(session, owner, "https://outside.test/1", published_at=NOON - timedelta(days=2))
    from app.models import Client
    foreign = Client(name="foreign")
    session.add(foreign)
    session.flush()
    _mention(session, foreign.id, "https://foreign.test/1")
    facts = build_digest_facts(session, client_id=owner, day=DAY, tz=TZ)
    story = next(item for item in facts["noticias"] if item["event_id"] == event.id)
    assert story["media_diversity"] == {"identified_outlet_count": 1}
    assert story["source_refs"] == [0]
    assert len(story["sources"]) == 2
    assert facts["evidence"] == freeze_sources([own, aggregate, other])


@pytest.mark.parametrize("mutation", [
    {"indicators_version": None}, {"indicators_version": True},
    {"indicators_version": "1"}, {"indicators_version": 2},
    {"media_diversity": None}, {"media_diversity": {}},
    *[{"media_diversity": {"identified_outlet_count": count}} for count in
      (True, "3", -1, 0.5, float("inf"), float("nan"))],
    {"veracity": "verified"}, {"veracity": None},
    {"missing": "indicators_version"}, {"missing": "media_diversity"},
    {"missing": "veracity"},
])
def test_new_export_and_validation_never_fall_back_to_high_confidence(mutation):
    item = {"title": "Historia", "summary": "Reseña.", "confidence": "alta",
            "confidence_note": "Observación válida.", "sources": [],
            "media_diversity": {"identified_outlet_count": 0}, "veracity": "not_evaluated"}
    content = {"schema": 2, "indicators_version": 1, "noticias": [item],
               "coverage": {}, "redes": {}, "personas": [], "pendientes": []}
    key = mutation.get("missing")
    if key:
        (content if key == "indicators_version" else item).pop(key)
    else:
        for key, value in mutation.items():
            (content if key == "indicators_version" else item)[key] = value
    assert validate_digest(content)
    plain = render_plain_text(content, "Titular")
    assert "Diversidad de medios: no disponible" in plain
    assert "Veracidad no evaluada" in plain
    assert "[alta]" not in plain
    assert "Nota del análisis: Observación válida. [No respaldada]" in plain


def test_zero_export_and_legacy_export_are_explicit_distinct_branches():
    legacy = {"noticias": [{"title": "Historia", "summary": "Reseña.",
               "confidence": "alta", "confidence_note": "Nota antigua.", "sources": []}]}
    old_plain = render_plain_text(legacy, "Titular")
    assert "- [alta] Historia\n  Reseña. [No respaldada] (Nota antigua. [No respaldada])" in old_plain
    assert "Diversidad" not in old_plain
    legacy["indicators_version"] = 1
    legacy["noticias"][0].update(media_diversity={"identified_outlet_count": 0}, veracity="not_evaluated")
    new_plain = render_plain_text(legacy, "Titular")
    assert "Diversidad de medios: 0 medios identificados" in new_plain
    assert "Veracidad no evaluada" in new_plain
    assert "[alta]" not in new_plain
    assert "Nota del análisis: Nota antigua. [No respaldada]" in new_plain


@pytest.mark.parametrize("references,state", [({}, "unbacked"), ({"items.0.confidence_note": [0]}, "linked")])
def test_public_generation_projects_metrics_not_truth_and_retains_optional_note(session, references, state):
    import json

    owner = _client(session)
    article = _mention(session, owner, "https://publisher.test/1")
    frozen = freeze_sources([article])

    def generate(prompt):
        view = json.loads(prompt.split("\n", 1)[1])
        assert view["indicators_version"] == 1
        assert view["noticias"][0]["media_diversity"] == {"identified_outlet_count": 1}
        assert view["noticias"][0]["veracity"] == "not_evaluated"
        assert "confidence" not in view["noticias"][0]
        assert "datos verificados" not in prompt
        assert "HECHOS verificados" not in SYSTEM_PROMPT
        assert "justifica la confianza" not in SYSTEM_PROMPT
        return json.dumps({
            "headline": "Síntesis válida.", "indicators_version": 99,
            "items": [{"index": 0, "summary": "Prosa válida sin cita.",
                       "confidence_note": "Observación del análisis.",
                       "confidence": "alta", "media_diversity": {"identified_outlet_count": 999},
                       "veracity": "verified"}], "references": references,
        })

    row = build_daily_summary(session, client_id=owner, day=DAY, generate=generate)
    assert row.mode == "llm"
    content = row.content
    item, card = content["noticias"][0], content["tarjetas"][0]
    assert content["evidence"] == frozen
    assert content["indicators_version"] == 1
    for target in (item, card):
        assert target["media_diversity"] == {"identified_outlet_count": 1}
        assert target["veracity"] == "not_evaluated"
        assert "confidence" not in target
        assert target["confidence_note"] == "Observación del análisis."
        assert resolved_provenance(content, target, "confidence_note", allowed=[0])["state"] == state
    assert item["summary"] == "Prosa válida sin cita."
    assert "Nota del análisis: Observación del análisis." in content["plain_text"]


@pytest.mark.parametrize("legacy,changed", [(True, False), (False, False), (True, True)])
def test_recovery_keeps_fresh_metrics_and_compatible_prose_not_old_levels(session, legacy, changed):
    import copy
    import json

    owner = _client(session)
    article = _mention(session, owner, "https://publisher.test/recovery")
    row = build_daily_summary(session, client_id=owner, day=DAY, generate=lambda prompt: json.dumps({
        "headline": "Síntesis recuperable.",
        "items": [{"index": 0, "summary": "Prosa recuperable.", "confidence_note": "Nota recuperable."}],
        "seleccion": [{"index": 0, "categoria": "decision", "razon": "Razón recuperable."}],
        "references": {"items.0.confidence_note": [0], "seleccion.0.razon": [0]},
    }))
    previous = copy.deepcopy(row.content)
    if legacy:
        previous.pop("indicators_version")
        for target in previous["noticias"] + previous["tarjetas"]:
            target.pop("media_diversity")
            target.pop("veracity")
            target["confidence"] = "alta"
        row.content = previous
        session.commit()
    if changed:
        article.content = "Material cambiado."
        session.commit()
    result = build_daily_summary(session, client_id=owner, day=DAY, generate=lambda prompt: "invalid json")
    assert result.content["indicators_version"] == 1
    for target in (result.content["noticias"][0], result.content["tarjetas"][0]):
        assert target["media_diversity"] == {"identified_outlet_count": 1}
        assert target["veracity"] == "not_evaluated"
        assert "confidence" not in target
    if changed:
        assert result.mode == "heuristic"
        assert "Prosa recuperable." not in result.content["plain_text"]
    else:
        assert result.mode == "llm"
        assert result.narrative == "Síntesis recuperable."
        item = result.content["noticias"][0]
        assert item["summary"] == "Prosa recuperable."
        assert resolved_provenance(result.content, item, "confidence_note", allowed=[0])["source_refs"] == [0]
        assert result.content["brief"]["decisiones"][0]["razon"] == "Razón recuperable."
        assert result.content["evidence"] == previous["evidence"]


def test_public_compilation_keeps_each_bullets_media_count_including_zero(session):
    import json

    owner = _client(session)
    for index in range(11):
        _mention(session, owner, f"https://same.test/{index}", title=f"Historia {index}",
                 source=MentionSource.x_twitter if index == 9 else MentionSource.news_rss)
    row = build_daily_summary(session, client_id=owner, day=DAY, generate=lambda prompt: json.dumps({
        "headline": "Síntesis.", "seleccion": [{"index": 10, "categoria": "decision"}],
    }))
    content = row.content
    compiled = content["tarjetas"][-1]
    assert compiled["notas_refs"] == [{"source_refs": [i], "material_ref": i} for i in (7, 8, 9)]
    assert [entry["media_diversity"]["identified_outlet_count"] for entry in compiled["notas_indicators"]] == [1, 1, 0]
    assert "media_diversity" not in compiled
    assert content["tarjetas"][1]["material_ref"] == 0
    assert content["tarjetas"][1]["media_diversity"] == {"identified_outlet_count": 1}
    assert validate_digest(content) == []
