"""Synthetic mechanism probes, not real-model semantic-quality certification."""

import copy
import json

import httpx
import pytest

from app.models import MentionSource, queries
from app.summaries import builder
from tests import test_api as api_fixtures
from tests.test_digest_factual_pipeline import DAY, _material, _plan

reviewer_db = (
    api_fixtures.db
)  # Reuse the file-SQLite fixture across TestClient threads.


def contextual_plan(prompt):
    plan = _plan(prompt)
    analysis = {
        "premises": [copy.deepcopy(plan["items"][0])],
        "interpretation": "La participación estudiantil puede abrir interlocución institucional.",
        "consequence": "Si hay continuidad, podría ampliarse el diálogo sobre proyectos culturales.",
        "attention": "Observar si se documentan nuevas propuestas de participación.",
        "conditions": "La presencia de autoridades no acredita compromisos ni respaldo público.",
        "relevance": "La vinculación con estudiantes puede ser pertinente, sin presumir responsabilidades del perfil monitoreado.",
    }
    plan["headline_analysis"] = analysis
    plan["seleccion"][0]["analysis"] = copy.deepcopy(analysis)
    return plan


def passed_review(packet):
    return {
        "input_fingerprint": packet["input_fingerprint"],
        "passed": True,
        "checks": {key: True for key in packet["required_checks"]},
        "assessments": [
            {
                "path": path,
                "passed": True,
                "reason": "Caso sintético conforme dentro del material suministrado.",
            }
            for path in packet["scope"]
        ],
    }


def configure(session, client):
    settings = queries.get_settings(session, client.id)
    settings.ai_provider = "openai"
    settings.ai_api_key = "fixture-only"
    settings.ai_base_url = "https://fixture.invalid/v1"
    settings.ai_model = "fixture"
    session.commit()


def configure_reviewer(session, client, **changes):
    return queries.upsert_settings(
        session,
        client.id,
        {
            "digest_reviewer_provider": "openai",
            "digest_reviewer_base_url": "https://reviewer-fixture.invalid/v1",
            "digest_reviewer_model": "reviewer-fixture-model",
            "digest_reviewer_api_key": "synthetic-reviewer-key-only",
            **changes,
        },
    )


def wire_response(url, options):
    packet = json.loads(options["json"]["messages"][1]["content"])
    value = (
        passed_review(packet)
        if "scope" in packet
        else contextual_plan(json.dumps(packet))
    )
    return httpx.Response(
        200,
        request=httpx.Request("POST", url),
        json={"choices": [{"message": {"content": json.dumps(value)}}]},
    )


@pytest.mark.parametrize("custom_factory", [False, True])
def test_dedicated_reviewer_routes_only_review_with_shared_budget(
    session, monkeypatch, custom_factory
):
    client, _ = _material(session)
    configure(session, client)
    configured = configure_reviewer(session, client)
    calls, phases = [], []

    def respond(url, **options):
        calls.append((url, copy.deepcopy(options)))
        return wire_response(url, options)

    def factory(effective, *, phase, **options):
        phases.append((phase, effective, options["budget"]))
        return builder.summary_generator(effective, **options)

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        **({"generator_factory": factory} if custom_factory else {}),
    )
    assert row.mode == "llm"
    assert row.content["generation"]["review"]["status"] == "passed"
    assert len(calls) == row.content["generation"]["physical_requests"] == 2
    assert [
        (url, options["json"]["model"], options["headers"]) for url, options in calls
    ] == [
        (
            "https://fixture.invalid/v1/chat/completions",
            "fixture",
            {"Authorization": "Bearer fixture-only"},
        ),
        (
            "https://reviewer-fixture.invalid/v1/chat/completions",
            "reviewer-fixture-model",
            {"Authorization": "Bearer synthetic-reviewer-key-only"},
        ),
    ]
    assert all(
        options["timeout"] == 120.0 and options["follow_redirects"] is False
        for _, options in calls
    )
    if custom_factory:
        assert [phase for phase, _, _ in phases] == ["proposal", "review"]
        assert phases[0][2] is phases[1][2]
        assert phases[0][1] is not phases[1][1]
        assert phases[0][1].ai_model == "fixture"
        assert phases[1][1].ai_model == "reviewer-fixture-model"
    assert (
        row.content["generation"]["reviewer_revision"]
        == configured.digest_reviewer_revision
    )
    serialized = json.dumps(row.content)
    assert "synthetic-reviewer-key-only" not in serialized
    assert "fixture-only" not in serialized
    assert set(row.content["generation"]["review"]) == {
        "method",
        "status",
        "input_fingerprint",
        "scope",
        "raw_review",
        "error",
        "fallible",
        "external_truth",
    }


