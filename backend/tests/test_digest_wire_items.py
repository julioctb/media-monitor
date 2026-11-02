"""Fresh transport envelopes preserve canonical identity, not semantic quality."""

import copy
import json

import httpx
import pytest

from app.models import DailySummary, DailySummaryRevision, MentionSource, queries
from app.summaries import builder
from tests.digest_plan_fixtures import advisory_completion, review_completion
from tests.test_digest_advisory_review import configure
from tests.test_digest_factual_pipeline import DAY, _material
from tests.test_political_analysis_regeneration import snapshot_tables


def _typed(value):
    """JSON comparison that cannot equate bools and numbers or lose key order."""
    if type(value) is dict:
        return (dict, [(_typed(k), _typed(v)) for k, v in value.items()])
    if type(value) in (list, tuple):
        return (type(value), [_typed(v) for v in value])
    return (type(value), value)


def _seed(session):
    client, _ = _material(session)
    for suffix, title in [
        (1, "Sesión del consejo regional"),
        (2, "Propuesta de movilidad"),
    ]:
        row = queries.insert_mention(
            session,
            client_id=client.id,
            source=MentionSource.news_rss,
            url=f"https://fixture.invalid/wire-{suffix}",
            title=title,
            published_at=DAY.replace(minute=suffix),
        )
        assert row is not None
        row.content = (
            f"La publicación número {suffix} describe una propuesta institucional."
        )
    configure(session, client)
    return client


def _proposal(prompt, *, wire=True):
    plan = json.loads(
        advisory_completion(
            prompt, [(2, "decision"), (0, "decision")], item_indexes=[2, 0]
        )
    )
    if wire:
        plan["items"] = {str(item["index"]): item for item in plan["items"]}
    return plan


def _transport(monkeypatch, *, wire=True, change=None, retry=False):
    calls, emitted, phases = [], [], []

    def respond(url, **options):
        calls.append(copy.deepcopy(options))
        if retry and len(calls) == 1:
            return httpx.Response(
                400,
                request=httpx.Request("POST", url),
                json={"error": "plain required"},
            )
        prompt = options["json"]["messages"][1]["content"]
        packet = json.loads(prompt)
        phase = "review" if "scope" in packet else "proposal"
        value = (
            json.loads(review_completion(prompt))
            if phase == "review"
            else _proposal(prompt, wire=wire)
        )
        if change is not None:
            value = change(phase, value, packet)
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        emitted.append(raw)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": raw}}]},
        )

    def factory(effective, *, phase, budget, system_prompt, response_schema):
        phases.append(phase)
        return builder.summary_generator(
            effective,
            budget=budget,
            system_prompt=system_prompt,
            response_schema=response_schema,
        )

    monkeypatch.setattr(builder.httpx, "post", respond)
    return factory, calls, emitted, phases


def test_public_wire_schema_uses_optional_identity_slots_and_unbounded_text(
    session, monkeypatch
):
    client = _seed(session)
    factory, calls, _, _ = _transport(monkeypatch, wire=False)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    assert row.mode == "llm"
    body = calls[0]["json"]
    packet = json.loads(body["messages"][1]["content"])
    schema = body["response_format"]["json_schema"]["schema"]
    items = schema["properties"]["items"]
    assert items["type"] == "object"
    assert items["additionalProperties"] is False
    assert "items" in schema["required"]
    assert "required" not in items
    assert set(items["properties"]) == {"0", "1", "2"}
    assert set(items) == {"title", "type", "properties", "additionalProperties"}
    all_choices = []
    for key, slot in items["properties"].items():
        for branch in slot["anyOf"]:
            assert branch["properties"]["index"]["const"] == int(key)
            assert branch["properties"]["index"]["type"] == "integer"
            all_choices.append(branch)
    assert _typed(all_choices) == _typed(schema["$defs"]["_Item"]["anyOf"])
    for field in (
        "interpretation",
        "consequence",
        "attention",
        "conditions",
        "relevance",
    ):
        assert schema["$defs"]["_Analysis"]["properties"][field] == {
            "title": field.title(),
            "type": "string",
        }
    assert packet["response_schema"] == schema
    assert "items es un objeto" in body["messages"][0]["content"]
    assert (
        "seleccion sigue siendo un arreglo ordenado por prioridad"
        in body["messages"][0]["content"]
    )


