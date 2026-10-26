"""Frozen publication inputs, exercised through offline facts and public builds."""

import copy
import json
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from app.models import Client, Event, Mention, MentionSource, make_url_hash
from app.summaries.builder import build_daily_summary, build_tarjetas, digest_prompt_view
from app.summaries.digest import build_digest_facts

DAY = date(2026, 10, 17)
NOON = datetime(2026, 10, 17, 18, tzinfo=UTC)


def client(session, name="Catalogue client"):
    row = Client(name=name)
    session.add(row)
    session.flush()
    return row


def publication(session, client_id, suffix, **fields):
    url = fields.pop("url", f"https://www.Medio.test/{suffix}")
    row = Mention(
        client_id=client_id,
        url=url,
        url_hash=make_url_hash(url),
        source=fields.pop("source", MentionSource.news_rss),
        published_at=fields.pop("published_at", NOON),
        title=fields.pop("title", f"Publicación institucional {suffix}"),
        **fields,
    )
    session.add(row)
    session.flush()
    return row


def facts_for(session, owner, **kwargs):
    return build_digest_facts(session, client_id=owner.id, day=DAY, tz="UTC", **kwargs)


def test_facts_freeze_exact_same_window_catalogue_and_story_membership(session):
    owner = client(session)
    event = Event(
        client_id=owner.id,
        title="Título global ajeno",
        title_tokens="global",
        first_seen_at=NOON,
        last_seen_at=NOON,
    )
    session.add(event)
    session.flush()
    loose = publication(session, owner.id, "loose", title="Nota suelta")
    article = publication(
        session,
        owner.id,
        "article",
        event_id=event.id,
        title="  Consulta aplazada · Ver más · Comentar ",
        author="Reportera A",
        summary="  " + "S" * 305 + "  ",
        content="  " + "E" * 305 + "  ",
        published_at=NOON,
    )
    showcase = publication(
        session,
        owner.id,
        "showcase",
        event_id=event.id,
        title="Esta es la PORTADA de @Diario: consulta y presupuesto",
        source=MentionSource.facebook_page,
    )
    cosmetic = publication(
        session,
        owner.id,
        "cosmetic",
        title="Actualizó su foto de perfil",
        source=MentionSource.facebook_page,
    )
    other = client(session, "Other client")
    publication(session, other.id, "foreign", title="Material de otro cliente")
    publication(session, owner.id, "old", published_at=NOON - timedelta(days=2))
    session.commit()
    session.expire_all()  # Actual SQLite naive-UTC roundtrip.

    facts = facts_for(session, owner)

    sources = facts["evidence"]["sources"]
    assert facts["evidence"]["version"] == 1
    assert [s["mention_id"] for s in sources] == [
        loose.id,
        article.id,
        showcase.id,
        cosmetic.id,
    ]
    assert [s["index"] for s in sources] == [0, 1, 2, 3]
    assert sources[1] == {
        "index": 1,
        "mention_id": article.id,
        "source": "news_rss",
        "url": article.url,
        "outlet": "medio.test",
        "author": "Reportera A",
        "title": "Consulta aplazada",
        "published_at": "2026-10-17T18:00:00+00:00",
        "summary": "S" * 300,
        "excerpt": "E" * 300,
    }
    assert sources[0]["summary"] is None
    assert sources[0]["excerpt"] is None
    assert facts["coverage"]["total"] == len(sources) == 4
    story = next(n for n in facts["noticias"] if n["event_id"] == event.id)
    assert story["source_refs"] == [1]  # Showcase is coverage, not membership.
    assert story["material_ref"] == 1
    assert [s["url"] for s in story["sources"]] == [article.url, showcase.url]
    assert next(n for n in facts["noticias"] if n["title"] == "Nota suelta")[
        "source_refs"
    ] == [0]