@pytest.mark.parametrize("missing", ["base_url", "model", "api_key", "unknown_mode"])
@pytest.mark.parametrize("custom_factory", [False, True])
def test_incomplete_reviewer_never_borrows_generator_or_calls_factory(
    session, monkeypatch, missing, custom_factory
):
    client, _ = _material(session)
    configure(session, client)
    changes = {"digest_reviewer_" + missing: None} if missing != "unknown_mode" else {}
    settings = configure_reviewer(session, client, **changes)
    if missing == "unknown_mode":
        settings.digest_reviewer_provider = "unrecognized"
        session.commit()
    calls, phases = [], []

    def respond(url, **options):
        calls.append(url)
        return wire_response(url, options)

    def factory(effective, *, phase, **options):
        phases.append(phase)
        return builder.summary_generator(effective, **options)

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        **({"generator_factory": factory} if custom_factory else {}),
    )
    assert row.mode == "heuristic"
    assert row.content["generation"]["review"]["status"] == "unavailable"
    assert calls == ["https://fixture.invalid/v1/chat/completions"]
    assert phases == (["proposal"] if custom_factory else [])
    assert row.content["brief"]["decisiones"] == []
    delivered = copy.deepcopy(row.content)
    control = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=lambda _: None
    )
    assert {key: value for key, value in delivered.items() if key != "generation"} == {
        key: value for key, value in control.content.items() if key != "generation"
    }
    assert calls == ["https://fixture.invalid/v1/chat/completions"]


@pytest.mark.parametrize("failure", ["unavailable", "rejected", "proposal_retry"])
def test_dedicated_review_failure_never_dispatches_third_request(
    session, monkeypatch, failure
):
    client, _ = _material(session)
    configure(session, client)
    configure_reviewer(session, client)
    calls = []

    def respond(url, **options):
        calls.append((url, copy.deepcopy(options)))
        if failure == "proposal_retry" and len(calls) == 1:
            return httpx.Response(400, request=httpx.Request("POST", url))
        if "reviewer-fixture" in url:
            if failure == "unavailable":
                raise httpx.ConnectError("Synthetic reviewer unavailable")
            packet = json.loads(options["json"]["messages"][1]["content"])
            review = passed_review(packet)
            review["passed"] = False
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={"choices": [{"message": {"content": json.dumps(review)}}]},
            )
        return wire_response(url, options)

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "heuristic"
    assert len(calls) == row.content["generation"]["physical_requests"] == 2
    assert [url for url, _ in calls] == [
        "https://fixture.invalid/v1/chat/completions",
        (
            "https://fixture.invalid/v1/chat/completions"
            if failure == "proposal_retry"
            else "https://reviewer-fixture.invalid/v1/chat/completions"
        ),
    ]
    assert row.content["generation"]["review"]["status"] == (
        "rejected" if failure == "rejected" else "unavailable"
    )
    assert row.content["brief"]["decisiones"] == []
    delivered = copy.deepcopy(row.content)
    control = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=lambda _: None
    )
    assert {key: value for key, value in delivered.items() if key != "generation"} == {
        key: value for key, value in control.content.items() if key != "generation"
    }
    assert len(calls) == 2


