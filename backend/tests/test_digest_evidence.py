"""Frozen publication inputs, exercised through offline facts and public builds."""

import copy
import json
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from app.models import Client, Event, Mention, MentionSource, make_url_hash
from app.summaries.builder import build_daily_summary, digest_prompt_view
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
