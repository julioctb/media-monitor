"""Public builder regressions for the S22 factual boundary."""

import copy
import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.models import AgendaItem, Client, DailySummaryRevision, MentionSource, queries
from app.settings_runtime import EffectiveSettings
from app.summaries import build_daily_summary, builder
from app.summaries.provider_contract import RequestBudget, RequestBudgetExhausted
from tests.digest_plan_fixtures import (
    advisory_completion,
    review_completion,
    reviewed_factory,
)
from tests.test_summaries import api as api  # noqa: PLC0414 - pytest fixture re-export

DAY = datetime(2026, 10, 10, 18, tzinfo=UTC)


def _material(session):
    client = Client(name="Factual pipeline fixture")
    session.add(client)
    session.commit()
    mention = queries.insert_mention(
        session,
        client_id=client.id,
        source=MentionSource.news_rss,
        url="https://fixture.invalid/mural-source",
        title="Develan mural en una sede regional",
        published_at=DAY,
    )
    assert mention is not None
    mention.content = "Estudiantes realizaron un mural. El acto reunió a autoridades."
    mention.summary = (
        "Resumen derivado: la universidad develó el 10 de octubre el mural."
    )
    mention.author = None
    session.commit()
    session.refresh(mention)
    return client, mention


def _plan(prompt):
    return json.loads(advisory_completion(prompt, [(0, "decision")], item_indexes=[0]))


@pytest.mark.parametrize(
    "corruption", [None, "duplicate_story", "foreign_source", "missing_passage"]
)
def test_public_factory_sends_scoped_choices_and_one_contextual_schema(
    session, monkeypatch, corruption
):
    client, _ = _material(session)
    second = queries.insert_mention(
        session,
        client_id=client.id,
        source=MentionSource.news_rss,
        url="https://fixture.invalid/mobility-source",
        title="Convenio de movilidad entre instituciones",
        published_at=DAY,
    )
    assert second is not None
    second.content = "Se anunció un intercambio académico entre instituciones."
    settings = queries.get_settings(session, client.id)
    settings.ai_provider = "openai"
    settings.ai_api_key = "fixture-only"
    settings.ai_base_url = "https://fixture.invalid/v1"
    settings.ai_model = "fixture"
    session.commit()
    calls = []

    def respond(url, **options):
        calls.append(copy.deepcopy(options))
        request = httpx.Request("POST", url)
        if len(calls) == 1:
            return httpx.Response(
                400, request=request, json={"error": "plain required"}
            )
        prompt = options["json"]["messages"][1]["content"]
        plan = _plan(prompt)
        if corruption == "duplicate_story":
            plan["items"].append(copy.deepcopy(plan["items"][0]))
        elif corruption == "foreign_source":
            packet = json.loads(prompt)
            plan["items"][0]["source_ref"] = packet["stories"][1]["source_refs"][0]
        elif corruption == "missing_passage":
            plan["items"][0]["passage_index"] = 6
        raw = json.dumps(plan)
        emitted.append(raw)
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": raw}}]},
        )

    emitted = []
    monkeypatch.setattr(builder.httpx, "post", respond)
    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    # Both planning attempts are consumed: a valid plan is not review approval.
    assert row.mode == "heuristic"
    assert row.content["generation"]["status"] == "source_fallback"
    assert row.content["generation"]["raw_proposal"] == emitted[0]
    assert row.content["generation"]["plan"] is None
    assert row.content["brief"]["decisiones"] == []
    assert len(calls) == row.content["generation"]["physical_requests"] == 2
    packet = json.loads(calls[0]["json"]["messages"][1]["content"])
    assert len(packet["stories"]) == 2
    schema = calls[0]["json"]["response_format"]["json_schema"]["schema"]
    assert (
        schema["properties"]["basis_fingerprint"].get("const")
        == packet["basis_fingerprint"]
    )
    assert schema["properties"]["items"]["type"] == "object"
    assert set(schema["properties"]["items"]["properties"]) == {"0", "1"}
    assert schema["properties"]["items"]["additionalProperties"] is False
    assert schema["properties"]["seleccion"]["maxItems"] == 2
    assert schema["$defs"]["_Pick"]["properties"]["index"]["enum"] == [0, 1]
    branches = [
        branch
        for slot in schema["properties"]["items"]["properties"].values()
        for branch in slot["anyOf"]
    ]
    actual = {
        (
            branch["properties"]["index"]["const"],
            branch["properties"]["source_ref"]["const"],
            passage,
        )
        for branch in branches
        for passage in branch["properties"]["passage_index"]["enum"]
    }
    expected = {
        (story["index"], ref, passage)
        for story in packet["stories"]
        for ref in story["source_refs"]
        for passage in range(len(packet["sources"][ref]["passages"]))
    }
    assert actual == expected
    for story in packet["stories"]:
        assert story["title"] == packet["sources"][story["material_ref"]]["title"]
        assert story["source_choices"] == [
            {
                "source_ref": ref,
                "passage_indices": list(range(len(packet["sources"][ref]["passages"]))),
            }
            for ref in story["source_refs"]
        ]
    for call in calls:
        assert (
            json.loads(call["json"]["messages"][1]["content"])["response_schema"]
            == schema
        )
        assert call["timeout"] == 120.0
        assert call["follow_redirects"] is False
        assert call["json"]["model"] == "fixture"
        assert "No renumeres" in call["json"]["messages"][0]["content"]
        assert "un solo pasaje por noticia" in call["json"]["messages"][0]["content"]