def test_injected_selected_rows_keep_empty_material_explicit_and_utc(session):
    owner = client(session)
    empty = publication(
        session,
        owner.id,
        "empty",
        title="   ",
        author=" ",
        summary=" ",
        content="",
        published_at=None,
    )
    aware = publication(
        session,
        owner.id,
        "aware",
        published_at=NOON.astimezone(timezone(timedelta(hours=-6))),
    )
    facts = facts_for(session, owner, mentions=[aware, empty])
    assert facts["evidence"]["sources"][0] == {
        "index": 0,
        "mention_id": empty.id,
        "source": "news_rss",
        "url": empty.url,
        "outlet": "medio.test",
        "author": None,
        "title": None,
        "published_at": None,
        "summary": None,
        "excerpt": None,
    }
    assert facts["evidence"]["sources"][1]["published_at"] == (
        "2026-10-17T18:00:00+00:00"
    )


def test_public_build_prompts_only_frozen_material_and_rejects_catalogue_injection(
    session,
):
    from app.summaries.builder import SYSTEM_PROMPT
    from app.summaries.digest import apply_narrative

    owner = client(session)
    article = publication(
        session,
        owner.id,
        "input",
        title="🎓 Consulta aplazada https://t.co/raw",
        summary="Síntesis derivada " + "S" * 310,
        content="Extracto capturado",
        author="Reportera A",
    )
    social = publication(
        session,
        owner.id,
        "social",
        source=MentionSource.facebook_page,
        title="Actualizó su foto de perfil",
        summary="Síntesis social",
        content="Contenido social capturado",
    )
    foreign = client(session, "Foreign")
    publication(session, foreign.id, "secret", title="Secreto ajeno")
    session.commit()
    captured = []

    def generate(prompt):
        captured.append(json.JSONDecoder().raw_decode(prompt.split("\n", 1)[1])[0])
        # The source may change after prompt assembly; that cannot rewrite
        # this cut's snapshot. This is not a real enrichment/regeneration.
        article.title = "Texto posterior no congelado"
        article.summary = "Resumen posterior no congelado"
        article.content = "Cuerpo posterior no congelado"
        return json.dumps(
            {
                "headline": "Prosa válida sin referencias.",
                "evidence": {"version": 1, "sources": [{"index": 999}]},
                "items": [
                    {
                        "index": 0,
                        "summary": "Reseña del modelo",
                        "source_refs": [999],
                        "material_ref": 999,
                    }
                ],
            }
        )

    row = build_daily_summary(session, client_id=owner.id, day=DAY, generate=generate)
    session.refresh(row)
    frozen = copy.deepcopy(row.content["evidence"])
    assert row.mode == "llm"
    assert row.content["schema"] == 2
    assert [s["mention_id"] for s in frozen["sources"]] == [article.id, social.id]
    assert frozen["sources"][0]["title"] == "🎓 Consulta aplazada https://t.co/raw"
    assert frozen["sources"][0]["summary"] == ("Síntesis derivada " + "S" * 310)[:300]
    assert frozen["sources"][0]["excerpt"] == "Extracto capturado"
    assert row.content["noticias"][0]["summary"] == "Reseña del modelo"
    assert row.content["noticias"][0]["source_refs"] == [0]
    assert row.content["noticias"][0]["material_ref"] == 0
    view = captured[0]
    assert view["noticias"][0]["title"] == "Consulta aplazada"
    assert view["noticias"][0]["summary"] == frozen["sources"][0]["summary"]
    assert view["noticias"][0]["source_refs"] == [0]
    assert view["noticias"][0]["material_ref"] == 0
    assert view["evidence"] == {
        "version": 1,
        "sources": [
            {
                key: ("Consulta aplazada" if key == "title" else value)
                for key, value in source.items()
                if key not in ("mention_id", "url")
            }
            if source["index"] == 0
            else {
                key: value
                for key, value in source.items()
                if key not in ("mention_id", "url")
            }
            for source in frozen["sources"]
        ],
    }
    assert view["redes"]["facebook_page"] == {"count": 1, "source_refs": [1]}
    assert "catálogo evidence" in SYSTEM_PROMPT
    assert "no confiable" in SYSTEM_PROMPT
    assert "instrucciones" in SYSTEM_PROMPT
    assert "derivado" in SYSTEM_PROMPT

    changed = copy.deepcopy(row.content)
    changed["noticias"][0].update(
        title="RUTA NO CONGELADA", summary="RUTA NO CONGELADA"
    )
    changed["noticias"][0]["sources"][0]["title"] = "RUTA NO CONGELADA"
    changed["redes"]["facebook_page"].update(
        note="RUTA NO CONGELADA",
        mentions=[{"title": "RUTA NO CONGELADA"}],
    )
    changed["personas"] = [
        {
            "person_id": 99,
            "name": "Persona registrada",
            "fact": "RUTA NO CONGELADA",
            "mention_count": 1,
        }
    ]
    reprojection = digest_prompt_view(changed)
    assert reprojection["evidence"] == view["evidence"]
    assert reprojection["noticias"] == view["noticias"]
    text = json.dumps(reprojection, ensure_ascii=False)
    for forbidden in (
        "RUTA NO CONGELADA",
        "mention_id",
        "person_id",
        '"url"',
        "Secreto ajeno",
    ):
        assert forbidden not in text
    assert reprojection["personas"] == [
        {"name": "Persona registrada", "mention_count": 1}
    ]
    assert (
        apply_narrative(
            changed,
            {
                "evidence": {"version": 99},
                "items": [
                    {"index": 0, "summary": "Otra prosa válida", "source_refs": [999]}
                ],
            },
        )
        == []
    )
    assert changed["evidence"] == frozen
    assert changed["noticias"][0]["source_refs"] == [0]


