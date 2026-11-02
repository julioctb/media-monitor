"""Guided-decoder text compatibility is separate from semantic quality."""

import json
from copy import deepcopy

import httpx
import pytest

from app.models import DailySummary, DailySummaryRevision
from app.summaries import builder
from app.summaries.advisory_review import (
    ReviewError,
    assess_review,
    compatible_review,
    review_receipt,
    review_schema,
)
from app.summaries.factual_contract import (
    FactualPlanError,
    factual_plan_schema,
    factual_prompt_view,
    require_contextual_plan,
)
from tests.test_digest_advisory_review import configure, contextual_plan, passed_review
from tests.test_digest_factual_contract import mention, prepared
from tests.test_digest_factual_pipeline import DAY, _material
from tests.test_political_analysis_regeneration import snapshot_tables

PROSE_FIELDS = ("interpretation", "consequence", "attention", "conditions", "relevance")


def test_contextual_wire_prose_preserves_sentences_and_bounds_without_pattern():
    content = prepared(mention())
    before = deepcopy(content)
    static = factual_plan_schema()
    wire = factual_plan_schema(content)
    for field in PROSE_FIELDS:
        old = static["$defs"]["_Analysis"]["properties"][field]
        text = wire["$defs"]["_Analysis"]["properties"][field]
        assert text["type"] == "string"
        assert text["minLength"] == 2
        assert text["maxLength"] == 1000
        assert "pattern" not in text
        assert {k: v for k, v in text.items() if k != "minLength"} == {
            k: v for k, v in old.items() if k not in {"minLength", "pattern"}
        }
    assert (
        static["$defs"]["_Analysis"]["properties"]["interpretation"]["pattern"] == r"\S"
    )
    assert factual_plan_schema() == static
    assert content == before


def envelope(url, value):
    return httpx.Response(
        200,
        request=httpx.Request("POST", url),
        json={"choices": [{"message": {"content": value}}]},
    )


def assert_complete_source_projection(session, client_id, content):
    control = builder.build_daily_summary(
        session,
        client_id=client_id,
        day=DAY.date(),
        generator_factory=lambda effective, **options: None,
    )
    assert control.mode == "heuristic"
    assert {k: v for k, v in content.items() if k != "generation"} == {
        k: v for k, v in control.content.items() if k != "generation"
    }


@pytest.mark.parametrize("owner", ["headline", "selection"])
@pytest.mark.parametrize("field", PROSE_FIELDS)
@pytest.mark.parametrize("value", ["A", " A "])
def test_public_pipeline_rejects_single_character_analysis(
    session, monkeypatch, owner, field, value
):
    client, _ = _material(session)
    configure(session, client)
    before = snapshot_tables(session)
    calls, outputs = [], []

    def respond(url, **options):
        calls.append(deepcopy(options))
        packet = json.loads(options["json"]["messages"][1]["content"])
        if "scope" in packet:
            result = passed_review(packet)
        else:
            result = contextual_plan(json.dumps(packet))
            analysis = (
                result["headline_analysis"]
                if owner == "headline"
                else result["seleccion"][0]["analysis"]
            )
            analysis[field] = value
        raw = json.dumps(result, ensure_ascii=False)
        outputs.append(raw)
        return envelope(url, raw)

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "heuristic"
    content = deepcopy(row.content)
    generation = content["generation"]
    assert generation["status"] == "source_fallback"
    assert generation["physical_requests"] == len(calls) == 1
    assert generation["raw_proposal"] == outputs[0]
    assert generation["plan"] is None
    assert_complete_source_projection(session, client.id, content)
    assert len(calls) == 1
    after = snapshot_tables(session)
    reports = {DailySummary.__tablename__, DailySummaryRevision.__tablename__}
    assert {k: v for k, v in after.items() if k not in reports} == {
        k: v for k, v in before.items() if k not in reports
    }


@pytest.mark.parametrize("owner", ["headline", "selection"])
@pytest.mark.parametrize("field", PROSE_FIELDS)
@pytest.mark.parametrize(
    "value", ["", " ", "A", " A ", pytest.param("x" * 1001, id="overflow"), True]
)
def test_fresh_gate_rejects_degenerate_or_overflow_prose(owner, field, value):
    content = prepared(mention())
    plan = contextual_plan(json.dumps(factual_prompt_view(content)))
    analysis = (
        plan["headline_analysis"]
        if owner == "headline"
        else plan["seleccion"][0]["analysis"]
    )
    analysis[field] = value
    before = deepcopy(plan)
    with pytest.raises(FactualPlanError):
        require_contextual_plan(plan)
    assert plan == before


