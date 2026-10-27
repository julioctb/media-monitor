"""Two-cut receipts through public generation, merge and source resolution."""

import copy
import json

import pytest

from app.summaries import build_daily_summary
from app.summaries.evidence import resolved_provenance
from app.summaries.digest import apply_narrative, render_plain_text
from tests.test_digest_comparison import CURRENT, _client, _failed, _mention, _prior


def comparison_build(session, payload):
    owner = _client(session)
    old, prior = _prior(session, owner)
    _mention(
        session,
        owner,
        CURRENT,
        "Se informa un acuerdo firmado.",
        title="Firma del acuerdo presupuestario",
        event_id=old.event_id,
    )
    row = build_daily_summary(
        session,
        client_id=owner.id,
        day=CURRENT.date(),
        generate=lambda prompt: json.dumps(payload),
    )
    return owner, row, prior


def test_public_build_keeps_separate_zero_receipts_backward_safe(session):
    payload = {
        "headline": "Comparación de los cortes.",
        "items": [
            {
                "index": 0,
                "summary": "El corte actual informa un acuerdo.",
                "angulo_nuevo": "El material pasa de negociación a acuerdo.",
            }
        ],
        "seleccion": [
            {
                "index": 0,
                "categoria": "decision",
                "razon": "Atender el acuerdo comparado.",
            }
        ],
        "comparison_references": {
            path: {"current": [0], "prior": [0]}
            for path in (
                "headline",
                "items.0.summary",
                "items.0.angulo_nuevo",
                "seleccion.0.razon",
            )
        },
    }
    _, row, prior = comparison_build(session, payload)
    content = row.content
    assert (
        content["evidence"]["sources"][0]["mention_id"]
        != prior.content["evidence"]["sources"][0]["mention_id"]
    )
    for target, field, allowed in [
        (content, "headline", None),
        (content["noticias"][0], "summary", [0]),
        (content["noticias"][0], "angulo_nuevo", [0]),
        (content["tarjetas"][0], "hecho", [0]),
        (content["brief"]["decisiones"][0], "razon", [0]),
    ]:
        stored = target["provenance"][field]
        assert stored["state"] == "unbacked"
        assert stored["comparison"]["current"] == [0]
        assert stored["comparison"]["prior"] == [0]
        receipt = resolved_provenance(
            content,
            target,
            field,
            text=row.narrative if field == "headline" else None,
            allowed=allowed,
        )
        assert receipt["state"] == "linked"
        assert receipt["comparison"]["prior"] == [0]


@pytest.mark.parametrize("linked", [True, False])
def test_public_same_context_recovery_preserves_two_namespace_receipts(session, linked):
    refs = (
        {"current": [0], "prior": [0]}
        if linked
        else {"current": [0], "prior": ["prior:0"]}
    )
    owner, first, _ = comparison_build(
        session,
        {
            "headline": "Comparación recuperada.",
            "items": [{"index": 0, "angulo_nuevo": "Comparación retenida."}],
            "comparison_references": {"headline": refs, "items.0.angulo_nuevo": refs},
        },
    )
    original = copy.deepcopy(first.content)
    row = build_daily_summary(
        session, client_id=owner.id, day=CURRENT.date(), generate=_failed
    )
    assert row.mode == "llm"
    for target, old, field, scope in [
        (row.content, original, "headline", None),
        (row.content["noticias"][0], original["noticias"][0], "angulo_nuevo", [0]),
    ]:
        assert target["provenance"][field] == old["provenance"][field]
        receipt = resolved_provenance(
            row.content,
            target,
            field,
            text=row.narrative if field == "headline" else None,
            allowed=scope,
        )
        assert receipt["state"] == ("linked" if linked else "unbacked")


@pytest.mark.parametrize("bad", [None, [], True, "invalid"])
def test_malformed_comparison_map_never_falls_back_to_current_only(session, bad):
    _, row, _ = comparison_build(
        session,
        {
            "headline": "Texto válido retenido.",
            "references": {"headline": [0]},
            "comparison_references": bad,
        },
    )
    binding = row.content["provenance"]["headline"]
    assert row.narrative == "Texto válido retenido."
    assert "comparison" in binding
    assert (
        resolved_provenance(row.content, row.content, "headline", text=row.narrative)[
            "state"
        ]
        == "unbacked"
    )


