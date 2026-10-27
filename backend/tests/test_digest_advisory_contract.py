"""Offline advisory transport contracts, not model/editorial quality tests."""

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Client, Event, MentionSource, queries
from app.summaries import build_daily_summary
from app.summaries.digest import render_plain_text
from app.summaries.digest_schema import narrative_response_schema
from app.summaries.evidence import resolved_provenance


CURRENT = datetime(2026, 10, 14, 18, tzinfo=timezone.utc)
FIELDS = ("accion_sugerida", "condicion")
TEXTS = {
    "razon": "El aplazamiento mantiene abierta la negociación.",
    "accion_sugerida": "Confirmar el alcance de la consulta ágil <aviso> https://fuente.test/á.",
    "condicion": "Contar primero con el aviso original de la comisión.",
}


def seed(session, *, prior=False, count=1):
    client = Client(name="Advisory synthetic")
    session.add(client)
    session.flush()
    events = []
    for i in range(count):
        event = Event(
            client_id=client.id,
            title=f"Consulta institucional {i}",
            title_tokens=f"consulta {i}",
            first_seen_at=CURRENT - timedelta(days=5),
            last_seen_at=CURRENT,
        )
        session.add(event)
        session.flush()
        events.append(event)
    for published in [CURRENT - timedelta(days=5), CURRENT] if prior else [CURRENT]:
        for i, event in enumerate(events):
            mention = queries.insert_mention(
                session,
                client_id=client.id,
                source=MentionSource.news_rss,
                url=f"https://advisory.test/{published.date()}/{i}",
                title=f"Consulta institucional {i} del {published.date()}",
                published_at=published,
            )
            assert mention is not None
            mention.event_id = event.id
            mention.content = (
                f"Se reporta el aplazamiento de la consulta {i}, sin nueva fecha."
            )
            mention.summary = mention.content
        session.commit()
        if published != CURRENT:
            build_daily_summary(
                session,
                client_id=client.id,
                day=published.date(),
                generate=lambda prompt: json.dumps(
                    {"headline": "Corte previo sintético."}
                ),
            )
    return client


def payload(**overrides):
    value = {
        "headline": "El aplazamiento mantiene la negociación abierta.",
        "seleccion": [{"index": 0, "categoria": "decision", **TEXTS}],
        "references": {f"seleccion.0.{field}": [0] for field in TEXTS},
    }
    value.update(overrides)
    return value


def build(session, client, value):
    return build_daily_summary(
        session,
        client_id=client.id,
        day=CURRENT.date(),
        generate=lambda prompt: json.dumps(value),
    )


def test_public_build_accepts_independent_attention_with_own_zero_receipts(session):
    client = seed(session)
    row = build(session, client, payload())
    assert row.content["comparison"]["available"] is False
    assert row.content["comparison"]["evidence"] is None
    pick = row.content["brief"]["decisiones"][0]
    schema = narrative_response_schema()["$defs"]["SeleccionEntry"]
    for field, text in TEXTS.items():
        assert pick.get(field) == text
        assert pick["provenance"][field]["text"] == text
        assert resolved_provenance(row.content, pick, field, allowed=[0])[
            "source_refs"
        ] == [0]
    for field in FIELDS:
        assert schema["properties"][field]["anyOf"] == [
            {"type": "string"},
            {"type": "null"},
        ]
        assert field not in schema["required"]
        assert all(
            field not in story
            for story in row.content["noticias"] + row.content["tarjetas"]
        )


@pytest.mark.parametrize("field", FIELDS)
def test_attention_comparison_uses_own_current_and_original_prior_zero(session, field):
    client = seed(session, prior=True)
    value = payload(
        comparison_references={f"seleccion.0.{field}": {"current": [0], "prior": [0]}}
    )
    row = build(session, client, value)
    pick = row.content["brief"]["decisiones"][0]
    binding = pick["provenance"][field]
    assert binding["state"] == "unbacked"
    assert binding["comparison"]["current"] == [0]
    assert binding["comparison"]["prior"] == [0]
    assert (
        resolved_provenance(row.content, pick, field, allowed=[0])["state"] == "linked"
    )
    other = FIELDS[1] if field == FIELDS[0] else FIELDS[0]
    assert "comparison" not in pick["provenance"][other]
    assert resolved_provenance(row.content, pick, other, allowed=[0])[
        "source_refs"
    ] == [0]