@pytest.mark.parametrize(
    "value", ["  Una lectura institucional completa.  ", "x" * 1000]
)
def test_fresh_gate_preserves_text_and_original_single_character_material(value):
    content = prepared(mention(title="A", content="X", summary="Y"))
    plan = contextual_plan(json.dumps(factual_prompt_view(content)))
    for analysis in [plan["headline_analysis"], plan["seleccion"][0]["analysis"]]:
        for field in PROSE_FIELDS:
            analysis[field] = value
    before = deepcopy(plan)
    require_contextual_plan(plan)
    assert plan == before
    assert content["factual_basis"]["sources"][0]["title"] == "A"
    assert content["factual_basis"]["sources"][0]["passages"] == ["X"]


def test_review_wire_reason_preserves_sentences_and_scope_without_pattern():
    packet = {"input_fingerprint": "0" * 64, "scope": ["headline"]}
    before = deepcopy(packet)
    schema = review_schema(packet)
    assert schema["$defs"]["_Assessment"]["properties"]["reason"] == {
        "type": "string",
        "title": "Reason",
        "minLength": 2,
        "maxLength": 500,
    }
    assert schema["$defs"]["_Assessment"]["properties"]["path"]["enum"] == ["headline"]
    assert schema["properties"]["input_fingerprint"]["const"] == "0" * 64
    assert schema["properties"]["assessments"]["minItems"] == 1
    assert schema["properties"]["assessments"]["maxItems"] == 1
    assert packet == before


@pytest.mark.parametrize(
    "reason", ["A", " A ", "", " ", pytest.param("x" * 501, id="overflow"), True]
)
def test_public_pipeline_rejects_inadequate_review_reason(session, monkeypatch, reason):
    client, _ = _material(session)
    configure(session, client)
    before = snapshot_tables(session)
    calls, outputs = [], []

    def respond(url, **options):
        calls.append(deepcopy(options))
        packet = json.loads(options["json"]["messages"][1]["content"])
        if "scope" in packet:
            value = passed_review(packet)
            value["assessments"][0]["reason"] = reason
        else:
            value = contextual_plan(json.dumps(packet))
        raw = json.dumps(value, ensure_ascii=False)
        outputs.append(raw)
        return envelope(url, raw)

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "heuristic"
    content = deepcopy(row.content)
    generation = content["generation"]
    assert generation["status"] == "source_fallback"
    assert generation["physical_requests"] == len(calls) == 2
    assert generation["plan"] is None
    assert generation["raw_proposal"] == outputs[0]
    assert generation["rejected_plan"] == json.loads(outputs[0])
    assert generation["review"]["status"] == "rejected"
    assert generation["review"]["raw_review"] == outputs[1]
    assert_complete_source_projection(session, client.id, content)
    assert len(calls) == 2
    after = snapshot_tables(session)
    reports = {DailySummary.__tablename__, DailySummaryRevision.__tablename__}
    assert {k: v for k, v in after.items() if k not in reports} == {
        k: v for k, v in before.items() if k not in reports
    }


@pytest.mark.parametrize("reason", ["A", " A "])
def test_single_character_review_is_not_eligible_for_recovery(reason):
    packet = {
        "input_fingerprint": "0" * 64,
        "scope": ["headline"],
        "required_checks": [
            "attribution",
            "factual_premises",
            "omissions",
            "profile_relevance",
            "categories",
            "uncertainty",
            "distinct_attention",
            "passage_suitability",
        ],
    }
    value = passed_review(packet)
    value["assessments"][0]["reason"] = reason
    raw = json.dumps(value)
    receipt = review_receipt(packet, status="passed", raw=raw)
    before = deepcopy(receipt)
    with pytest.raises(ReviewError):
        assess_review(raw, packet)
    assert compatible_review(receipt, packet) is False
    assert receipt == before