def test_headline_projections_match_the_accepted_code_owned_headline(session):
    client, _ = _material(session)
    row = build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        generator_factory=reviewed_factory(lambda prompt: json.dumps(_plan(prompt))),
    )
    assert row.mode == "llm"
    assert row.content["generation"]["status"] == "plan_applied"
    assert row.content.get("headline") == row.narrative
    assert row.content["brief"]["headline"] == row.narrative


def _origins(value):
    if isinstance(value, list):
        return [origin for item in value for origin in _origins(item)]
    if isinstance(value, dict):
        return ([value["origin"]] if "origin" in value else []) + [
            origin for item in value.values() for origin in _origins(item)
        ]
    return []


def test_rendered_facts_are_code_owned_but_advice_remains_model_authored(session):
    client, _ = _material(session)
    row = build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        generator_factory=reviewed_factory(lambda prompt: json.dumps(_plan(prompt))),
    )
    assert row.mode == "llm"
    origins = _origins(row.content["brief"])
    assert origins
    assert "model_output" in origins
    assert row.content["noticias"][0]["provenance"]["summary"]["origin"] == "derived"
    assert row.content["provenance"]["headline"]["origin"] == "model_output"


def test_saved_plan_uses_its_input_namespace_and_can_be_rerendered(session):
    client, _ = _material(session)
    queries.insert_mention(
        session,
        client_id=client.id,
        source=MentionSource.news_rss,
        url="https://fixture.invalid/second",
        title="Otra publicación",
        published_at=DAY.replace(minute=1),
    )

    def choose_second(prompt):
        return advisory_completion(
            prompt, [(1, "decision")], headline_index=1, item_indexes=[0]
        )

    row = build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        generator_factory=reviewed_factory(choose_second),
    )
    assert row.mode == "llm"
    assert "factual_basis" not in row.content
    receipt = row.content["generation"]
    assert receipt["input_basis"]["fingerprint"] == receipt["plan"]["basis_fingerprint"]
    assert receipt["plan"] == json.loads(receipt["raw_proposal"])
    previous_headline = row.narrative

    def unavailable(_):
        raise RuntimeError("fixture provider unavailable")

    recovered = build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=unavailable
    )
    assert recovered.mode == "llm"
    assert recovered.content["generation"]["status"] == "plan_recovered"
    assert recovered.narrative == previous_headline
    assert recovered.content["generation"]["plan"] == receipt["plan"]


def test_new_generation_never_invokes_agenda_source_mutation(session, monkeypatch):
    from app.summaries import agenda_detect

    client, _ = _material(session)
    session.add(
        AgendaItem(
            client_id=client.id,
            title="Registro manual protegido",
            kind="activity",
            event_date=DAY.date(),
            date_label="10 octubre 2026",
        )
    )
    session.commit()
    before = list(session.execute(select(*AgendaItem.__table__.c)))
    real_sync = agenda_detect.sync_agenda_from_digest
    calls = []

    def observed_sync(*args, **kwargs):
        calls.append(True)
        return real_sync(*args, **kwargs)

    monkeypatch.setattr(agenda_detect, "sync_agenda_from_digest", observed_sync)
    row = build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        generator_factory=reviewed_factory(lambda prompt: json.dumps(_plan(prompt))),
    )
    assert row.content["generation"]["agenda_promotion_allowed"] is False
    assert calls == []
    assert list(session.execute(select(*AgendaItem.__table__.c))) == before