def test_public_build_preserves_source_zero_and_bullet_refs_after_reorder(session):
    owner = client(session)
    articles = [publication(session, owner.id, str(i)) for i in range(11)]
    session.commit()

    row = build_daily_summary(
        session,
        client_id=owner.id,
        day=DAY,
        generate=lambda prompt: json.dumps(
            {
                "headline": "Resumen de prueba.",
                "seleccion": [
                    {"index": 10, "categoria": "decision", "razon": "Atender."}
                ],
            }
        ),
    )
    session.refresh(row)
    content = row.content
    assert [s["mention_id"] for s in content["evidence"]["sources"]] == [
        article.id for article in articles
    ]
    assert [n["source_refs"] for n in content["noticias"]] == [
        [10],
        *[[i] for i in range(10)],
    ]
    assert [t["source_refs"] for t in content["tarjetas"][:-1]] == [
        [10],
        *[[i] for i in range(7)],
    ]
    assert [t["material_ref"] for t in content["tarjetas"][:-1]] == [10, *range(7)]
    assert len(content["tarjetas"]) == 9
    compiled = content["tarjetas"][-1]
    assert compiled["titulo"] == "También hoy"
    assert compiled["source_refs"] == [7, 8, 9]
    assert compiled["notas_refs"] == [
        {"source_refs": [i], "material_ref": i} for i in (7, 8, 9)
    ]
    assert "material_ref" not in compiled  # No invented single representative.
    assert content["indicators_version"] == 1
    assert all(t["media_diversity"] == {"identified_outlet_count": 1} for t in content["tarjetas"][:-1])
    assert compiled["notas_indicators"] == [
        {"media_diversity": {"identified_outlet_count": 1}, "veracity": "not_evaluated"}
        for _ in (7, 8, 9)
    ]
    assert "media_diversity" not in compiled
    assert compiled["notas"] == [
        f"Publicación institucional {i} (news_rss)" for i in (7, 8, 9)
    ]
    assert content["coverage"]["total"] == len(content["noticias"]) == 11
    for noticia in content["noticias"]:
        ref = noticia["material_ref"]
        assert noticia["sources"] == [
            {
                "source": "news_rss",
                "url": articles[ref].url,
                "title": articles[ref].title,
            }
        ]
    projected = digest_prompt_view(content)
    assert [n["material_ref"] for n in projected["noticias"]] == [10, *range(10)]
    assert [s["index"] for s in projected["evidence"]["sources"]] == list(range(11))