def test_plain_attention_has_separate_labels_receipts_and_used_only_sources(session):
    client = seed(session, prior=True)
    row = build(
        session,
        client,
        payload(
            references={"seleccion.0.accion_sugerida": [0]},
            comparison_references={
                "seleccion.0.condicion": {"current": [0], "prior": [0]}
            },
        ),
    )
    plain = render_plain_text(row.content, row.narrative)
    assert f"{TEXTS['razon']} [No respaldada]" in plain
    assert (
        f"Acción sugerida: {TEXTS['accion_sugerida']} [Fuentes vinculadas: #0]" in plain
    )
    assert (
        f"Condición: {TEXTS['condicion']} [Fuentes vinculadas (ambos cortes): current:#0, prior:#0]"
        in plain
    )
    assert "https://advisory.test/2026-10-09/0" in plain
    assert "https://advisory.test/2026-10-14/0" in plain
    changed = copy.deepcopy(row.content)
    changed["brief"]["decisiones"][0]["condicion"] += " Texto cambiado."
    stale = render_plain_text(changed, row.narrative)
    assert "https://advisory.test/2026-10-09/0" not in stale
    assert f"{TEXTS['condicion']} Texto cambiado. [No respaldada]" in stale


@pytest.mark.parametrize("prior", [False, True])
def test_guarded_whole_pick_recovery_keeps_original_optional_prose(session, prior):
    client = seed(session, prior=prior)
    value = payload()
    if prior:
        value["comparison_references"] = {
            f"seleccion.0.{field}": {"current": [0], "prior": [0]} for field in TEXTS
        }
    first = build(session, client, value)
    original = copy.deepcopy(first.content["brief"]["decisiones"])

    def failed(prompt):
        raise RuntimeError("Offline synthetic failure")

    recovered = build_daily_summary(
        session,
        client_id=client.id,
        day=CURRENT.date(),
        generate=failed,
    )
    assert recovered.mode == "llm"
    assert recovered.content["brief"]["decisiones"] == original


@pytest.mark.parametrize("role", ["Rectora", "Gobernante", "Candidata", None])
def test_advisory_instructions_reach_both_offline_attempts_with_registered_profile(
    session, monkeypatch, role
):
    import httpx
    from app.models import ClientSettings, Person
    from app.settings_runtime import EffectiveSettings
    from app.summaries import builder

    client = seed(session)
    if role:
        person = Person(
            client_id=client.id,
            name="Persona sintética",
            name_key="persona sintética",
            role=role,
            org=None,
        )
        session.add(person)
        session.flush()
        session.add(
            ClientSettings(client_id=client.id, digest_focus_person_id=person.id)
        )
        session.commit()
    requests = []

    def post(url, **kwargs):
        requests.append(copy.deepcopy(kwargs["json"]))
        if len(requests) == 1:
            return httpx.Response(400, request=httpx.Request("POST", url))
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": json.dumps(payload())}}]},
        )

    monkeypatch.setattr(builder.httpx, "post", post)
    monkeypatch.setattr(builder.time, "sleep", lambda seconds: None)
    generator = builder.summary_generator(
        EffectiveSettings(
            client_id=client.id,
            ai_provider="openai",
            ai_api_key="synthetic-not-a-secret",
            ai_base_url="https://offline.invalid",
        )
    )
    row = build_daily_summary(
        session, client_id=client.id, day=CURRENT.date(), generate=generator
    )
    assert row.mode == "llm"
    assert len(requests) == 2
    assert requests[0]["messages"] == requests[1]["messages"]
    assert "response_format" in requests[0] and "response_format" not in requests[1]
    system, user = [message["content"] for message in requests[0]["messages"]]
    view = json.JSONDecoder().raw_decode(user.split("\n", 1)[1])[0]
    assert view.get("focus_person") == (
        {"name": "Persona sintética", "role": role, "org": None} if role else None
    )
    for instruction in (
        "asesor político",
        "relevancia concreta",
        "gobernabilidad",
        "coordinación",
        "negociación",
        "costos reputacionales",
        "atribución y la negación",
        "motivos o escenarios inferidos como interpretación",
        "sin propaganda",
        "no es necesariamente lector, protagonista, afectado ni responsable",
        "Sin focus_person",
        "no atribuyas facultades de gobierno a una candidatura",
        "accion_sugerida",
        "condicion",
        "prerrequisito o limitación",
        "no son autorización ni plazos inferidos",
        "seleccion.<index>.accion_sugerida",
        "seleccion.<index>.condicion",
        "mínimo tres decisiones cuando existan al menos tres candidatas sustantivas",
        "headline admite hasta 3",
    ):
        assert instruction in system
    assert "Eres editor" not in system and "Español periodístico" not in system
    assert "igual que las positivas y neutras" not in system


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", [None, "", " \n ", "absent"])
def test_optional_attention_omission_does_not_add_null_keys_or_stale_advice(
    session, field, value
):
    client = seed(session)
    build(session, client, payload())
    fresh = payload()
    if value == "absent":
        fresh["seleccion"][0].pop(field)
    else:
        fresh["seleccion"][0][field] = value
    row = build(session, client, fresh)
    pick = row.content["brief"]["decisiones"][0]
    assert field not in pick and field not in pick["provenance"]
    other = FIELDS[1] if field == FIELDS[0] else FIELDS[0]
    assert pick[other] == TEXTS[other]
    assert (
        "Acción sugerida:" if field == FIELDS[0] else "Condición:"
    ) not in row.content["plain_text"]


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("bad", [True, 0, [], {}])
def test_malformed_optional_prose_skips_only_that_entry(session, field, bad):
    client = seed(session)
    entries = [
        {"index": 0, "categoria": "riesgo", **TEXTS, field: bad},
        {
            "index": 0,
            "categoria": "decision",
            "razon": "Hermana válida",
            "condicion": "Con acta",
        },
    ]
    row = build(session, client, payload(seleccion=entries))
    assert row.content["brief"]["riesgos"] == []
    assert row.content["brief"]["decisiones"][0]["condicion"] == "Con acta"


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("bad", [[True], ["0"], [1], [-1], None, "0"])
def test_bad_current_attention_refs_retain_unbacked_prose_without_reason_borrowing(
    session, field, bad
):
    client = seed(session, count=2)
    references = {f"seleccion.0.razon": [0], f"seleccion.0.{field}": bad}
    row = build(session, client, payload(references=references))
    pick = row.content["brief"]["decisiones"][0]
    assert pick[field] == TEXTS[field]
    assert (
        resolved_provenance(row.content, pick, field, allowed=[0])["state"]
        == "unbacked"
    )
    assert (
        resolved_provenance(row.content, pick, "razon", allowed=[0])["state"]
        == "linked"
    )
    assert f"{TEXTS[field]} [No respaldada]" in row.content["plain_text"]


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("namespace", ["current", "prior"])
@pytest.mark.parametrize("bad", [[True], ["0"], [1], [], None])
def test_explicit_bad_comparison_attention_never_downgrades_to_current_only(
    session, field, namespace, bad
):
    client = seed(session, prior=True, count=2)
    refs = {"current": [0], "prior": [0], namespace: bad}
    row = build(
        session, client, payload(comparison_references={f"seleccion.0.{field}": refs})
    )
    pick = row.content["brief"]["decisiones"][0]
    receipt = resolved_provenance(row.content, pick, field, allowed=[0])
    assert pick[field] == TEXTS[field]
    assert receipt["state"] == "unbacked" and receipt["source_refs"] == []
    assert receipt["comparison"]["current"] == receipt["comparison"]["prior"] == []