@pytest.mark.parametrize(
    "mode,change,recover",
    [
        ("openai", "same", True),
        ("openai", "blank_key", True),
        ("openai", "key", False),
        ("openai", "model", False),
        ("openai", "url", False),
        ("openai", "mode", False),
        ("openai", "unmarked", False),
        ("openai", "generator", True),
        ("inherit", "same", True),
        ("inherit", "unmarked", True),
        ("inherit", "key", False),
        ("inherit", "model", False),
        ("inherit", "url", False),
        ("inherit", "mode", False),
        ("inherit", "fast_model", True),
    ],
)
def test_recovery_is_bound_to_effective_reviewer_revision(
    reviewer_db, monkeypatch, mode, change, recover
):
    from fastapi.testclient import TestClient

    from app.api.deps import get_client_id
    from app.db import get_db
    from app.main import create_app

    session = reviewer_db
    client, _ = _material(session)
    configure(session, client)
    if mode == "openai":
        configure_reviewer(session, client)
    calls = []

    def respond(url, **options):
        calls.append(url)
        return wire_response(url, options)

    monkeypatch.setattr(builder.httpx, "post", respond)
    first = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert first.mode == "llm"
    original = copy.deepcopy(first.content["generation"])
    initial_revision = queries.get_settings(session, client.id).digest_reviewer_revision
    changes = {}
    prefix = "digest_reviewer_" if mode == "openai" else "ai_"
    if change in {"key", "model", "url"}:
        field, value = {
            "key": ("api_key", "synthetic-replaced-secret-only"),
            "model": ("model", "replacement-fixture-model"),
            "url": ("base_url", "https://replacement-fixture.invalid/v1"),
        }[change]
        changes[prefix + field] = value
    elif change == "mode":
        changes = (
            {"digest_reviewer_provider": "inherit"}
            if mode == "openai"
            else {"ai_provider": "local"}
        )
    elif change == "generator":
        changes = {"ai_model": "other-generator-fixture"}
    elif change == "fast_model":
        changes = {"ai_model_fast": "other-fast-fixture"}
    elif change == "blank_key":
        changes = {"digest_reviewer_api_key": "  "}
    elif change == "same":
        changes = {
            prefix + "model": "reviewer-fixture-model"
            if mode == "openai"
            else "fixture"
        }
    elif change == "unmarked":
        edited = copy.deepcopy(first.content)
        edited["generation"].pop("reviewer_revision", None)
        first.content = edited
        session.commit()

    app = create_app()

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_client_id] = lambda: client.id
    with TestClient(app) as api:
        response = api.put("/api/settings", json=changes)
        assert response.status_code == 200
    revision = queries.get_settings(session, client.id).digest_reviewer_revision
    if change != "unmarked":
        assert (revision == initial_revision) is recover

    def unavailable(_):
        raise RuntimeError("Synthetic proposal unavailable")

    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=unavailable
    )
    assert (row.mode == "llm") is recover
    assert row.content["generation"]["status"] == (
        "plan_recovered" if recover else "source_fallback"
    )
    assert calls == [
        "https://fixture.invalid/v1/chat/completions",
        (
            "https://reviewer-fixture.invalid/v1/chat/completions"
            if mode == "openai"
            else "https://fixture.invalid/v1/chat/completions"
        ),
    ]
    assert row.content["generation"]["prior_generation"]["review"] == original["review"]
    if recover:
        assert row.content["generation"]["review"] == original["review"]
    else:
        assert row.content["brief"]["decisiones"] == []
        assert row.content["generation"]["plan"] is None
    assert "synthetic-replaced-secret-only" not in json.dumps(row.content)