def test_public_review_wire_envelope_preserves_lossless_escaped_text(
    session, monkeypatch
):
    client = _seed(session)
    text = '  Lectura de "ámbito" institucional.\nRuta C:\\captura; símbolo Ω y 漢字.  '

    def escaped(phase, value, packet):
        if phase == "proposal":
            analyses = [value["headline_analysis"]] + [
                pick["analysis"] for pick in value["seleccion"]
            ]
            for analysis in analyses:
                for field in (
                    "interpretation",
                    "consequence",
                    "attention",
                    "conditions",
                    "relevance",
                ):
                    analysis[field] = text
        else:
            for assessment in value["assessments"]:
                assessment["reason"] = text
        return json.dumps(value, ensure_ascii=True, indent=2)

    factory, calls, emitted, _ = _transport(monkeypatch, change=escaped)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    assert row.mode == "llm"
    generation = row.content["generation"]
    assert generation["raw_proposal"] == emitted[0]
    assert generation["review"]["raw_review"] == emitted[1]
    assert generation["plan"]["headline_analysis"]["interpretation"] == text
    assert all(a["reason"] == text for a in json.loads(emitted[1])["assessments"])
    schema = calls[1]["json"]["response_format"]["json_schema"]["schema"]
    assert schema["$defs"]["_Assessment"]["properties"]["reason"] == {
        "title": "Reason",
        "type": "string",
    }
    packet = json.loads(calls[1]["json"]["messages"][1]["content"])
    assert packet["response_schema"] == schema
    assert packet["plan"]["headline_analysis"]["interpretation"] == text


def test_public_caller_created_factory_accepts_sparse_nonascending_wire_items(
    session, monkeypatch
):
    client = _seed(session)
    before = snapshot_tables(session)
    factory, calls, emitted, phases = _transport(monkeypatch)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    assert row.mode == "llm"
    generation = row.content["generation"]
    assert generation["status"] == "plan_applied"
    assert generation["physical_requests"] == len(calls) == 2
    assert phases == ["proposal", "review"]
    assert generation["raw_proposal"] == emitted[0]
    assert list(json.loads(emitted[0])["items"]) == ["2", "0"]
    assert [item["index"] for item in generation["plan"]["items"]] == [2, 0]
    assert [pick["index"] for pick in generation["plan"]["seleccion"]] == [2, 0]
    packet = json.loads(calls[1]["json"]["messages"][1]["content"])
    assert _typed(packet["plan"]) == _typed(generation["plan"])
    assert packet["candidate"]["plain_text"] == row.content["plain_text"]
    assert generation["review"]["raw_review"] == emitted[1]
    after = snapshot_tables(session)
    reports = {DailySummary.__tablename__, DailySummaryRevision.__tablename__}
    assert _typed({k: v for k, v in after.items() if k not in reports}) == _typed(
        {k: v for k, v in before.items() if k not in reports}
    )


def test_wire_and_array_candidates_have_identical_canonical_review_and_export(
    session, monkeypatch
):
    from app.summaries.regeneration import generate_candidate

    client = _seed(session)
    session.add(
        DailySummary(
            client_id=client.id,
            summary_date=DAY.date(),
            mode="heuristic",
            narrative="Original protegido",
            content={
                "date": DAY.date().isoformat(),
                "timezone": "UTC",
                "window": {
                    "from": "2026-10-10T00:00:00+00:00",
                    "to": "2026-10-11T00:00:00+00:00",
                },
            },
        )
    )
    session.commit()
    before = snapshot_tables(session)
    results, packets, raw = [], [], []
    for wire in (False, True):
        factory, calls, emitted, phases = _transport(monkeypatch, wire=wire)
        result = generate_candidate(
            session.get_bind(),
            client_id=client.id,
            day=DAY.date(),
            generator_factory=factory,
        )
        assert phases == ["proposal", "review"]
        assert _typed(snapshot_tables(session)) == _typed(before)
        assert result["calls"][0]["completion"] == emitted[0]
        raw.append(result["content"]["generation"].pop("raw_proposal"))
        packets.append(json.loads(calls[1]["json"]["messages"][1]["content"]))
        results.append({k: v for k, v in result.items() if k != "calls"})
    assert type(json.loads(raw[0])["items"]) is list
    assert type(json.loads(raw[1])["items"]) is dict
    assert json.loads(raw[0])["items"] == list(json.loads(raw[1])["items"].values())
    assert _typed(results[0]) == _typed(results[1])
    assert _typed(packets[0]) == _typed(packets[1])