@pytest.fixture
def two_cut_content():
    from types import SimpleNamespace
    from app.summaries.comparison import freeze_comparison
    from app.summaries.builder import _delta_key
    from app.summaries.evidence import catalogue_fingerprint

    def cut(day, offset):
        sources = [
            {
                "index": i,
                "mention_id": offset + i,
                "source": "news_rss",
                "url": f"https://medio.test/{offset}/{i}",
                "outlet": "medio.test",
                "author": "María",
                "title": f"Publicación {offset}-{i}",
                "published_at": f"{day}T18:00:00+00:00",
                "summary": "á" + "😀" * 299,
                "excerpt": "Material capturado.",
            }
            for i in range(3)
        ]
        evidence = {"version": 1, "sources": sources}
        evidence["catalogue_fingerprint"] = catalogue_fingerprint(evidence)
        return {
            "schema": 2,
            "coverage": {},
            "redes": {},
            "personas": [],
            "pendientes": [],
            "agenda": [],
            "date": day,
            "timezone": "America/Mexico_City",
            "evidence": evidence,
            "noticias": [
                {
                    "event_id": i + 1,
                    "title": f"Asunto {i}",
                    "summary": "Hecho actual.",
                    "source_refs": [i],
                    "material_ref": i,
                    "tone": {"neutral": 1},
                }
                for i in range(2)
            ],
        }

    prior = cut("2026-10-09", 10)
    content = cut("2026-10-14", 20)
    content["comparison"] = freeze_comparison(
        SimpleNamespace(content=prior, summary_date=CURRENT.date().replace(day=9)),
        content["noticias"],
        _delta_key,
    )
    return content


def merge_comparison(content, refs=None, field="summary"):
    refs = {"current": [0], "prior": [0]} if refs is None else refs
    payload = {
        "items": [{"index": 0, field: "Prosa comparativa retenida."}],
        "references": {f"items.0.{field}": [0]},
        "comparison_references": {f"items.0.{field}": refs},
    }
    assert apply_narrative(content, payload) == []
    return content["noticias"][0]


@pytest.mark.parametrize("namespace", ["current", "prior"])
@pytest.mark.parametrize("bad", [True, "0", "prior:0", -1, 3, 0.5, None])
def test_merge_rejects_strict_invalid_refs_without_losing_prose(
    two_cut_content, namespace, bad
):
    refs = {"current": [0], "prior": [0]}
    refs[namespace] = [0, bad]
    note = merge_comparison(two_cut_content, refs)
    assert note["summary"] == "Prosa comparativa retenida."
    assert (
        resolved_provenance(two_cut_content, note, "summary", allowed=[0])["state"]
        == "unbacked"
    )


@pytest.mark.parametrize(
    "refs",
    [
        {"current": [0], "prior": [1]},
        {"current": [1], "prior": [0]},
        {"current": [0], "prior": [2]},
        {"current": [], "prior": [0]},
        {"current": [0], "prior": []},
        {"current": [0]},
        {"prior": [0]},
        {"current": [0], "prior": [0], "version": 99},
    ],
)
def test_merge_rejects_foreign_unsupplied_partial_comparison_sets(
    two_cut_content, refs
):
    note = merge_comparison(two_cut_content, refs)
    assert (
        resolved_provenance(two_cut_content, note, "summary", allowed=[0])["state"]
        == "unbacked"
    )


def test_missing_angle_namespaces_cannot_upgrade_current_only_refs(two_cut_content):
    content = two_cut_content
    assert (
        apply_narrative(
            content,
            {
                "items": [
                    {
                        "index": 0,
                        "summary": "Hecho actual.",
                        "angulo_nuevo": "Comparación no citada.",
                    }
                ],
                "references": {"items.0.summary": [0], "items.0.angulo_nuevo": [0]},
            },
        )
        == []
    )
    note = content["noticias"][0]
    assert (
        resolved_provenance(content, note, "summary", allowed=[0])["state"] == "linked"
    )
    assert "comparison" in note["provenance"]["angulo_nuevo"]
    assert (
        resolved_provenance(content, note, "angulo_nuevo", allowed=[0])["state"]
        == "unbacked"
    )
    legacy = copy.deepcopy(content)
    legacy.pop("comparison")
    apply_narrative(
        legacy,
        {
            "items": [{"index": 0, "angulo_nuevo": "Solo corte actual."}],
            "references": {"items.0.angulo_nuevo": [0]},
        },
    )
    assert (
        resolved_provenance(legacy, legacy["noticias"][0], "angulo_nuevo", allowed=[0])[
            "state"
        ]
        == "linked"
    )


def test_nonstory_comparison_metadata_cannot_fall_back_to_current_receipt(
    two_cut_content,
):
    content = two_cut_content
    apply_narrative(
        content,
        {
            "agenda": [{"when": "15 octubre", "title": "Plazo documentado"}],
            "references": {"agenda.0.title": [0]},
            "comparison_references": {"agenda.0.title": {"current": [0], "prior": [0]}},
        },
    )
    entry = content["agenda"][0]
    assert entry["title"] == "Plazo documentado"
    assert "comparison" in entry["provenance"]["title"]
    assert resolved_provenance(content, entry, "title")["state"] == "unbacked"