def test_public_pipeline_reviews_actual_compiled_candidate_with_shared_budget(
    session, monkeypatch
):
    from app.models import DailySummary, DailySummaryRevision
    from tests.test_political_analysis_regeneration import snapshot_tables

    client, mention = _material(session)
    before = (mention.title, mention.content, mention.summary, mention.published_at)
    configure(session, client)
    table_preimages = snapshot_tables(session)
    calls, outputs = [], []

    def respond(url, **options):
        calls.append(copy.deepcopy(options))
        packet = json.loads(options["json"]["messages"][1]["content"])
        result = (
            contextual_plan(json.dumps(packet))
            if len(calls) == 1
            else passed_review(packet)
        )
        raw = json.dumps(result, ensure_ascii=False)
        outputs.append(raw)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": raw}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "llm"
    assert len(calls) == row.content["generation"]["physical_requests"] == 2
    receipt = row.content["generation"]["review"]
    assert receipt["status"] == "passed"
    assert receipt["raw_review"] == outputs[1]
    assert row.content["generation"]["raw_proposal"] == outputs[0]
    packet = json.loads(calls[1]["json"]["messages"][1]["content"])
    assert packet["candidate"]["tarjetas"] == row.content["tarjetas"]
    assert packet["candidate"]["brief"] == row.content["brief"]
    assert packet["candidate"]["plain_text"] == row.content["plain_text"]
    assert "plain_text" in packet["scope"]
    assert any(path.startswith("brief.decisiones") for path in packet["scope"])
    assert all(
        call["timeout"] == 120.0 and call["follow_redirects"] is False for call in calls
    )
    assert all(call["json"]["model"] == "fixture" for call in calls)
    assert "falible" in calls[1]["json"]["messages"][0]["content"]
    assert row.content["provenance"]["headline"]["origin"] == "model_output"
    assert row.content["noticias"][0]["provenance"]["summary"]["origin"] == "derived"
    assert (
        row.content["brief"]["decisiones"][0]["provenance"]["razon"]["origin"]
        == "model_output"
    )
    session.refresh(mention)
    assert (
        mention.title,
        mention.content,
        mention.summary,
        mention.published_at,
    ) == before
    table_postimages = snapshot_tables(session)
    report_tables = {DailySummary.__tablename__, DailySummaryRevision.__tablename__}
    assert {
        name: rows
        for name, rows in table_postimages.items()
        if name not in report_tables
    } == {
        name: rows
        for name, rows in table_preimages.items()
        if name not in report_tables
    }


def test_dedicated_reviewer_guided_mode_reaches_the_wire(session, monkeypatch):
    client, _ = _material(session)
    configure(session, client)
    configure_reviewer(session, client, digest_reviewer_guided_mode="json_object")
    calls = []

    def respond(url, **options):
        calls.append(copy.deepcopy(options))
        packet = json.loads(options["json"]["messages"][1]["content"])
        value = (
            contextual_plan(json.dumps(packet))
            if len(calls) == 1
            else passed_review(packet)
        )
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps(value, ensure_ascii=False)}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "llm" and len(calls) == 2
    # Proposal keeps the strict generator envelope.
    assert calls[0]["json"]["response_format"]["type"] == "json_schema"
    # The dedicated reviewer carries its configured envelope in ONE request.
    assert calls[1]["json"]["response_format"] == {"type": "json_object"}
    assert calls[1]["json"]["model"] == "reviewer-fixture-model"


def test_inherit_reviewer_ignores_stored_guided_mode_on_the_wire(session, monkeypatch):
    client, _ = _material(session)
    configure(session, client)
    configure_reviewer(session, client,
                       digest_reviewer_guided_mode="json_object")  # stored but inert
    from app.models import queries as queries_module
    row = queries_module.get_settings(session, client.id)
    row.digest_reviewer_provider = "inherit"
    session.commit()
    calls = []

    def respond(url, **options):
        calls.append(copy.deepcopy(options))
        packet = json.loads(options["json"]["messages"][1]["content"])
        value = (
            contextual_plan(json.dumps(packet))
            if len(calls) == 1
            else passed_review(packet)
        )
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps(value, ensure_ascii=False)}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    row_result = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row_result.mode == "llm" and len(calls) == 2
    # Inheritance routes BOTH phases through the generator envelope.
    assert all(c["json"]["response_format"]["type"] == "json_schema" for c in calls)