@pytest.mark.parametrize("change", ["current", "prior", "legacy"])
def test_recovery_guards_and_genuine_legacy_picks_remain_unchanged(session, change):
    from sqlalchemy import select
    from app.models import Mention

    client = seed(session, prior=change == "prior")
    first = build(session, client, payload())
    if change == "legacy":
        content = copy.deepcopy(first.content)
        content.pop("comparison")
        for pick in content["brief"]["decisiones"]:
            for field in FIELDS:
                pick.pop(field)
                pick["provenance"].pop(field)
        first.content = content
        expected = copy.deepcopy(content["brief"]["decisiones"])
    elif change == "current":
        mention = session.scalars(
            select(Mention).where(Mention.client_id == client.id)
        ).first()
        mention.content = "Material actual cambiado."
    else:
        previous = queries.get_daily_summary(
            session, client.id, (CURRENT - timedelta(days=5)).date()
        )
        content = copy.deepcopy(previous.content)
        content["evidence"]["sources"][0]["excerpt"] = "Material previo cambiado."
        previous.content = content
    session.commit()

    def failed(prompt):
        raise RuntimeError("Offline synthetic failure")

    row = build_daily_summary(
        session, client_id=client.id, day=CURRENT.date(), generate=failed
    )
    if change == "legacy":
        assert row.mode == "llm" and row.content["brief"]["decisiones"] == expected
        assert "comparison" not in row.content
    else:
        assert row.mode == "heuristic" and row.content["brief"]["decisiones"] == []


@pytest.mark.parametrize(
    "selection",
    [None, [], "invalid", [{"index": 0, "categoria": "decision", "condicion": False}]],
)
def test_unassessed_or_explicit_empty_selection_never_invents_attention(
    session, selection
):
    client = seed(session)
    row = build(
        session,
        client,
        {"headline": "Informe sin sugerencias.", "seleccion": selection},
    )
    assert all(
        row.content["brief"][bucket] == []
        for bucket in ("decisiones", "riesgos", "ruido", "a_favor")
    )
    assert (
        "Acción sugerida:" not in row.content["plain_text"]
        and "Condición:" not in row.content["plain_text"]
    )