def test_valid_review_text_and_receipt_remain_eligible_without_normalization():
    packet = {
        "input_fingerprint": "0" * 64,
        "scope": ["headline"],
        "required_checks": [
            "attribution",
            "factual_premises",
            "omissions",
            "profile_relevance",
            "categories",
            "uncertainty",
            "distinct_attention",
            "passage_suitability",
        ],
    }
    value = passed_review(packet)
    value["assessments"][0]["reason"] = "  Premisa literal y alcance conservados.  "
    raw = json.dumps(value)
    assert assess_review(raw, packet) == value
    receipt = review_receipt(packet, status="passed", raw=raw)
    before = deepcopy(receipt)
    assert compatible_review(receipt, packet) is True
    assert receipt == before


@pytest.mark.parametrize("reason", ["A", " A "])
def test_public_recovery_rejects_previously_passed_single_character_reason(
    session, monkeypatch, reason
):
    client, _ = _material(session)
    configure(session, client)
    calls = []

    def respond(url, **options):
        calls.append(deepcopy(options))
        packet = json.loads(options["json"]["messages"][1]["content"])
        value = (
            passed_review(packet)
            if "scope" in packet
            else contextual_plan(json.dumps(packet))
        )
        return envelope(url, json.dumps(value))

    monkeypatch.setattr(builder.httpx, "post", respond)
    first = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert first.mode == "llm"
    edited = deepcopy(first.content)
    review = json.loads(edited["generation"]["review"]["raw_review"])
    review["assessments"][0]["reason"] = reason
    edited["generation"]["review"]["raw_review"] = json.dumps(review)
    first.content = edited
    session.commit()

    def unavailable(prompt):
        raise RuntimeError("Synthetic generation unavailable")

    row = builder.build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        generate=unavailable,
    )
    assert row.mode == "heuristic"
    assert row.content["generation"]["status"] == "source_fallback"
    assert row.content["generation"]["prior_generation"] == edited["generation"]
    assert len(calls) == 2
    assert_complete_source_projection(session, client.id, deepcopy(row.content))
    assert len(calls) == 2


def test_public_adapter_emits_identical_bounded_wire_schemas_and_keeps_raw_text(
    session, monkeypatch
):
    client, _ = _material(session)
    configure(session, client)
    calls, outputs = [], []
    sentence = "  La lectura institucional exige seguimiento específico.  "

    def respond(url, **options):
        calls.append(deepcopy(options))
        packet = json.loads(options["json"]["messages"][1]["content"])
        if "scope" in packet:
            value = passed_review(packet)
            for assessment in value["assessments"]:
                assessment["reason"] = (
                    "  Evaluación sintética del campo suministrado.  "
                )
        else:
            value = contextual_plan(json.dumps(packet))
            value["headline_analysis"]["interpretation"] = sentence
        raw = json.dumps(value, ensure_ascii=False)
        outputs.append(raw)
        return envelope(url, raw)

    monkeypatch.setattr(builder.httpx, "post", respond)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "llm"
    assert len(calls) == row.content["generation"]["physical_requests"] == 2
    assert row.content["generation"]["raw_proposal"] == outputs[0]
    assert (
        row.content["generation"]["plan"]["headline_analysis"]["interpretation"]
        == sentence
    )
    assert row.content["generation"]["review"]["raw_review"] == outputs[1]
    for call in calls:
        body = call["json"]
        packet = json.loads(body["messages"][1]["content"])
        assert (
            packet["response_schema"]
            == body["response_format"]["json_schema"]["schema"]
        )
        assert set(body) == {
            "model",
            "messages",
            "temperature",
            "response_format",
            "chat_template_kwargs",
        }
        # Tarea mecanica del digest: sin razonamiento (ver app/llm_chat.py).
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert body["model"] == "fixture"
        assert call["timeout"] == 120.0
        assert call["follow_redirects"] is False
    proposal = calls[0]["json"]["response_format"]["json_schema"]["schema"]
    review = calls[1]["json"]["response_format"]["json_schema"]["schema"]
    for field in PROSE_FIELDS:
        assert proposal["$defs"]["_Analysis"]["properties"][field] == {
            "title": field.title(),
            "type": "string",
        }
        assert "pattern" not in proposal["$defs"]["_Analysis"]["properties"][field]
    assert review["$defs"]["_Assessment"]["properties"]["reason"] == {
        "title": "Reason",
        "type": "string",
    }
    assert "pattern" not in review["$defs"]["_Assessment"]["properties"]["reason"]