def test_reviewer_guided_mode_selects_the_provider_envelope(monkeypatch):
    from app.settings_runtime import EffectiveSettings
    from app.summaries.builder import summary_generator

    def role_settings():
        return EffectiveSettings(
            client_id=1, ai_provider="openai", ai_api_key="synthetic",
            ai_base_url="https://fixture.invalid/v1", ai_model="fixture",
        )

    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    sent = []

    def respond(url, **options):
        sent.append(options["json"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": "{\"ok\": true}"}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    for mode, expected in (("json_object", {"type": "json_object"}), ("plain", None)):
        sent.clear()
        generate = summary_generator(
            role_settings(), system_prompt="s", response_schema=schema,
            guided_mode=mode,
        )
        assert generate("prompt")
        assert sent[0].get("response_format") == expected, mode
    # Default keeps the strict json_schema path for capable providers.
    sent.clear()
    generate = summary_generator(role_settings(), system_prompt="s", response_schema=schema)
    assert generate("prompt")
    assert sent[0]["response_format"]["type"] == "json_schema"


def test_rejected_review_preserves_the_judged_candidate_for_audit(
    session, monkeypatch
):
    client, _ = _material(session)
    configure(session, client)

    def respond(url, **options):
        packet = json.loads(options["json"]["messages"][1]["content"])
        if "scope" not in packet:
            value = contextual_plan(json.dumps(packet))
        else:
            value = {
                "input_fingerprint": packet["input_fingerprint"],
                "passed": False,
                "checks": {key: key != "attribution" for key in packet["required_checks"]},
                "assessments": [
                    {
                        "path": path,
                        "passed": path != "noticias.0.title",
                        "reason": "Caso sintético conforme."
                        if path != "noticias.0.title"
                        else "Título registrado sin atribución esencial.",
                    }
                    for path in packet["scope"]
                ],
            }
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps(value, ensure_ascii=False)}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    gen = row.content["generation"]
    assert gen["review"]["status"] == "rejected"
    context = gen["review_context"]
    # The judged candidate survives the fallback strip...
    assert context["candidate"]["brief"]["decisiones"], "judged candidate lost"
    # ...while the stored report keeps the fallback composition.
    assert gen["plan"] is None and row.content["brief"]["decisiones"] == []
    # Binding identifiers match the receipt, so reasons are auditable.
    assert context["scope"] == gen["review"]["scope"]
    assert context["input_fingerprint"] == gen["review"]["input_fingerprint"]
    assert "title" in context["candidate"]["noticias"][0]
    assert gen["rejected_plan"] is not None


def test_passed_review_stores_no_review_context(session, monkeypatch):
    client, _ = _material(session)
    configure(session, client)

    def respond(url, **options):
        packet = json.loads(options["json"]["messages"][1]["content"])
        value = (
            contextual_plan(json.dumps(packet))
            if "scope" not in packet
            else passed_review(packet)
        )
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps(value, ensure_ascii=False)}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.content["generation"]["review"]["status"] == "passed"
    assert "review_context" not in row.content["generation"]


def test_changed_context_prevents_recovery_but_preserves_previous_review(
    session, monkeypatch
):
    client, _ = _material(session)
    configure(session, client)
    calls = []

    def respond(url, **options):
        packet = json.loads(options["json"]["messages"][1]["content"])
        calls.append(packet)
        value = (
            passed_review(packet)
            if "scope" in packet
            else contextual_plan(json.dumps(packet))
        )
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps(value)}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    first = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert first.mode == "llm"
    previous = copy.deepcopy(first.content["generation"])
    mention = queries.insert_mention(
        session,
        client_id=client.id,
        source=MentionSource.news_rss,
        url="https://fixture.invalid/changed-context",
        title="Otra noticia documentada",
        published_at=DAY,
    )
    assert mention is not None
    session.commit()

    def unavailable(_):
        raise RuntimeError("Synthetic provider unavailable")

    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=unavailable
    )
    assert row.mode == "heuristic"
    assert row.content["brief"]["decisiones"] == []
    assert row.content["generation"].get("prior_generation") == previous


