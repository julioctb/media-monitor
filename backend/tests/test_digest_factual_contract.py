"""Behavioral checks for source identity, literal reporting and constrained plans."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models import Mention, MentionSource
from app.summaries.evidence import freeze_sources
from app.summaries.factual_contract import (
    FactualPlanError,
    build_factual_basis,
    factual_plan_schema,
    factual_prompt_view,
    render_factual_plan,
)


def mention(index=1, **values):
    return Mention(
        id=index,
        client_id=1,
        source=MentionSource.news_rss,
        url=f"https://example.test/publication/{index}",
        title=values.pop("title", "Encuentro de instituciones"),
        content=values.pop("content", "Se invitó a las instituciones a otra edición."),
        summary=values.pop("summary", "Resumen derivado sin autoridad documental."),
        author=values.pop("author", None),
        published_at=datetime(2026, 10, 20, 12, tzinfo=UTC),
        **values,
    )


def content_for(*rows):
    return {
        "schema": 2,
        "coverage": {},
        "redes": {},
        "personas": [],
        "pendientes": [],
        "agenda": [],
        "date": "2026-10-20",
        "timezone": "UTC",
        "window": {
            "from": "2026-10-20T00:00:00+00:00",
            "to": "2026-10-21T00:00:00+00:00",
        },
        "evidence": freeze_sources(list(rows)),
        "noticias": [
            {
                "source_refs": [i],
                "material_ref": i,
                "summary": row.summary,
                "title": row.title,
                "when_label": "20 oct",
            }
            for i, row in enumerate(rows)
        ],
    }


def prepared(*rows, client_id=1):
    content = content_for(*rows)
    content["factual_basis"] = build_factual_basis(content, rows, client_id=client_id)
    return content


def test_contextual_schema_is_detached_and_preserves_static_callers_control():
    content = prepared(mention(), mention(2, title="Otra publicación"))
    before = deepcopy(content)
    static = factual_plan_schema()
    schema = factual_plan_schema(content)
    assert schema["required"] == static["required"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["headline_index"]["anyOf"] == [
        {"type": "integer", "enum": [0, 1]},
        {"type": "null"},
    ]
    for key in ("categoria", "frame", "action"):
        assert (
            schema["$defs"]["_Pick"]["properties"][key]
            == static["$defs"]["_Pick"]["properties"][key]
        )
    assert static["properties"]["items"]["maxItems"] == 1000
    schema["properties"]["items"]["maxItems"] = 0
    packet = factual_prompt_view(content)
    packet["stories"][0]["source_choices"][0]["passage_indices"].clear()
    assert content == before
    assert factual_plan_schema(content)["properties"]["items"]["maxItems"] == 2
    assert factual_plan_schema() == static


def test_empty_contextual_schema_allows_only_empty_arrays_and_null_headline_control():
    content = prepared()
    before = deepcopy(content)
    schema = factual_plan_schema(content)
    assert schema["properties"]["items"]["maxItems"] == 0
    assert schema["properties"]["seleccion"]["maxItems"] == 0
    assert schema["properties"]["headline_index"]["anyOf"] == [{"type": "null"}]
    assert factual_prompt_view(content)["stories"] == []
    assert content == before


@pytest.mark.parametrize("field,value", [("fingerprint", "0" * 64), ("version", True)])
def test_contextual_schema_rejects_stale_or_malformed_material_control(field, value):
    content = prepared(mention())
    content["factual_basis"][field] = value
    with pytest.raises(FactualPlanError):
        factual_plan_schema(content)


def test_new_passages_preserve_complete_sentences_and_original_bytes():
    sentences = [
        f"La institución informó sobre el acuerdo número {i} y sus condiciones. "
        for i in range(35)
    ]
    body = "".join(sentences).strip()
    row = mention(content=body)
    content = prepared(row)
    bank = content["factual_basis"]
    assert bank.get("passage_scheme") == "readable-v1"
    source = bank["sources"][0]
    assert source["original"] == body
    assert len(source["passages"]) <= 7
    assert all(passage.endswith(".") for passage in source["passages"])
    assert all(passage.startswith("La institución") for passage in source["passages"])
    assert all(passage in body for passage in source["passages"])
    assert row.content == body


def test_contextual_analysis_renders_separate_premises_consequence_and_attention():
    content = prepared(mention())
    selector = {"index": 0, "source_ref": 0, "passage_index": 0}
    analysis = {
        "premises": [selector],
        "interpretation": "La invitación puede abrir interlocución académica.",
        "consequence": "Si hay continuidad, podría ampliarse la cooperación.",
        "attention": "Observar si se publican propuestas de colaboración.",
        "conditions": "La invitación no acredita un compromiso adoptado.",
        "relevance": "La vinculación institucional ofrece un ámbito de seguimiento, sin atribuir facultades.",
    }
    plan = {
        "basis_fingerprint": content["factual_basis"]["fingerprint"],
        "headline_index": 0,
        "headline_frame": "negotiation",
        "headline_analysis": analysis,
        "items": [selector],
        "seleccion": [
            {
                "index": 0,
                "categoria": "decision",
                "frame": "negotiation",
                "action": "monitor_followup",
                "analysis": analysis,
            }
        ],
    }
    output = render_factual_plan(content, plan)
    assert analysis["interpretation"] in output["headline"]
    assert analysis["consequence"] in output["headline"]
    pick = output["seleccion"][0]
    assert "Premisa documental" in pick["razon"]
    assert "Se invitó a las instituciones" in pick["razon"]
    assert pick["accion_sugerida"] == analysis["attention"]
    assert pick["condicion"] == analysis["conditions"]
    assert output["references"]["seleccion.0.condicion"] == [0]
    assert (
        content["noticias"][0]["summary"]
        == "Resumen derivado sin autoridad documental."
    )


def test_contextual_schema_resolves_nested_premise_selectors():
    content = prepared(mention())
    schema = factual_plan_schema(content)

    def inspect(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = schema
                for part in node["$ref"].removeprefix("#/").split("/"):
                    assert part in target, node["$ref"]
                    target = target[part]
            for value in node.values():
                inspect(value)
        elif isinstance(node, list):
            for value in node:
                inspect(value)

    inspect(schema)
    assert (
        schema["$defs"]["_Analysis"]["properties"]["premises"]["items"]["$ref"]
        == "#/$defs/_Item"
    )


@pytest.mark.parametrize("scheme", ["legacy", "unknown", None, True])
def test_old_banks_keep_exact_600_chunks_without_default_fingerprint_rewrite_control(
    scheme,
):
    import hashlib

    row = mention(content="Una oración documental completa. " * 70)
    content = prepared(row)
    bank = content["factual_basis"]
    bank.pop("passage_scheme")
    source = bank["sources"][0]
    source["passages"] = [
        source["original"][start : start + 600].strip()
        for start in range(0, len(source["original"]), 600)
    ]
    if scheme != "legacy":
        bank["passage_scheme"] = scheme
    body = {key: value for key, value in bank.items() if key != "fingerprint"}
    bank["fingerprint"] = hashlib.sha256(
        json.dumps(
            body,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    before = deepcopy(content)
    if scheme == "legacy":
        packet = factual_prompt_view(content)
        assert packet["sources"][0]["passages"] == source["passages"]
        assert packet["basis_fingerprint"] == bank["fingerprint"]
        assert "passage_scheme" not in content["factual_basis"]
    else:
        with pytest.raises(FactualPlanError):
            factual_prompt_view(content)
    assert content == before


def test_basis_separates_publication_from_occurrence_and_derivative():
    body = "El encuentro ocurrió el viernes anterior. " + "Contenido literal. " * 260
    row = mention(
        content=body, summary="El acto ocurrió el 20 de octubre; hubo un compromiso."
    )
    content = content_for(row)
    original = deepcopy(content)
    basis = build_factual_basis(content, [row], client_id=1)
    assert isinstance(basis, dict)
    assert basis["sources"][0]["publication_date"] == "2026-10-20T12:00:00+00:00"
    assert "occurrence_date" not in basis["sources"][0]
    assert basis["sources"][0]["original"] == body[:4000]
    assert basis["sources"][0]["derived_summary"] == row.summary
    assert basis["sources"][0]["captured_author"] is None
    assert json.dumps(content, sort_keys=True) == json.dumps(original, sort_keys=True)
    assert len(content["evidence"]["sources"][0]) == 10
    assert len(content["evidence"]["sources"][0]["excerpt"]) == 300


@pytest.mark.parametrize("replacement", ["different", "foreign", "missing_excerpt"])
def test_full_body_requires_owned_immutable_identity_and_frozen_prefix(replacement):
    row = mention(content="Texto capturado. " * 30)
    content = content_for(row)
    candidate = SimpleNamespace(id=row.id, client_id=1, content=row.content)
    if replacement == "different":
        candidate.content = "Texto cambiado después de la captura."
    elif replacement == "foreign":
        candidate.client_id = 2
    else:
        row.content = None
        content = content_for(row)
        candidate.content = "Un cuerpo ausente de la captura no puede ampliarse."
    basis = build_factual_basis(content, [candidate], client_id=1)
    assert (
        basis["sources"][0]["original"] == content["evidence"]["sources"][0]["excerpt"]
    )


def test_prompt_uses_literal_passages_not_derivative_authority_or_identifiers():
    row = mention(content="El acta no establece una fecha. " * 150)
    title_only = mention(
        2, title="T" * 953, content=None, summary="Un compromiso inventado."
    )
    content = prepared(row, title_only)
    packet = factual_prompt_view(content)
    assert isinstance(packet, dict)
    assert packet["basis_fingerprint"] == content["factual_basis"]["fingerprint"]
    assert packet["stories"][1]["material_ref"] == 1
    for source, original in zip(
        packet["sources"], [row.content[:4000], title_only.title]
    ):
        assert source["passages"]
        assert all(passage and passage in original for passage in source["passages"])
    assert packet["sources"][1]["passage_kind"] == "title"
    assert packet["sources"][0]["passage_kind"] == "body"
    assert packet["sources"][1]["passages"] == [title_only.title]
    encoded = json.dumps(packet, ensure_ascii=False)
    for forbidden in (
        "mention_id",
        "client_id",
        "url",
        "derived_summary",
        row.summary,
        title_only.summary,
    ):
        assert forbidden not in encoded


def test_source_only_render_is_complete_attributed_and_does_not_invent_relations():
    rows = [
        mention(
            content="El acto ocurrió el viernes anterior. No se publicó su fecha exacta."
        ),
        mention(
            2,
            title="Participantes en una reunión",
            content="Asistieron una directora, un alcalde y una rectora.",
        ),
        mention(
            3,
            title="Invitación a otra edición",
            content="Se invitó a las instituciones a otra edición.",
        ),
        mention(4, title="Comunicado que menciona una institución", content=None),
    ]
    content = prepared(*rows)
    before = json.dumps(content, sort_keys=True)
    output = render_factual_plan(content)
    assert isinstance(output, dict)
    assert set(output) == {
        "headline",
        "items",
        "seleccion",
        "agenda",
        "redes",
        "personas",
        "references",
    }
    assert [entry["index"] for entry in output["items"]] == [0, 1, 2, 3]
    assert "análisis político no disponible" in output["headline"]
    assert output["seleccion"] == output["agenda"] == output["personas"] == []
    assert output["redes"] == {}
    for index, row in enumerate(rows):
        summary = output["items"][index]["summary"]
        assert row.title in summary
        assert "Fecha de publicación registrada: 2026-10-20T12:00:00+00:00" in summary
        assert "Autor no registrado" in summary
        assert output["references"][f"items.{index}.summary"] == [index]
        assert row.summary not in summary
        assert (row.content or row.title) in summary
    text = json.dumps(output, ensure_ascii=False)
    for invented in (
        "tres máximas autoridades",
        "se comprometieron",
        "cuenta institucional",
        "acto del 20",
    ):
        assert invented not in text
    assert json.dumps(content, sort_keys=True) == before


def replace_path(target, path, value):
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


@pytest.mark.parametrize(
    "path,value",
    [
        (("factual_basis", "fingerprint"), "0" * 64),
        (("factual_basis", "version"), True),
        (("factual_basis", "client_id"), True),
        (("factual_basis", "stories", 0, "index"), False),
        (("factual_basis", "stories", 0, "material_ref"), False),
        (("factual_basis", "sources", 0, "original"), "Un cuerpo alterado."),
        (("factual_basis", "sources", 0, "passages"), ["Un pasaje inventado."]),
        (("factual_basis", "sources", 0, "occurrence_date"), "2026-10-20"),
        (("noticias", 0, "source_refs"), [True]),
        (("noticias", 0, "source_refs"), [0, 0]),
        (("noticias", 0, "material_ref"), 1),
        (("window", "from"), "2026-10-19T00:00:00+00:00"),
        (("client_id",), 2),
        (("evidence", "sources", 0, "summary"), "Derivado cambiado."),
        (("evidence", "catalogue_fingerprint"), "0" * 64),
    ],
)
def test_stale_or_malformed_basis_is_rejected_before_any_use(path, value):
    content = prepared(mention())
    replace_path(content, path, value)
    before = json.dumps(content, sort_keys=True)
    for consume in (factual_prompt_view, render_factual_plan):
        with pytest.raises(FactualPlanError):
            consume(content)
    assert json.dumps(content, sort_keys=True) == before


def plan_for(content):
    return {
        "basis_fingerprint": content["factual_basis"]["fingerprint"],
        "headline_index": 1,
        "headline_frame": "visibility",
        "items": [],
        "seleccion": [
            {
                "index": 1,
                "categoria": "a_favor",
                "frame": "governance_followup",
                "action": "verify_record",
            }
        ],
    }


def test_model_selects_only_existing_material_and_code_owned_analysis():
    rows = [
        mention(content="Primera captura. " * 80),
        mention(2, content="Segunda captura. " * 80),
        mention(3, title="Otra noticia"),
    ]
    content = content_for(*rows)
    content["noticias"] = [
        {**content["noticias"][0], "source_refs": [0, 1]},
        content["noticias"][2],
    ]
    content["factual_basis"] = build_factual_basis(content, rows, client_id=1)
    plan = plan_for(content)
    plan["items"] = [{"index": 0, "source_ref": 1, "passage_index": 1}]
    before = json.dumps([content, plan], sort_keys=True)
    output = render_factual_plan(content, plan)
    assert len(output["seleccion"]) == 1
    assert output["seleccion"][0]["categoria"] == "a_favor"
    assert output["seleccion"][0]["index"] == 1
    assert output["seleccion"][0]["razon"].startswith("Lectura política")
    assert output["seleccion"][0]["accion_sugerida"].startswith("Atención sugerida")
    assert "Otra noticia" in output["headline"]
    assert "Lectura política" in output["headline"]
    assert [item["index"] for item in output["items"]] == [0, 1]
    assert (
        content["factual_basis"]["sources"][1]["passages"][1]
        in output["items"][0]["summary"]
    )
    assert output["references"]["items.0.summary"] == [1]
    assert output["references"]["seleccion.1.razon"] == [2]
    assert output["references"]["seleccion.1.accion_sugerida"] == [2]
    assert json.dumps([content, plan], sort_keys=True) == before


@pytest.mark.parametrize(
    "path,value",
    [
        (("headline",), "La asistencia acredita las tres máximas autoridades."),
        (("rationale",), "La invitación demuestra un compromiso."),
        (("basis_fingerprint",), "0" * 64),
        (("headline_index",), True),
        (("headline_index",), "1"),
        (("headline_index",), 1.0),
        (("headline_index",), -1),
        (("headline_index",), 2),
        (("headline_frame",), "invented"),
        (("items", 0, "index"), False),
        (("items", 0, "index"), "0"),
        (("items", 0, "index"), 2),
        (("items", 0, "source_ref"), 1),
        (("items", 0, "source_ref"), True),
        (("items", 0, "source_ref"), "0"),
        (("items", 0, "passage_index"), True),
        (("items", 0, "passage_index"), -1),
        (("items", 0, "passage_index"), 1),
        (("items", 0, "summary"), "La publicación y el acto tienen la misma fecha."),
        (("seleccion", 0, "index"), False),
        (("seleccion", 0, "index"), 2),
        (("seleccion", 0, "categoria"), "benefit"),
        (("seleccion", 0, "frame"), "invented"),
        (("seleccion", 0, "action"), "invented"),
        (("seleccion", 0, "razon"), "La cuenta pertenece a la institución mencionada."),
        (("items",), [{"index": 0, "source_ref": 0, "passage_index": 0}] * 2),
        (
            ("seleccion",),
            [
                {
                    "index": 1,
                    "categoria": "ruido",
                    "frame": "visibility",
                    "action": "verify_record",
                }
            ]
            * 2,
        ),
    ],
)
def test_invalid_plan_is_atomic_and_never_licenses_generated_relations(path, value):
    content = prepared(mention(), mention(2))
    plan = plan_for(content)
    plan["items"] = [{"index": 0, "source_ref": 0, "passage_index": 0}]
    replace_path(plan, path, value)
    before = json.dumps([content, plan], sort_keys=True)
    with pytest.raises(FactualPlanError):
        render_factual_plan(content, plan)
    assert json.dumps([content, plan], sort_keys=True) == before


def test_private_schema_bounds_facts_and_separates_optional_contextual_analysis():
    schema = factual_plan_schema()
    assert isinstance(schema, dict)
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "basis_fingerprint",
        "headline_index",
        "headline_frame",
        "headline_analysis",
        "items",
        "seleccion",
    }
    assert set(schema["required"]) == {
        "basis_fingerprint",
        "headline_index",
        "headline_frame",
        "items",
        "seleccion",
    }
    assert set(schema["$defs"]["_Analysis"]["required"]) == {
        "premises",
        "interpretation",
        "consequence",
        "attention",
        "conditions",
        "relevance",
    }
    assert schema["properties"]["items"]["maxItems"] == 1000
    assert schema["properties"]["seleccion"]["maxItems"] == 1000
    definitions = schema["$defs"]
    assert definitions["_Item"]["additionalProperties"] is False
    assert definitions["_Pick"]["additionalProperties"] is False
    assert set(definitions["_Item"]["properties"]) == {
        "index",
        "source_ref",
        "passage_index",
    }
    assert set(definitions["_Pick"]["properties"]) == {
        "index",
        "categoria",
        "frame",
        "action",
        "analysis",
    }
    assert definitions["_Item"]["properties"]["passage_index"]["exclusiveMaximum"] == 7
    assert set(schema["properties"]["headline_frame"]["enum"]) == {
        "visibility",
        "governance_followup",
        "execution_logistics",
        "reputational_exposure",
        "coverage_gaps",
        "negotiation",
        "institutional_positioning",
    }
    from app.summaries.factual_contract import FACTUAL_SYSTEM_PROMPT

    assert "fecha de publicación" in FACTUAL_SYSTEM_PROMPT
    assert "no es verificación" in FACTUAL_SYSTEM_PROMPT
    assert "sin rellenar" in FACTUAL_SYSTEM_PROMPT
    schema["properties"].clear()
    assert factual_plan_schema()["properties"]


# Preservation controls: these exercise unchanged legacy behavior, not new REDs.
def test_historical_receiver_keeps_uncited_authored_prose():
    from app.summaries.digest import apply_narrative

    content = content_for(mention())
    errors = apply_narrative(
        content,
        {
            "headline": "Lectura histórica sin referencias.",
            "items": [{"index": 0, "summary": "Prosa histórica válida sin cita."}],
            "unknown_legacy_key": True,
        },
    )
    assert not errors
    assert (
        content["provenance"]["headline"]["text"]
        == "Lectura histórica sin referencias."
    )
    assert content["noticias"][0]["summary"] == "Prosa histórica válida sin cita."
    assert content["noticias"][0]["provenance"]["summary"]["state"] == "unbacked"


def test_valid_plan_and_fallback_payloads_merge_through_unchanged_receiver():
    from app.summaries.digest import apply_narrative

    content = prepared(mention(), mention(2))
    for plan in (None, plan_for(content)):
        output = render_factual_plan(content, plan)
        target = deepcopy(content)
        assert apply_narrative(target, output) == []
        for item in output["items"]:
            assert target["noticias"][item["index"]]["summary"] == item["summary"]


@pytest.mark.parametrize("category", ["decision", "riesgo", "ruido", "a_favor"])
def test_categories_remain_model_choices_without_tone_or_count_padding(category):
    content = prepared(mention(), mention(2), mention(3))
    plan = plan_for(content)
    plan["seleccion"][0]["categoria"] = category
    output = render_factual_plan(content, plan)
    assert [(item["index"], item["categoria"]) for item in output["seleccion"]] == [
        (1, category)
    ]
    plan["seleccion"] = []
    plan["headline_index"] = None
    assert render_factual_plan(content, plan)["seleccion"] == []


def test_all_catalogued_frames_and_actions_render_without_custom_fact_slots():
    content = prepared(mention(), mention(2))
    schema = factual_plan_schema()
    frames = schema["properties"]["headline_frame"]["enum"]
    actions = schema["$defs"]["_Pick"]["properties"]["action"]["enum"]
    for frame, action in zip(frames, actions, strict=True):
        plan = plan_for(content)
        plan["headline_frame"] = plan["seleccion"][0]["frame"] = frame
        plan["seleccion"][0]["action"] = action
        output = render_factual_plan(content, plan)
        assert output["headline"].startswith("Lectura política")
        assert output["seleccion"][0]["accion_sugerida"].startswith("Atención sugerida")


def test_two_tenants_source_zero_and_bank_zero_are_not_interchangeable():
    first = prepared(mention())
    second_row = mention(91, title="Otra persona y otra institución")
    second_row.client_id = 2
    second = prepared(second_row, client_id=2)
    first_plan = {
        "basis_fingerprint": first["factual_basis"]["fingerprint"],
        "headline_index": 0,
        "headline_frame": "visibility",
        "items": [],
        "seleccion": [],
    }
    with pytest.raises(FactualPlanError):
        render_factual_plan(second, first_plan)
    second["factual_basis"] = first["factual_basis"]
    with pytest.raises(FactualPlanError):
        factual_prompt_view(second)


@pytest.mark.parametrize("plan", [{}, [], False, 0, "{}", {"items": []}])
def test_nonnull_invalid_plans_are_not_fallback_requests(plan):
    with pytest.raises(FactualPlanError):
        render_factual_plan(prepared(mention()), plan)


def test_empty_and_missing_source_slots_have_complete_safe_output():
    content = content_for()
    content["noticias"] = [
        {"source_refs": [], "material_ref": None, "summary": "Derivado sin fuente."}
    ]
    content["factual_basis"] = build_factual_basis(content)
    output = render_factual_plan(content)
    assert [item["index"] for item in output["items"]] == [0]
    assert (
        output["items"][0]["summary"]
        == "Material original no disponible para esta noticia."
    )
    assert output["references"]["items.0.summary"] == []
    assert output["seleccion"] == []
    content["noticias"] = []
    content["factual_basis"] = build_factual_basis(content)
    assert render_factual_plan(content)["items"] == []


def test_registered_people_and_mutable_summary_never_become_literal_inputs():
    content = prepared(mention())
    content["noticias"][0].update(
        summary="Contaminación del derivado.",
        when_label="Un día no documentado",
        person_ids=[9],
    )
    content["personas"] = [
        {
            "name": "Nombre registrado",
            "role": "Máxima autoridad",
            "fact": "Presidió todos los actos.",
        }
    ]
    packet = json.dumps(factual_prompt_view(content), ensure_ascii=False)
    output = json.dumps(render_factual_plan(content), ensure_ascii=False)
    for forbidden in (
        "Contaminación",
        "Un día no documentado",
        "Nombre registrado",
        "Máxima autoridad",
        "Presidió",
    ):
        assert forbidden not in packet + output


def test_owned_captured_author_is_attributed_not_verified_and_null_dates_stay_null():
    row = mention(author="Cuenta capturada")
    row.published_at = None
    content = prepared(row)
    output = render_factual_plan(content)
    summary = output["items"][0]["summary"]
    assert "Autor capturado (identidad no verificada): «Cuenta capturada»" in summary
    assert "Fecha de publicación no registrada" in summary
    assert "2026-10-20" not in summary


@pytest.mark.parametrize("client_id", [True, "1", 1.0, 0, -1])
def test_build_rejects_coerced_client_identity(client_id):
    with pytest.raises(FactualPlanError):
        build_factual_basis(content_for(mention()), client_id=client_id)


def test_full_source_without_tenant_argument_still_requires_an_exact_integer_id():
    row = mention(content="Texto documentado. " * 40)
    content = content_for(row)
    forged = SimpleNamespace(id=True, client_id=1, content=row.content)
    basis = build_factual_basis(content, [forged])
    assert (
        basis["sources"][0]["original"] == content["evidence"]["sources"][0]["excerpt"]
    )


def test_source_objects_and_json_scalars_are_preserved_by_all_pure_interfaces():
    row = mention(content="Original con Unicode ñ y cifras 0. " * 40)
    content = content_for(row)
    content["unrelated"] = {
        "boolean": True,
        "integer": 1,
        "decimal": 1.0,
        "null": None,
        "list": [False, 0],
    }
    before = json.dumps(content, sort_keys=True, ensure_ascii=False)
    row_before = {
        key: value for key, value in vars(row).items() if key != "_sa_instance_state"
    }
    basis = build_factual_basis(content, [row], client_id=1)
    content["factual_basis"] = basis
    packet = factual_prompt_view(content)
    packet["sources"][0]["passages"].clear()
    output = render_factual_plan(content)
    output["references"]["items.0.summary"].clear()
    assert factual_prompt_view(content)["sources"][0]["passages"]
    assert render_factual_plan(content)["references"]["items.0.summary"] == [0]
    content.pop("factual_basis")
    assert json.dumps(content, sort_keys=True, ensure_ascii=False) == before
    assert {
        key: value for key, value in vars(row).items() if key != "_sa_instance_state"
    } == row_before


def test_invalid_unicode_catalogue_is_rejected_as_a_factual_contract_error():
    content = content_for(mention())
    content["evidence"]["sources"][0]["title"] = "Invalid surrogate: \ud800"
    with pytest.raises(FactualPlanError):
        build_factual_basis(content)


def test_content_client_identity_also_scopes_optional_full_source_expansion():
    row = mention(content="Cuerpo congelado. " * 30)
    content = content_for(row)
    content["client_id"] = 1
    foreign = SimpleNamespace(id=row.id, client_id=2, content=row.content)
    basis = build_factual_basis(content, [foreign])
    assert basis["client_id"] == 1
    assert (
        basis["sources"][0]["original"] == content["evidence"]["sources"][0]["excerpt"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("passages", ["Una relación que nunca estuvo en el original."]),
        ("passage_kind", "title"),
        ("publication_date", "2026-10-19"),
        ("captured_author", "Propietario supuesto"),
        ("original", "Un original completamente distinto."),
        ("title", "Un titular de otra noticia"),
    ],
)
def test_recomputed_hash_does_not_replace_material_and_passage_validation(field, value):
    import hashlib

    content = prepared(mention())
    bank = content["factual_basis"]
    bank["sources"][0][field] = value
    material = {key: item for key, item in bank.items() if key != "fingerprint"}
    bank["fingerprint"] = hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    with pytest.raises(FactualPlanError):
        factual_prompt_view(content)
    with pytest.raises(FactualPlanError):
        render_factual_plan(content)


def test_original_and_derivative_limits_remain_separate_with_excerpt_fallback():
    row = mention(content="Texto original. " * 400, summary="Derivado. " * 80)
    original_evidence = freeze_sources([row])
    content = content_for(row)
    bank = build_factual_basis(content, [row], client_id=1)
    assert len(bank["sources"][0]["original"]) == 4000
    assert len(bank["sources"][0]["derived_summary"]) == 300
    assert content["evidence"] == original_evidence
    fallback = build_factual_basis(content)
    assert (
        fallback["sources"][0]["original"] == original_evidence["sources"][0]["excerpt"]
    )
    assert len(fallback["sources"][0]["original"]) == 300


def test_valid_uncited_strategic_choice_has_no_zero_reference_gate():
    content = content_for()
    content["noticias"] = [{"source_refs": [], "material_ref": None}]
    content["factual_basis"] = build_factual_basis(content)
    plan = plan_for(content)
    plan["headline_index"] = 0
    plan["seleccion"][0]["index"] = 0
    output = render_factual_plan(content, plan)
    assert len(output["seleccion"]) == 1
    assert output["references"]["seleccion.0.razon"] == []
    assert "Lectura política" in output["headline"]


def test_new_bank_material_limits_reject_overflow_without_altering_legacy_catalogue():
    row = mention(title="L" * 4001)
    content = content_for(row)
    before = json.dumps(content, sort_keys=True)
    with pytest.raises(FactualPlanError):
        build_factual_basis(content, [row], client_id=1)
    assert json.dumps(content, sort_keys=True) == before