@pytest.mark.parametrize(
    "failure",
    [
        "unknown",
        "zero_padded",
        "left_padded",
        "right_padded",
        "null_slot",
        "list_slot",
        "number_slot",
        "missing_index",
        "bool_index",
        "float_index",
        "string_index",
        "mismatched_index",
        "missing_items",
        "null_items",
        "stale_fingerprint",
        "extra_root",
        "extra_item",
        "foreign_source",
        "missing_passage",
        "foreign_premise",
        "duplicate_premise",
        "duplicate_selection",
        "duplicate_array",
    ],
)
def test_invalid_wire_or_legacy_selectors_fail_atomically_control(
    session, monkeypatch, failure
):
    client = _seed(session)

    def corrupt(phase, value, packet):
        assert phase == "proposal"
        items, entry = value["items"], value["items"]["2"]
        if failure in {"unknown", "zero_padded", "left_padded", "right_padded"}:
            key = {
                "unknown": "99",
                "zero_padded": "02",
                "left_padded": " 2",
                "right_padded": "2 ",
            }[failure]
            items[key] = items.pop("2")
        elif failure in {"null_slot", "list_slot", "number_slot"}:
            items["2"] = {"null_slot": None, "list_slot": [], "number_slot": 2}[failure]
        elif failure == "missing_index":
            entry.pop("index")
        elif failure in {
            "bool_index",
            "float_index",
            "string_index",
            "mismatched_index",
        }:
            entry["index"] = {
                "bool_index": True,
                "float_index": 2.0,
                "string_index": "2",
                "mismatched_index": 0,
            }[failure]
        elif failure == "missing_items":
            value.pop("items")
        elif failure == "null_items":
            value["items"] = None
        elif failure == "stale_fingerprint":
            value["basis_fingerprint"] = "0" * 64
        elif failure == "extra_root":
            value["unexpected"] = True
        elif failure == "extra_item":
            entry["unexpected"] = True
        elif failure == "foreign_source":
            entry["source_ref"] = packet["stories"][1]["source_refs"][0]
        elif failure == "missing_passage":
            entry["passage_index"] = 6
        elif failure == "foreign_premise":
            value["headline_analysis"]["premises"] = [copy.deepcopy(entry)]
        elif failure == "duplicate_premise":
            value["headline_analysis"]["premises"] *= 2
        elif failure == "duplicate_selection":
            value["seleccion"].append(copy.deepcopy(value["seleccion"][0]))
        elif failure == "duplicate_array":
            value["items"] = [copy.deepcopy(entry), copy.deepcopy(entry)]
        return value

    factory, calls, emitted, phases = _transport(monkeypatch, change=corrupt)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    assert row.mode == "heuristic"
    generation = row.content["generation"]
    assert generation["reason"] == "noncompliant_response"
    assert generation["plan"] is generation["review"] is None
    assert generation["raw_proposal"] == emitted[0]
    assert len(calls) == 1
    assert phases == ["proposal"]