@pytest.mark.parametrize(
    "failure",
    [
        "negative",
        "smuggled_premise",
        "missing_scope",
        "duplicate_scope",
        "wrong_fingerprint",
        "bad_type",
        "schema_error",
        "transport",
        "planning_fallback",
    ],
)
def test_review_failure_rebuilds_complete_source_projection_control(
    session, monkeypatch, failure
):
    client, _ = _material(session)
    configure(session, client)
    calls, raw = [], []
    hidden = "Los participantes adoptaron un compromiso presupuestario."

    def respond(url, **options):
        calls.append(copy.deepcopy(options))
        packet = json.loads(options["json"]["messages"][1]["content"])
        if failure == "planning_fallback" and len(calls) == 1:
            return httpx.Response(
                400,
                request=httpx.Request("POST", url),
                json={"error": "plain required"},
            )
        if "scope" not in packet:
            value = contextual_plan(json.dumps(packet))
            if failure == "smuggled_premise":
                value["seleccion"][0]["analysis"]["consequence"] = (
                    "Si se mantiene el compromiso presupuestario adoptado, mejoraría la coordinación."
                )
        else:
            if failure == "transport":
                raise httpx.ConnectError("Synthetic review unavailable")
            value = passed_review(packet)
            if failure in {"negative", "smuggled_premise"}:
                value["passed"] = False
                value["checks"]["factual_premises"] = False
                value["assessments"][0].update(
                    passed=False,
                    reason="Una formulación condicional introduce un compromiso no documentado.",
                )
            elif failure == "missing_scope":
                value["assessments"].pop()
            elif failure == "duplicate_scope":
                value["assessments"][-1] = copy.deepcopy(value["assessments"][0])
            elif failure == "wrong_fingerprint":
                value["input_fingerprint"] = "0" * 64
            elif failure == "bad_type":
                value["checks"]["attribution"] = 1
            elif failure == "schema_error":
                value = {"passed": True}
        text = json.dumps(value, ensure_ascii=False)
        raw.append(text)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": text}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "heuristic"
    generation = row.content["generation"]
    assert generation["status"] == "source_fallback"
    assert generation["physical_requests"] == len(calls) == 2
    assert generation["plan"] is None
    assert generation["raw_proposal"] == raw[0]
    assert generation["review"]["status"] == (
        "unavailable" if failure in {"transport", "planning_fallback"} else "rejected"
    )
    assert generation["review"]["raw_review"] == (
        None if failure in {"transport", "planning_fallback"} else raw[-1]
    )
    for bucket in ("decisiones", "riesgos", "ruido", "a_favor"):
        assert row.content["brief"][bucket] == []
    delivered = json.dumps(
        {key: value for key, value in row.content.items() if key != "generation"},
        ensure_ascii=False,
    )
    assert "compromiso presupuestario" not in delivered
    assert "participación estudiantil puede" not in delivered
    assert "Estudiantes realizaron un mural" in row.content["plain_text"]
    assert all(
        "participación estudiantil puede" not in card.get("por_que", "")
        for card in row.content["tarjetas"]
    )
    assert hidden not in delivered


@pytest.mark.parametrize("dedicated", [False, True])
def test_injected_generation_never_activates_configured_reviewer_control(
    session, monkeypatch, dedicated
):
    client, _ = _material(session)
    configure(session, client)
    calls = []
    if dedicated:
        configure_reviewer(session, client)

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Configured credentials must not be activated")

    monkeypatch.setattr(builder, "summary_generator", forbidden)
    row = builder.build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        generate=lambda prompt: json.dumps(contextual_plan(prompt)),
    )
    assert row.mode == "heuristic"
    assert calls == []
    assert row.content["generation"]["review"]["status"] == "unavailable"
    assert row.content["generation"]["physical_requests"] == 0