def test_physical_factory_shared_budget_control(monkeypatch):
    calls = []

    def unavailable(url, **kwargs):
        calls.append((url, kwargs))
        raise httpx.ConnectError("isolated transport fixture")

    monkeypatch.setattr(builder.httpx, "post", unavailable)
    cfg = EffectiveSettings(
        client_id=1,
        ai_base_url="https://fixture.invalid/v1",
        ai_model="fixture",
        ai_api_key="fixture-only",
    )
    budget = RequestBudget()
    generate = builder._openai_generator(
        cfg,
        budget=budget,
        system_prompt="fixture-system",
        response_schema={"type": "object"},
    )
    with pytest.raises(RuntimeError, match="summary ll failed after 2 attempts"):
        generate("fixture")
    with pytest.raises(RequestBudgetExhausted):
        generate("second phase cannot reset its budget")
    assert budget.used == 2
    assert len(calls) == 2
    assert [options["timeout"] for _, options in calls] == [120.0, 120.0]
    assert all(options["follow_redirects"] is False for _, options in calls)
    assert calls[0][1]["json"]["messages"][0]["content"] == "fixture-system"
    assert "response_format" in calls[0][1]["json"]
    assert "response_format" not in calls[1][1]["json"]


def test_legacy_factory_preservation_control(monkeypatch):
    calls = []

    def unavailable(url, **kwargs):
        calls.append(kwargs)
        raise httpx.ConnectError("isolated transport fixture")

    monkeypatch.setattr(builder.httpx, "post", unavailable)
    cfg = EffectiveSettings(
        client_id=1,
        ai_base_url="https://fixture.invalid/v1",
        ai_model="fixture",
        ai_api_key="fixture-only",
    )
    with pytest.raises(RuntimeError, match="summary ll failed after 2 attempts"):
        builder._openai_generator(cfg)("fixture")
    assert len(calls) == 2
    assert [options["timeout"] for options in calls] == [60, 60]
    assert all("follow_redirects" not in options for options in calls)
    assert "response_format" in calls[0]["json"]
    assert "response_format" not in calls[1]["json"]


@pytest.mark.parametrize(
    "corruption",
    [
        "free_rationale",
        "foreign_reference",
        "boolean_index",
        "duplicate_key",
        "malformed",
    ],
)
def test_rejected_proposals_are_retained_but_not_adopted_control(session, corruption):
    client, _ = _material(session)
    sent = []

    def produce(prompt):
        proposal = _plan(prompt)
        if corruption == "free_rationale":
            proposal["seleccion"][0]["razon"] = (
                "Los tres principales cargos operativos asumieron un compromiso."
            )
        elif corruption == "foreign_reference":
            proposal["items"][0]["source_ref"] = 999
        elif corruption == "boolean_index":
            proposal["headline_index"] = True
        raw = json.dumps(proposal)
        if corruption == "duplicate_key":
            raw = raw[:-1] + ', "headline_index": 0}'
        elif corruption == "malformed":
            raw = "not a JSON object"
        sent.append(raw)
        return raw

    row = build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=produce
    )
    assert row.mode == "heuristic"
    assert row.content["generation"]["status"] == "source_fallback"
    assert row.content["generation"]["raw_proposal"] == sent[0]
    assert row.content["agenda"] == []
    assert "Estudiantes realizaron un mural" in row.content["noticias"][0]["summary"]
    assert "tres principales" not in row.narrative
    assert "compromiso" not in row.content["noticias"][0]["summary"]