@pytest.mark.parametrize(
    "failure",
    ["malformed", "root_duplicate", "slot_duplicate", "escaped_slot", "escaped_nested"],
)
def test_strict_decode_precedes_wire_adaptation(session, monkeypatch, failure):
    client = _seed(session)
    adapted = []
    original = builder.adapt_factual_wire_plan

    def observed(*args):
        adapted.append(True)
        return original(*args)

    monkeypatch.setattr(builder, "adapt_factual_wire_plan", observed)

    def corrupt(phase, value, packet):
        raw = json.dumps(value)
        if failure == "malformed":
            return raw[:-1]
        if failure == "root_duplicate":
            return (
                raw[:-1]
                + ', "basis_fingerprint": "'
                + value["basis_fingerprint"]
                + '"}'
            )
        if failure in {"slot_duplicate", "escaped_slot"}:
            alias = '"2"' if failure == "slot_duplicate" else '"\\u0032"'
            return raw.replace('"2": {', alias + ': {}, "2": {', 1)
        return raw.replace('"index": 2', '"index": 2, "\\u0069ndex": 2', 1)

    factory, calls, emitted, _ = _transport(monkeypatch, change=corrupt)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    assert row.mode == "heuristic"
    assert row.content["generation"]["raw_proposal"] == emitted[0]
    assert row.content["generation"]["reason"] == "noncompliant_response"
    assert adapted == []
    assert len(calls) == 1


@pytest.mark.parametrize(
    "failure", ["negative", "scope", "fingerprint", "extra", "type"]
)
def test_wire_review_rejection_retains_raw_and_canonical_rejected_plan(
    session, monkeypatch, failure
):
    client = _seed(session)

    def corrupt(phase, value, packet):
        if phase == "review":
            if failure == "negative":
                value["passed"] = False
            elif failure == "scope":
                value["assessments"].pop()
            elif failure == "fingerprint":
                value["input_fingerprint"] = "0" * 64
            elif failure == "extra":
                value["checks"]["extra"] = True
            else:
                value["checks"]["attribution"] = 1
        return value

    factory, calls, emitted, _ = _transport(monkeypatch, change=corrupt)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    generation = row.content["generation"]
    assert row.mode == "heuristic"
    assert generation["reason"] == "semantic_review_rejected"
    assert generation["plan"] is None
    expected = json.loads(emitted[0])
    expected["items"] = list(expected["items"].values())
    assert _typed(generation["rejected_plan"]) == _typed(expected)
    assert generation["raw_proposal"] == emitted[0]
    assert generation["review"]["raw_review"] == emitted[1]
    assert len(calls) == generation["physical_requests"] == 2


def test_empty_wire_items_omits_all_overrides_without_omitting_stories(
    session, monkeypatch
):
    client = _seed(session)

    def empty(phase, value, packet):
        if phase == "proposal":
            value["items"] = {}
        return value

    factory, _, _, _ = _transport(monkeypatch, change=empty)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    assert row.mode == "llm"
    assert row.content["generation"]["plan"]["items"] == []
    assert len(row.content["noticias"]) == 3


def test_wire_plain_retry_is_identical_except_response_format_and_never_dispatches_third(
    session, monkeypatch
):
    client = _seed(session)
    factory, calls, emitted, phases = _transport(monkeypatch, retry=True)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    assert row.mode == "heuristic"
    generation = row.content["generation"]
    assert generation["reason"] == "semantic_review_unavailable"
    assert len(calls) == generation["physical_requests"] == 2
    first = copy.deepcopy(calls[0])
    schema = first["json"].pop("response_format")["json_schema"]["schema"]
    assert _typed(first) == _typed(calls[1])
    assert (
        json.loads(first["json"]["messages"][1]["content"])["response_schema"] == schema
    )
    assert schema["properties"]["items"]["type"] == "object"
    assert generation["raw_proposal"] == emitted[0]
    assert type(generation["rejected_plan"]["items"]) is list
    assert phases == ["proposal", "review"]