@pytest.mark.parametrize(
    "invalid",
    [
        "missing_version",
        "null",
        "future",
        "boolean",
        "string",
        "bad_index",
        "duplicate_id",
        "unbounded_summary",
        "unbounded_excerpt",
    ],
)
def test_invalid_catalogue_never_unlocks_frozen_projection(session, invalid):
    owner = client(session)
    publication(session, owner.id, "valid")
    facts = facts_for(session, owner)
    evidence = facts["evidence"]
    if invalid == "missing_version":
        del evidence["version"]
    elif invalid == "null":
        facts["evidence"] = None
    elif invalid in ("future", "boolean", "string"):
        evidence["version"] = {"future": 2, "boolean": True, "string": "1"}[invalid]
    elif invalid == "bad_index":
        evidence["sources"][0]["index"] = True
    elif invalid == "duplicate_id":
        evidence["sources"].append({**evidence["sources"][0], "index": 1})
    else:
        evidence["sources"][0][invalid.removeprefix("unbounded_")] = "Z" * 301
    facts["noticias"][0].update(title="No usar esta ruta", summary="No usar esta ruta")
    view = digest_prompt_view(facts)
    assert "evidence" not in view
    assert view["noticias"][0]["sources"] == []
    for key in ("title", "summary", "source_refs", "material_ref"):
        assert key not in view["noticias"][0]
    assert "No usar esta ruta" not in json.dumps(view)


@pytest.mark.parametrize("ref", [None, False, "0", -1, 999])
def test_invalid_material_ref_never_substitutes_mutable_story_text(session, ref):
    owner = client(session)
    publication(session, owner.id, "valid", summary="Síntesis original")
    facts = facts_for(session, owner)
    facts["noticias"][0].update(
        material_ref=ref, title="No sustituir", summary="No sustituir"
    )
    view = digest_prompt_view(facts)
    assert view["noticias"][0]["source_refs"] == [0]
    assert "material_ref" not in view["noticias"][0]
    assert "No sustituir" not in json.dumps(view)


def test_legacy_view_and_cards_remain_unchanged_without_evidence():
    from app.summaries.builder import build_tarjetas

    facts = {
        "noticias": [
            {
                "title": "🎓 Nota histórica",
                "summary": "Reseña previa",
                "sources": [
                    {
                        "source": "news_rss",
                        "title": "Título fuente",
                        "url": "https://legacy.test/",
                    }
                ],
            }
        ],
        "redes": {"x": {"count": 1, "note": "Prosa histórica"}},
        "personas": [{"person_id": 9, "name": "Persona", "fact": "Hecho histórico"}],
    }
    before = copy.deepcopy(facts)
    assert digest_prompt_view(facts) == {
        "noticias": [
            {
                "title": "Nota histórica",
                "summary": "Reseña previa",
                "sources": [{"source": "news_rss", "title": "Título fuente"}],
            }
        ],
        "redes": facts["redes"],
        "personas": [{"name": "Persona", "fact": "Hecho histórico"}],
    }
    assert build_tarjetas(facts["noticias"]) == [
        {
            "titulo": "Nota histórica",
            "hecho": "Reseña previa",
            "por_que": None,
            "fuentes": ["news_rss"],
            "tono": None,
            "repeat": False,
            "angulo_nuevo": None,
        }
    ]
    assert facts == before


def test_injected_facts_do_not_requery_publications(session):
    from sqlalchemy import event

    owner = client(session)
    article = publication(session, owner.id, "selected")
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(session.bind, "before_cursor_execute", capture)
    try:
        facts = facts_for(session, owner, mentions=[article])
    finally:
        event.remove(session.bind, "before_cursor_execute", capture)
    assert facts["evidence"]["sources"][0]["mention_id"] == article.id
    assert not any("FROM mentions" in statement for statement in statements)