@pytest.mark.parametrize(
    "change",
    [
        None,
        "analysis",
        "review",
        "scope",
        "receipt_metadata",
        "frame_only",
        "restore",
        "material",
        "coverage_context",
    ],
)
def test_recovery_requires_exact_compatible_passed_receipt_control(
    session, monkeypatch, change
):
    client, mention = _material(session)
    configure(session, client)

    def respond(url, **options):
        packet = json.loads(options["json"]["messages"][1]["content"])
        value = (
            passed_review(packet)
            if "scope" in packet
            else contextual_plan(json.dumps(packet))
        )
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps(value)}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    first = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert first.mode == "llm"
    original = copy.deepcopy(first.content)
    edited = copy.deepcopy(first.content)
    generation = edited["generation"]
    if change == "analysis":
        generation["plan"]["headline_analysis"]["interpretation"] = (
            "Otra interpretación que no fue revisada."
        )
    elif change == "review":
        generation["review"]["status"] = "rejected"
    elif change == "scope":
        generation["review"]["scope"].pop()
    elif change == "receipt_metadata":
        generation["review"]["fallible"] = False
    elif change == "frame_only":
        generation["plan"].pop("headline_analysis")
        generation["plan"]["seleccion"][0].pop("analysis")
        generation.pop("review")
    elif change == "restore":
        generation["status"] = "revision_restored"
        generation["plan"] = None
    elif change == "material":
        mention.content += " Nueva condición registrada en la publicación."
    elif change == "coverage_context":
        generation["context_fingerprint"] = "0" * 64
    first.content = edited
    session.commit()

    def unavailable(_):
        raise RuntimeError("Synthetic proposal unavailable")

    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=unavailable
    )
    if change is None:
        assert row.mode == "llm"
        assert row.content["generation"]["status"] == "plan_recovered"
        assert row.narrative == original["headline"]
        assert row.content["generation"]["review"] == original["generation"]["review"]
        assert row.content["noticias"] == original["noticias"]
        assert row.content["tarjetas"] == original["tarjetas"]
        assert row.content["brief"] == original["brief"]
    else:
        assert row.mode == "heuristic"
        assert row.content["generation"]["status"] == "source_fallback"
        assert row.content["brief"]["decisiones"] == []
        assert "Otra interpretación" not in row.content["plain_text"]
    assert row.content["generation"]["prior_generation"] == edited["generation"]


@pytest.mark.parametrize("focus", ["missing", "foreign", "absent"])
def test_unavailable_focus_does_not_choose_substitute_control(
    session, monkeypatch, focus
):
    from app.models import Client, Person

    client, _ = _material(session)
    configure(session, client)
    settings = queries.get_settings(session, client.id)
    if focus == "missing":
        settings.digest_focus_person_id = 99999
    elif focus == "foreign":
        other = Client(name="Synthetic foreign tenant")
        session.add(other)
        session.flush()
        person = Person(
            client_id=other.id,
            name="Identidad ajena",
            name_key="identidad ajena",
            role="Cargo ajeno",
        )
        session.add(person)
        session.flush()
        settings.digest_focus_person_id = person.id
    session.commit()
    packets = []

    def factory(effective, *, phase, budget, system_prompt, response_schema):
        def generate(prompt):
            packet = json.loads(prompt)
            packets.append(packet)
            return json.dumps(
                passed_review(packet) if phase == "review" else contextual_plan(prompt)
            )

        return generate

    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    assert row.mode == "llm"
    assert "focus_person" not in packets[0]
    assert packets[1]["focus_person"] is None
    assert "Identidad ajena" not in json.dumps(packets, ensure_ascii=False)


def test_frame_only_plan_is_not_fresh_semantic_approval_control(session):
    from tests.digest_plan_fixtures import plan_completion, reviewed_factory

    client, _ = _material(session)
    row = builder.build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        generator_factory=reviewed_factory(
            lambda prompt: plan_completion(prompt, [(0, "decision")])
        ),
    )
    assert row.mode == "heuristic"
    assert row.content["generation"]["review"] is None
    assert row.content["brief"]["decisiones"] == []