@pytest.mark.parametrize("wire", [False, True])
def test_direct_generate_remains_legacy_and_cannot_activate_provider_control(
    session, monkeypatch, wire
):
    from app.summaries.factual_contract import (
        FACTUAL_SYSTEM_PROMPT,
        factual_plan_schema,
    )

    client = _seed(session)
    sent = []

    def forbidden(*args, **kwargs):
        raise AssertionError("Direct callable must not activate configured credentials")

    monkeypatch.setattr(builder, "summary_generator", forbidden)

    def generate(prompt):
        packet = json.loads(prompt)
        sent.append(packet)
        assert packet["response_schema"]["properties"]["items"]["type"] == "array"
        return json.dumps(_proposal(prompt, wire=wire))

    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=generate
    )
    generation = row.content["generation"]
    assert row.mode == "heuristic"
    assert generation["physical_requests"] == 0
    assert generation["reason"] == (
        "noncompliant_response" if wire else "semantic_review_unavailable"
    )
    assert (generation["review"] is None) == wire
    assert len(sent) == 1
    assert factual_plan_schema()["properties"]["items"]["type"] == "array"
    assert "items es un objeto" not in FACTUAL_SYSTEM_PROMPT


@pytest.mark.parametrize("stale", [False, True])
def test_canonical_wire_recovery_requires_unchanged_receipt(
    session, monkeypatch, stale
):
    client = _seed(session)
    factory, calls, _, _ = _transport(monkeypatch)
    first = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    assert first.mode == "llm"
    original = copy.deepcopy(first.content)
    edited = copy.deepcopy(first.content)
    if stale:
        edited["generation"]["review"]["input_fingerprint"] = "0" * 64
        first.content = edited
        session.commit()
    row = builder.build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        generator_factory=lambda effective, **options: None,
    )
    assert len(calls) == 2
    assert row.mode == ("heuristic" if stale else "llm")
    generation = row.content["generation"]
    assert generation["status"] == ("source_fallback" if stale else "plan_recovered")
    assert _typed(generation["prior_generation"]) == _typed(edited["generation"])
    if not stale:
        assert _typed(generation["plan"]) == _typed(original["generation"]["plan"])
        assert _typed(generation["review"]) == _typed(original["generation"]["review"])
        assert row.content["plain_text"] == original["plain_text"]


def test_wire_helpers_are_exact_detached_projections_with_only_legal_slots():
    from app.summaries.advisory_review import review_schema, review_wire_schema
    from app.summaries.factual_contract import (
        adapt_factual_wire_plan,
        factual_plan_schema,
        factual_prompt_view,
        factual_wire_schema,
        render_factual_plan,
        require_contextual_plan,
    )
    from tests.test_digest_factual_contract import mention, prepared

    content = prepared(
        mention(content="Una premisa documentada. " * 60),
        mention(2, title="", content=""),
    )
    before = copy.deepcopy(content)
    static, contextual = factual_plan_schema(), factual_plan_schema(content)
    schema = factual_wire_schema(content)
    expected = copy.deepcopy(contextual)
    branches = contextual["properties"]["items"]["items"]["anyOf"]
    expected["properties"]["items"] = {
        "title": "Items",
        "type": "object",
        "properties": {"0": {"anyOf": branches}},
        "additionalProperties": False,
    }
    for field in (
        "interpretation",
        "consequence",
        "attention",
        "conditions",
        "relevance",
    ):
        for key in ("pattern", "minLength", "maxLength"):
            expected["$defs"]["_Analysis"]["properties"][field].pop(key, None)
    assert _typed(schema) == _typed(expected)
    assert _typed(schema["$defs"]["_Item"]) == _typed(contextual["$defs"]["_Item"])
    plan = json.loads(
        advisory_completion(json.dumps(factual_prompt_view(content)), [(0, "decision")])
    )
    plan["headline_analysis"]["premises"].append(
        {"index": 0, "source_ref": 0, "passage_index": 1}
    )
    plan["items"] = {"0": plan["items"][0]}
    detached = adapt_factual_wire_plan(content, plan)
    render_factual_plan(content, detached)
    require_contextual_plan(detached)
    detached["headline_analysis"]["premises"][0]["index"] = 99
    assert plan["headline_analysis"]["premises"][0]["index"] == 0
    packet = {"input_fingerprint": "0" * 64, "scope": ["headline", "plain_text"]}
    prior = copy.deepcopy(packet)
    review = review_schema(packet)
    projected = review_wire_schema(packet)
    expected_review = copy.deepcopy(review)
    for key in ("pattern", "minLength", "maxLength"):
        expected_review["$defs"]["_Assessment"]["properties"]["reason"].pop(key, None)
    assert _typed(projected) == _typed(expected_review)
    schema["$defs"]["_Item"]["anyOf"].clear()
    projected["properties"]["checks"]["required"].clear()
    assert _typed(factual_plan_schema()) == _typed(static)
    assert _typed(factual_plan_schema(content)) == _typed(contextual)
    assert _typed(review_schema(packet)) == _typed(review)
    assert _typed(content) == _typed(before)
    assert _typed(packet) == _typed(prior)
    assert factual_wire_schema(prepared())["properties"]["items"]["properties"] == {}