@pytest.mark.parametrize(
    "refs, linked",
    [
        ([0], True),
        (None, False),
        ([], False),
        (["0"], False),
        ([False], False),
        ([1], False),
        ([999], False),
        ([0, 999], False),
    ],
)
def test_output_references_bind_own_story_without_discarding_prose(
    session, refs, linked
):
    from app.summaries.digest import apply_narrative

    owner = client(session)
    publication(session, owner.id, "own")
    publication(session, owner.id, "foreign-story")
    facts = facts_for(session, owner)
    facts["schema"] = 2
    payload = {
        "headline": "  Lectura no verificada.  ",
        # Model-return order is not the story index.
        "items": [
            {"index": 1, "summary": "Otra historia."},
            {"index": 0, "summary": "  Texto retenido.  "},
        ],
        "references": {"headline": [0], "items.0.summary": refs},
        "provenance": {"headline": {"state": "linked", "source_refs": [1]}},
    }
    assert apply_narrative(facts, payload) == []
    assert facts["noticias"][0]["summary"] == "Texto retenido."
    binding = facts["noticias"][0]["provenance"]["summary"]
    assert binding["text"] == "Texto retenido."
    assert binding["state"] == ("linked" if linked else "unbacked")
    assert binding["source_refs"] == ([0] if linked else [])
    assert binding["origin"] == "model_output"
    assert len(binding["catalogue_fingerprint"]) == 64
    assert facts["provenance"]["headline"]["text"] == "Lectura no verificada."
    assert facts["provenance"]["headline"]["source_refs"] == [0]
    # Catalogue membership alone cannot back the second generated sentence.
    assert facts["noticias"][1]["provenance"]["summary"]["state"] == "unbacked"


@pytest.mark.parametrize("wrong_scope", [False, True])
def test_reference_scopes_and_raw_positions_across_prose_fields(session, wrong_scope):
    from app.models import MentionPerson, Person
    from app.summaries.digest import apply_brief, apply_narrative

    owner = client(session)
    publication(session, owner.id, "news")
    one = publication(
        session, owner.id, "one", source=MentionSource.x_twitter, author="@one"
    )
    publication(session, owner.id, "two", source=MentionSource.x_twitter, author="@two")
    publication(session, owner.id, "fb", source=MentionSource.facebook_page)
    person = Person(
        client_id=owner.id, name="Persona registrada", name_key="persona registrada"
    )
    session.add(person)
    session.flush()
    session.add(MentionPerson(mention_id=one.id, person_id=person.id))
    session.commit()
    facts = facts_for(session, owner)
    facts.update(schema=2, brief={}, tarjetas=build_tarjetas(facts["noticias"]))
    payload = {
        "items": [
            {"index": False, "summary": "No aceptar."},
            {"index": "0", "summary": "No coercionar."},
            {"index": 0, "summary": 99},
            {
                "index": 1,
                "summary": "Síntesis.",
                "why_it_matters": "Importa.",
                "confidence_note": "Atribución.",
                "angulo_nuevo": "Giro.",
            },
        ],
        "agenda": [
            {"when": 12, "title": "No aceptar"},
            {
                "when": " mañana ",
                "title": " Plazo ",
                "status": " Abierto ",
                "source": " Fuente ",
            },
        ],
        "redes": {
            "x": {
                "note": " Hallazgo ",
                "cuentas": [
                    {"cuenta": 22},
                    {"cuenta": "@one", "nota": " Nota de cuenta "},
                ],
            }
        },
        "personas": [{"fact": " Hecho personal "}],
        "seleccion": [{"index": 1, "categoria": "decision", "razon": " Motivo "}],
        "references": {
            **{
                f"items.1.{key}": [0 if wrong_scope else 1]
                for key in (
                    "summary",
                    "why_it_matters",
                    "confidence_note",
                    "angulo_nuevo",
                )
            },
            **{f"agenda.1.{key}": [0] for key in ("when", "title", "status", "source")},
            "redes.x.note": [3 if wrong_scope else 1],
            "redes.x.cuentas.1.cuenta": [2 if wrong_scope else 1],
            "redes.x.cuentas.1.nota": [2 if wrong_scope else 1],
            "personas.0.fact": [0 if wrong_scope else 1],
            "seleccion.1.razon": [0 if wrong_scope else 1],
        },
    }
    assert apply_narrative(facts, payload) == []
    apply_brief(facts, payload)
    expected = "unbacked" if wrong_scope else "linked"
    assert "No aceptar." not in json.dumps(facts)
    for key in ("summary", "why_it_matters", "confidence_note", "angulo_nuevo"):
        assert facts["noticias"][1]["provenance"][key]["state"] == expected
    for key in ("when", "title", "status", "source"):
        assert facts["agenda"][0]["provenance"][key]["source_refs"] == [0]
    network = facts["redes"]["x"]
    assert network["provenance"]["note"]["state"] == expected
    assert network["cuentas"][0]["provenance"]["nota"]["state"] == expected
    assert network["cuentas"][0]["provenance"]["cuenta"]["state"] == expected
    assert facts["personas"][0]["fact"] == "Hecho personal"
    assert facts["personas"][0]["provenance"]["fact"]["state"] == expected
    assert facts["brief"]["decisiones"][0]["provenance"]["razon"]["state"] == expected