def test_restoring_legacy_prose_invalidates_new_plan_receipt(api):
    http, db = api
    client, _ = _material(db)
    row = build_daily_summary(
        db,
        client_id=client.id,
        day=DAY.date(),
        generator_factory=reviewed_factory(lambda prompt: json.dumps(_plan(prompt))),
    )
    before = copy.deepcopy(row.content)
    restored_text = "Texto histórico sin referencias: se conserva sin certificarlo."
    db.add(
        DailySummaryRevision(
            client_id=client.id,
            summary_date=DAY.date(),
            seq=2,
            narrative=restored_text,
            mode="llm",
        )
    )
    db.commit()
    response = http.post(
        f"/api/clients/{client.id}/summary-revisions/restore",
        json={"day": DAY.date().isoformat(), "seq": 2},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["narrative"] == restored_text
    receipt = result["content"]["generation"]
    assert receipt["status"] == "revision_restored"
    assert receipt["plan"] is None
    assert receipt["prior_generation"] == before["generation"]
    assert result["content"]["headline"] == restored_text
    assert result["content"]["brief"]["headline"] == restored_text
    for field in ("noticias", "evidence", "agenda", "redes", "personas"):
        assert result["content"][field] == before[field]
    assert result["content"]["provenance"]["headline"]["origin"] == "revision_restore"
    assert result["content"]["provenance"]["headline"]["source_refs"] == []
    repeated = http.post(
        f"/api/clients/{client.id}/summary-revisions/restore",
        json={"day": DAY.date().isoformat(), "seq": 2},
    )
    assert repeated.status_code == 200
    assert repeated.json()["content"]["generation"] == receipt


def test_plain_provider_retry_receives_the_same_closed_plan_contract(
    session, monkeypatch
):
    client, _ = _material(session)
    settings = queries.get_settings(session, client.id)
    settings.ai_provider = "openai"
    settings.ai_api_key = "fixture-only"
    settings.ai_base_url = "https://fixture.invalid/v1"
    settings.ai_model = "fixture"
    session.commit()
    calls = []

    def respond(url, **options):
        calls.append(copy.deepcopy(options))
        request = httpx.Request("POST", url)
        if len(calls) == 1:
            return httpx.Response(
                400, request=request, json={"error": "unsupported guided format"}
            )
        prompt = options["json"]["messages"][1]["content"]
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": json.dumps(_plan(prompt))}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "heuristic"
    assert row.content["generation"]["review"]["status"] == "unavailable"
    assert len(calls) == 2
    assert row.content["generation"]["physical_requests"] == 2
    assert "response_format" in calls[0]["json"]
    assert "response_format" not in calls[1]["json"]
    for call in calls:
        packet = json.loads(call["json"]["messages"][1]["content"])
        expected_schema = calls[0]["json"]["response_format"]["json_schema"]["schema"]
        assert packet.get("response_schema") == expected_schema
        assert (
            expected_schema["properties"]["basis_fingerprint"]["const"]
            == packet["basis_fingerprint"]
        )
        assert expected_schema["properties"]["items"]["type"] == "object"
        assert set(expected_schema["properties"]["items"]["properties"]) == {"0"}
        assert expected_schema["properties"]["items"]["additionalProperties"] is False
        assert expected_schema["$defs"]["_Pick"]["properties"]["index"]["enum"] == [0]
        assert call["timeout"] == 120.0
        assert call["follow_redirects"] is False
        for rule in (
            "mínimo tres decisiones cuando existan al menos tres candidatas sustantivas",
            "sin rellenar con ceremonias o difusión",
            "no es necesariamente lector, protagonista, afectado ni responsable",
            "no atribuyas facultades de gobierno a una candidatura",
            "Sin focus_person",
            "atribución y la negación",
            "sin propaganda",
        ):
            assert rule in call["json"]["messages"][0]["content"]


@pytest.mark.parametrize("closed", [False, True])
def test_factual_http_preserves_raw_fences_without_repair(session, monkeypatch, closed):
    client, _ = _material(session)
    settings = queries.get_settings(session, client.id)
    settings.ai_provider = "openai"
    settings.ai_api_key = "fixture-only"
    settings.ai_base_url = "https://fixture.invalid/v1"
    settings.ai_model = "fixture"
    session.commit()
    emitted = []

    def respond(url, **options):
        prompt = options["json"]["messages"][1]["content"]
        raw = (
            review_completion(prompt)
            if "scope" in json.loads(prompt)
            else "```json\n" + json.dumps(_plan(prompt)) + ("\n```" if closed else "")
        )
        emitted.append(raw)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": raw}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert len(emitted) == (2 if closed else 1)
    assert row.mode == ("llm" if closed else "heuristic")
    assert row.content["generation"]["status"] == (
        "plan_applied" if closed else "source_fallback"
    )
    assert row.content["generation"]["raw_proposal"] == emitted[0]
    assert row.content["generation"]["physical_requests"] == (2 if closed else 1)


@pytest.mark.parametrize(
    "source,label",
    [
        ("news_rss", "noticias por RSS"),
        ("x_twitter", "X"),
        ("facebook_page", "Facebook"),
        ("unfamiliar_channel", "Unfamiliar Channel"),
    ],
)
def test_source_only_headline_uses_spanish_channel_labels(source, label):
    headline = builder._heuristic_headline(DAY.date(), 2, [], {source: 2})
    assert f"La fuente con más notas fue {label}." in headline
    assert source not in headline or source == label


def test_publication_day_cannot_become_an_accepted_act_date(session):
    client, mention = _material(session)
    original = (mention.title, mention.content, mention.summary, mention.published_at)
    invented = "La universidad develó el 10 de octubre el mural."
    payload = {"headline": invented, "items": [{"index": 0, "summary": invented}]}

    row = build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        generate=lambda _: json.dumps(payload),
    )

    assert "develó el 10 de octubre" not in row.narrative
    assert "develó el 10 de octubre" not in row.content["noticias"][0]["summary"]
    assert row.mode == "heuristic"
    assert row.content["generation"]["status"] == "source_fallback"
    session.refresh(mention)
    assert (
        mention.title,
        mention.content,
        mention.summary,
        mention.published_at,
    ) == original