@pytest.mark.parametrize("phase", ["proposal", "review"])
@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "blank",
        "singleton",
        "padded_singleton",
        "overflow",
        "bool",
        "number",
        "null",
        "minimum",
        "maximum",
    ],
)
def test_wire_envelope_does_not_relax_runtime_text_acceptance(
    session, monkeypatch, phase, case
):
    client = _seed(session)
    maximum = 1000 if phase == "proposal" else 500
    values = {
        "empty": "",
        "blank": " \n\t",
        "singleton": "A",
        "padded_singleton": " A ",
        "overflow": "x" * (maximum + 1),
        "bool": True,
        "number": 2,
        "null": None,
        "minimum": "áΩ",
        "maximum": "x" * maximum,
    }
    text = values[case]

    def change(current, value, packet):
        if current == phase:
            if phase == "proposal":
                value["headline_analysis"]["interpretation"] = text
            else:
                value["assessments"][0]["reason"] = text
        return value

    factory, calls, emitted, _ = _transport(monkeypatch, change=change)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generator_factory=factory
    )
    accepted = case in {"minimum", "maximum"}
    assert row.mode == ("llm" if accepted else "heuristic")
    generation = row.content["generation"]
    assert generation["raw_proposal"] == emitted[0]
    assert len(calls) == (2 if phase == "review" or accepted else 1)
    if accepted:
        if phase == "proposal":
            assert generation["plan"]["headline_analysis"]["interpretation"] == text
        else:
            assert (
                json.loads(generation["review"]["raw_review"])["assessments"][0][
                    "reason"
                ]
                == text
            )
    else:
        assert generation["plan"] is None


def test_factory_precedence_still_uses_wire_when_direct_generate_is_also_given(
    session, monkeypatch
):
    client = _seed(session)
    factory, calls, _, _ = _transport(monkeypatch)

    def forbidden(prompt):
        raise AssertionError("Factory retains precedence over direct generation")

    row = builder.build_daily_summary(
        session,
        client_id=client.id,
        day=DAY.date(),
        generate=forbidden,
        generator_factory=factory,
    )
    assert row.mode == "llm"
    assert len(calls) == 2
    assert (
        calls[0]["json"]["response_format"]["json_schema"]["schema"]["properties"][
            "items"
        ]["type"]
        == "object"
    )


def test_configured_provider_accepts_wire_object_without_factory(session, monkeypatch):
    client = _seed(session)
    _, calls, emitted, _ = _transport(monkeypatch)
    row = builder.build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "llm"
    assert row.content["generation"]["raw_proposal"] == emitted[0]
    assert [item["index"] for item in row.content["generation"]["plan"]["items"]] == [
        2,
        0,
    ]
    assert len(calls) == 2


@pytest.mark.parametrize("key", [0, "00", " 0", "0 ", "+0", "-0"])
def test_adapter_rejects_noncanonical_keys_without_inferring_indexes_control(key):
    from app.summaries.factual_contract import (
        FactualPlanError,
        adapt_factual_wire_plan,
        factual_prompt_view,
    )
    from tests.test_digest_factual_contract import mention, prepared

    content = prepared(mention())
    plan = json.loads(advisory_completion(json.dumps(factual_prompt_view(content))))
    plan["items"] = {key: plan["items"][0]}
    before = copy.deepcopy(plan)
    with pytest.raises(FactualPlanError, match="Invalid factual item slot"):
        adapt_factual_wire_plan(content, plan)
    assert _typed(plan) == _typed(before)