@pytest.mark.parametrize(
    "change", ["text", "material", "legacy", "future", "invalid", "claimed_hash"]
)
def test_binding_resolution_fails_safe_after_mutation(session, change):
    from app.summaries.digest import apply_narrative
    from app.summaries import evidence

    owner = client(session)
    publication(session, owner.id, "bound", summary="Material original")
    facts = facts_for(session, owner)
    facts["schema"] = 2
    apply_narrative(
        facts,
        {
            "items": [{"index": 0, "summary": "Prosa"}],
            "references": {"items.0.summary": [0]},
        },
    )
    target = facts["noticias"][0]
    assert (
        evidence.resolved_provenance(facts, target, "summary", allowed=[0])["state"]
        == "linked"
    )
    if change == "text":
        target["summary"] += " alterada"
    elif change == "material":
        facts["evidence"]["sources"][0]["excerpt"] = "Otro cuerpo"
    elif change == "legacy":
        del facts["evidence"]
    elif change == "future":
        facts["evidence"]["version"] = 2
    elif change == "invalid":
        facts["evidence"]["sources"][0]["index"] = False
    else:
        target["provenance"]["summary"]["catalogue_fingerprint"] = "modelo inventa hash"
    binding = evidence.resolved_provenance(facts, target, "summary", allowed=[0])
    assert binding["state"] == "unbacked"
    assert binding["source_refs"] == []
    assert binding["text"] == target["summary"]


def test_public_cards_and_compiled_bullets_keep_object_bound_provenance(session):
    from app.summaries.builder import build_tarjetas
    from app.summaries.evidence import resolved_provenance

    owner = client(session)
    for i in range(11):
        publication(session, owner.id, f"p{i}", summary=f"Resumen {i}")
    session.commit()
    row = build_daily_summary(
        session,
        client_id=owner.id,
        day=DAY,
        generate=lambda prompt: json.dumps(
            {
                "headline": "Síntesis",
                "items": [
                    {"index": 10, "summary": "Resumen 10"}
                ],  # Equal to source, still uncited.
                "seleccion": [{"index": 10, "categoria": "decision", "razon": "Razón"}],
                "references": {"headline": [0], "seleccion.10.razon": [10]},
            }
        ),
    )
    content = row.content
    first = content["tarjetas"][0]
    assert first["source_refs"] == [10]
    assert first["provenance"]["hecho"]["state"] == "unbacked"
    assert first["provenance"]["titulo"]["source_refs"] == [10]
    pick = content["brief"]["decisiones"][0]
    assert pick["index"] == 0
    assert pick["provenance"]["razon"]["source_refs"] == [10]
    compiled = content["tarjetas"][-1]
    assert compiled["source_refs"] == [7, 8, 9]
    for pos, ref in enumerate((7, 8, 9)):
        binding = compiled["provenance"]["notas"][pos]
        assert binding["text"] == compiled["notas"][pos]
        assert binding["source_refs"] == [ref]  # Never the compiled union.
        assert binding["state"] == "linked"
    changed = copy.deepcopy(content["noticias"])
    changed[0]["summary"] = "Cambio arbitrario"
    cards = build_tarjetas(changed, content=content)
    assert cards[0]["provenance"]["hecho"]["state"] == "unbacked"
    assert (
        resolved_provenance(content, content, "headline", text=row.narrative)["state"]
        == "linked"
    )