@pytest.mark.parametrize(
    "change",
    [
        "text",
        "current_material",
        "prior_material",
        "current_date",
        "prior_date",
        "timezone",
        "window",
        "coverage",
        "scope",
        "correspondence",
        "unicode_current",
        "unicode_prior",
        "unknown",
        "mixed",
        "malformed",
        "origin",
        "outer_state",
    ],
)
def test_reader_revalidates_actual_raw_text_and_complete_context(
    two_cut_content, change
):
    content = two_cut_content
    note = merge_comparison(content)
    assert (
        resolved_provenance(content, note, "summary", allowed=[0])["state"] == "linked"
    )
    binding = note["provenance"]["summary"]
    if change == "text":
        note["summary"] += " https://x.test/"
    elif change in ("current_material", "prior_material"):
        catalogue = (
            content["evidence"]
            if change == "current_material"
            else content["comparison"]["evidence"]
        )
        catalogue["sources"][2]["excerpt"] = "Cambió material no citado."
    elif change in ("unicode_current", "unicode_prior"):
        evidence = (
            content["evidence"]
            if change == "unicode_current"
            else content["comparison"]["evidence"]
        )
        evidence["sources"][0]["excerpt"] = "\ud800"
    elif change == "current_date":
        content["date"] = "2026-10-15"
    elif change == "prior_date":
        content["comparison"]["date"] = "2026-10-08"
    elif change == "timezone":
        content["comparison"]["timezone"] = "UTC"
    elif change == "window":
        content["comparison"]["window_start"] = "2026-10-08T21:00:00-06:00"
    elif change == "coverage":
        content["comparison"]["coverage_context"][0]["title"] = "Contexto cambiado"
    elif change == "scope":
        content["comparison"]["current_source_scopes"][0] = [False]
    elif change == "correspondence":
        content["comparison"]["stories"][0]["current_indexes"] = [True]
    elif change == "unknown":
        binding["comparison"]["version"] = 99
    elif change == "mixed":
        binding["comparison"]["current"] = [0, False]
    elif change == "malformed":
        binding["comparison"] = None
    elif change == "origin":
        binding["origin"] = "provider_claim"
    else:
        binding["state"] = "linked"
    assert (
        resolved_provenance(content, note, "summary", allowed=[0])["state"]
        == "unbacked"
    )


def test_same_source_index_different_fields_keep_independent_receipts(two_cut_content):
    note = merge_comparison(two_cut_content)
    merge_comparison(two_cut_content, field="why_it_matters")
    note["summary"] = "Texto cambiado"
    assert (
        resolved_provenance(two_cut_content, note, "summary", allowed=[0])["state"]
        == "unbacked"
    )
    assert (
        resolved_provenance(two_cut_content, note, "why_it_matters", allowed=[0])[
            "state"
        ]
        == "linked"
    )


def test_plain_export_distinguishes_namespaces_and_only_cited_sources(two_cut_content):
    content = two_cut_content
    merge_comparison(content)
    plain = render_plain_text(content, "Titular sin referencias.")
    assert "current:#0" in plain
    assert "prior:#0" in plain
    assert "Corte actual: 2026-10-14" in plain
    assert "Corte comparado: 2026-10-09" in plain
    assert "Publicación 10-0" in plain
    assert "Publicación 20-0" in plain
    for uncited in (
        "Publicación 10-1",
        "Publicación 10-2",
        "Publicación 20-1",
        "Publicación 20-2",
    ):
        assert uncited not in plain
    content["noticias"][0]["summary"] = "Prosa cambiada conservada."
    plain = render_plain_text(content, "Titular sin referencias.")
    assert "Prosa cambiada conservada. [No respaldada]" in plain
    assert "prior:#" not in plain
    assert "FUENTES VINCULADAS" not in plain


def test_public_recovery_rejects_identically_malformed_comparison_context(session):
    owner = _client(session)
    old, prior = _prior(session, owner)
    saved = copy.deepcopy(prior.content)
    saved["noticias"][0]["tone"] = {"neutral": True}
    prior.content = saved
    session.commit()
    _mention(
        session,
        owner,
        CURRENT,
        "Material actual.",
        title="Firma del acuerdo actual",
        event_id=old.event_id,
    )
    first = build_daily_summary(
        session,
        client_id=owner.id,
        day=CURRENT.date(),
        generate=lambda _: json.dumps(
            {"headline": "Análisis sobre contexto inválido."}
        ),
    )
    assert first.mode == "llm"
    result = build_daily_summary(
        session, client_id=owner.id, day=CURRENT.date(), generate=_failed
    )
    assert result.mode == "heuristic"
    assert result.narrative != "Análisis sobre contexto inválido."