def test_accepted_tail_attention_survives_in_place_remapping_and_compilation(session):
    client = seed(session, count=11, prior=True)
    value = payload(
        seleccion=[{"index": 10, "categoria": "riesgo", **TEXTS}],
        references={f"seleccion.10.{field}": [10] for field in TEXTS},
        comparison_references={
            "seleccion.10.condicion": {"current": [10], "prior": [10]}
        },
    )
    row = build(session, client, value)
    pick = row.content["brief"]["riesgos"][0]
    assert pick["index"] == 0
    story = row.content["noticias"][pick["index"]]
    assert story["source_refs"] == [10]
    assert row.content["tarjetas"][pick["index"]]["source_refs"] == [10]
    for field, text in TEXTS.items():
        assert pick[field] == text
        assert resolved_provenance(row.content, pick, field, allowed=[10])[
            "source_refs"
        ] == [10]
    assert pick["provenance"]["condicion"]["comparison"]["prior"] == [10]
    assert any("notas" in card for card in row.content["tarjetas"])


def test_fresh_api_generation_restore_and_rejected_requests_preserve_optional_pick_and_source_tables(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from app.api import summaries as routes
    from app.db import get_db
    from app.main import create_app
    from app.models import Base, DailySummary, DailySummaryRevision

    engine = create_engine(f"sqlite:///{tmp_path}/advisory-api.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def tables():
        with engine.connect() as connection:
            return {
                table.name: [
                    tuple(row)
                    for row in connection.execute(
                        select(table).order_by(*table.primary_key.columns)
                    )
                ]
                for table in Base.metadata.sorted_tables
            }

    with factory() as session:
        client = seed(session, prior=True)
        client_id = client.id
    app = create_app()

    def fresh_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = fresh_db
    value = payload(
        comparison_references={"seleccion.0.condicion": {"current": [0], "prior": [0]}}
    )
    monkeypatch.setattr(
        routes,
        "build_daily_summary",
        lambda session, **kwargs: build_daily_summary(
            session, **kwargs, generate=lambda prompt: json.dumps(value)
        ),
    )
    try:
        with TestClient(app) as api:
            before = tables()
            generated = api.post(
                f"/api/clients/{client_id}/summaries/generate",
                json={"date": CURRENT.date().isoformat()},
            )
            assert generated.status_code == 200
            read = api.get(f"/api/clients/{client_id}/summaries/{CURRENT.date()}")
            assert read.status_code == 200 and read.json() == generated.json()
            content = read.json()["content"]
            expected = copy.deepcopy(content["brief"]["decisiones"])
            for field in FIELDS:
                assert expected[0][field] == TEXTS[field]
                assert (
                    resolved_provenance(content, expected[0], field, allowed=[0])[
                        "state"
                    ]
                    == "linked"
                )
            with factory() as session:
                session.add(
                    DailySummaryRevision(
                        client_id=client_id,
                        summary_date=CURRENT.date(),
                        seq=9,
                        narrative="Titular restaurado sin fuentes.",
                        mode="llm",
                    )
                )
                session.commit()
            restore_url = f"/api/clients/{client_id}/summary-revisions/restore"
            assert (
                api.post(
                    restore_url, json={"day": CURRENT.date().isoformat(), "seq": 9}
                ).status_code
                == 200
            )
            restored = api.get(
                f"/api/clients/{client_id}/summaries/{CURRENT.date()}"
            ).json()
            assert restored["content"]["brief"]["decisiones"] == expected
            assert restored["content"]["provenance"]["headline"]["state"] == "unbacked"
            assert "prior:#0" in restored["content"]["plain_text"]
            after = tables()
            mutable = {DailySummary.__tablename__, DailySummaryRevision.__tablename__}
            assert {
                key: rows for key, rows in before.items() if key not in mutable
            } == {key: rows for key, rows in after.items() if key not in mutable}
            for url, body, status in [
                (restore_url, {"day": CURRENT.date().isoformat(), "seq": 999}, 404),
                (restore_url, {"day": "invalid", "seq": 9}, 422),
                (
                    "/api/clients/999999/summaries/generate",
                    {"date": CURRENT.date().isoformat()},
                    404,
                ),
            ]:
                assert api.post(url, json=body).status_code == status
                assert tables() == after
    finally:
        engine.dispose()