def test_compiled_label_cannot_inherit_support_for_changed_source_names(session):
    from app.summaries.builder import build_tarjetas, compile_tail_cards

    owner = client(session)
    for i in range(10):
        publication(session, owner.id, f"compile{i}")
    facts = facts_for(session, owner)
    facts["tarjetas"] = build_tarjetas(facts["noticias"], content=facts)
    facts["tarjetas"][-1]["fuentes"] = ["Fuente inventada"]
    assert compile_tail_cards(facts)
    compiled = facts["tarjetas"][-1]
    assert compiled["notas"][-1].endswith("(Fuente inventada)")
    assert compiled["provenance"]["notas"][-1]["state"] == "unbacked"
    assert compiled["provenance"]["notas"][-1]["source_refs"] == []


def test_resolution_rejects_unknown_origin_and_derivation_requires_all_parents(session):
    from app.summaries.digest import apply_narrative
    from app.summaries.evidence import derive_provenance, resolved_provenance

    owner = client(session)
    publication(session, owner.id, "parents")
    facts = facts_for(session, owner)
    facts["schema"] = 2
    apply_narrative(
        facts,
        {
            "items": [{"index": 0, "summary": "Hecho", "why_it_matters": "Lectura"}],
            "references": {"items.0.summary": [0], "items.0.why_it_matters": [0]},
        },
    )
    target = facts["noticias"][0]
    parents = [(target, "summary"), (target, "why_it_matters")]
    assert derive_provenance(facts, "Hecho: Lectura", parents, [0])["state"] == "linked"
    target["provenance"]["why_it_matters"]["origin"] = "inventado_por_el_modelo"
    assert (
        resolved_provenance(facts, target, "why_it_matters", allowed=[0])["state"]
        == "unbacked"
    )
    assert (
        derive_provenance(facts, "Hecho: Lectura", parents, [0])["state"] == "unbacked"
    )


def test_prompt_documents_exact_paths_and_person_scopes_without_exposing_bindings(
    session,
):
    from app.models import MentionPerson, Person
    from app.summaries.builder import SYSTEM_PROMPT

    owner = client(session)
    one = publication(session, owner.id, "person-scope")
    person = Person(client_id=owner.id, name="Sujeto", name_key="sujeto")
    session.add(person)
    session.flush()
    session.add(MentionPerson(mention_id=one.id, person_id=person.id))
    session.commit()
    facts = facts_for(session, owner)
    view = digest_prompt_view(facts)
    assert view["personas"][0]["source_refs"] == [0]
    assert "provenance" not in json.dumps(view)
    assert "catalogue_fingerprint" not in json.dumps(view)
    for path in (
        "items.<index>.summary",
        "seleccion.<index>.razon",
        "agenda.<posición>.title",
        "redes.<canal>.cuentas.<posición>.nota",
        "personas.<posición>.fact",
    ):
        assert path in SYSTEM_PROMPT


@pytest.mark.parametrize(
    "invalid", [None, {"version": 2}, {"version": 1, "sources": []}]
)
def test_unknown_catalogue_cannot_link_retained_prose(session, invalid):
    from app.summaries.digest import apply_narrative

    owner = client(session)
    publication(session, owner.id, "unknown")
    facts = facts_for(session, owner)
    facts.update(schema=2, evidence=invalid)
    assert (
        apply_narrative(
            facts,
            {
                "headline": "Conservar",
                "items": [{"index": 0, "summary": "Conservar"}],
                "references": {"headline": [0], "items.0.summary": [0]},
            },
        )
        == []
    )
    assert facts["noticias"][0]["summary"] == "Conservar"
    assert facts["provenance"]["headline"]["state"] == "unbacked"
    assert facts["noticias"][0]["provenance"]["summary"]["state"] == "unbacked"