def test_public_order_and_tail_compilation_keep_original_namespace_ownership(session):
    from datetime import timedelta
    from app.models import Event
    from tests.test_digest_comparison import PRIOR, _view

    owner = _client(session)
    for index in range(11):
        event = Event(
            client_id=owner.id,
            title=f"Asunto institucional {index}",
            title_tokens=f"asunto {index}",
            first_seen_at=PRIOR,
            last_seen_at=CURRENT,
        )
        session.add(event)
        session.commit()
        _mention(
            session,
            owner,
            PRIOR + timedelta(minutes=index),
            f"Premisa previa {index}.",
            title=f"Cobertura anterior del asunto {index}",
            event_id=event.id,
        )
        _mention(
            session,
            owner,
            CURRENT + timedelta(minutes=index),
            f"Material actual {index}.",
            title=f"Cobertura actual del asunto {index}",
            event_id=event.id,
        )
    build_daily_summary(session, client_id=owner.id, day=PRIOR.date())

    def generate(prompt):
        view = _view(prompt)
        news = view["noticias"]
        refs = {
            f"items.{i}.summary": {
                "current": note["source_refs"],
                "prior": [
                    int(ref.split(":")[1])
                    for story in view["comparison"]["stories"]
                    if i in story["current_indexes"]
                    for ref in story["source_refs"]
                ],
            }
            for i, note in enumerate(news)
        }
        refs["seleccion.10.razon"] = refs["items.10.summary"]
        return json.dumps(
            {
                "headline": "Análisis con once historias.",
                "items": [
                    {"index": i, "summary": f"Comparación de la historia {i}."}
                    for i in range(11)
                ],
                "seleccion": [
                    {
                        "index": 10,
                        "categoria": "riesgo",
                        "razon": "Atención a la historia once.",
                    }
                ],
                "comparison_references": refs,
            }
        )

    row = build_daily_summary(
        session, client_id=owner.id, day=CURRENT.date(), generate=generate
    )
    content = row.content
    assert content["noticias"][0]["summary"] == "Comparación de la historia 10."
    pick = content["brief"]["riesgos"][0]
    assert pick["index"] == 0
    assert resolved_provenance(content, pick, "razon", allowed=[10])["comparison"][
        "prior"
    ] == [10]
    for note in content["noticias"]:
        receipt = resolved_provenance(
            content, note, "summary", allowed=note["source_refs"]
        )
        assert receipt["state"] == "linked"
        assert receipt["comparison"]["prior"] == note["source_refs"]
    compiled = content["tarjetas"][-1]
    assert len(compiled["notas"]) == 3
    for position, scope in enumerate(compiled["notas_refs"]):
        receipt = resolved_provenance(
            content, compiled, "notas", position=position, allowed=scope["source_refs"]
        )
        assert receipt["state"] == "linked"
        assert (
            "comparison" not in receipt
        )  # The bullet copies a current title, not the comparative summary.
        assert receipt["source_refs"] == scope["source_refs"]


def test_known_comparison_mirror_compiles_without_union_rebinding(two_cut_content):
    from app.summaries.builder import build_tarjetas
    from app.summaries.evidence import compiled_provenance

    content = two_cut_content
    note = merge_comparison(content)
    note["title"] = None  # With no title the existing bullet formatter uses hecho.
    card = build_tarjetas([note], content=content)[0]
    text = card["hecho"]
    binding = compiled_provenance(content, card, text)
    assert binding["state"] == "unbacked"
    compiled = {"notas": [text, text], "provenance": {"notas": [binding, binding]}}
    assert (
        resolved_provenance(content, compiled, "notas", position=0, allowed=[0])[
            "state"
        ]
        == "linked"
    )
    assert (
        resolved_provenance(content, compiled, "notas", position=1, allowed=[1])[
            "state"
        ]
        == "unbacked"
    )
    assert (
        resolved_provenance(content, compiled, "notas", position=0, allowed=[0, 1])[
            "state"
        ]
        == "unbacked"
    )


def test_model_cannot_replace_frozen_context_or_backend_receipts(two_cut_content):
    content = two_cut_content
    frozen = copy.deepcopy({k: content[k] for k in ("evidence", "comparison")})
    apply_narrative(
        content,
        {
            "items": [
                {
                    "index": 0,
                    "summary": "Prosa válida.",
                    "provenance": {"summary": {"state": "linked"}},
                }
            ],
            "evidence": {},
            "comparison": {},
            "provenance": {"headline": {"state": "linked"}},
        },
    )
    assert {k: content[k] for k in frozen} == frozen
    assert content["noticias"][0]["summary"] == "Prosa válida."
    assert content["noticias"][0]["provenance"]["summary"]["state"] == "unbacked"
