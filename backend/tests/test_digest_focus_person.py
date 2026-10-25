"""Offline transport contract for the principal monitored person's context."""

import copy
import json
from datetime import datetime, timezone

import pytest

from app.models import Client, ClientSettings, MentionPerson, MentionSource, Person, queries
from app.settings_runtime import EffectiveSettings
from app.summaries import builder


PUBLISHED = datetime(2026, 10, 9, 18, tzinfo=timezone.utc)


def seed_person(session, *, name="Persona Alfa", role="Candidata", org="Organización Alfa"):
    client = Client(name=f"Cliente de {name}")
    session.add(client)
    session.flush()
    person = Person(
        client_id=client.id,
        name=name,
        name_key=name.lower(),
        role=role,
        org=org,
    )
    session.add(person)
    session.flush()
    return client, person


def prompt_json(prompt):
    return json.JSONDecoder().raw_decode(prompt.split("\n", 1)[1])[0]


def test_build_passes_focus_person_even_without_person_mentions(session):
    client, person = seed_person(session)
    session.add(ClientSettings(
        client_id=client.id, digest_focus_person_id=person.id
    ))
    session.flush()
    queries.insert_mention(
        session,
        client_id=client.id,
        source=MentionSource.news_rss,
        url="https://example.test/monitored-person-context",
        title="Se aplaza la consulta sin anunciar una nueva fecha",
        published_at=PUBLISHED,
    )
    captured = []

    def generate(prompt):
        captured.append(prompt_json(prompt))
        return json.dumps({"headline": "Narrativa sintética sin proveedor externo."})

    row = builder.build_daily_summary(
        session, client_id=client.id, day=PUBLISHED.date(), generate=generate
    )

    assert len(captured) == 1
    assert captured[0].get("focus_person") == {
        "name": "Persona Alfa", "role": "Candidata", "org": "Organización Alfa"
    }
    assert captured[0]["personas"] == []
    assert row.mode == "llm"
    assert "focus_person" not in row.content


@pytest.mark.parametrize(
    ("role", "org"),
    [("Rectora", "Universidad Alfa"), ("Gobernador", "Gobierno Alfa"),
     ("Candidato", None), (None, None)],
)
def test_focus_person_context_uses_registered_metadata(session, role, org):
    client, person = seed_person(session, role=role, org=org)
    effective = EffectiveSettings(client_id=client.id, digest_focus_person_id=person.id)

    assert builder._focus_person_context(session, effective) == {
        "name": person.name, "role": role, "org": org
    }


@pytest.mark.parametrize("focus_id", [None, 999_999])
def test_focus_person_context_missing_focus_is_omitted(session, focus_id):
    client, _ = seed_person(session)
    effective = EffectiveSettings(client_id=client.id, digest_focus_person_id=focus_id)

    assert builder._focus_person_context(session, effective) is None


def test_focus_person_context_rejects_foreign_client(session):
    owner, person = seed_person(session)
    other, _ = seed_person(session, name="Persona Beta")
    assert owner.id != other.id
    effective = EffectiveSettings(client_id=other.id, digest_focus_person_id=person.id)

    assert builder._focus_person_context(session, effective) is None


def test_projection_focus_person_is_allowlisted_without_mutating_facts():
    facts = {
        "noticias": [
            {
                "title": "Primera historia", "event_id": 81,
                "sources": [{
                    "source": "news_rss", "title": "Una publicación",
                    "url": "https://example.test/story", "mention_id": 92,
                }],
            },
            {"title": "Segunda historia", "event_id": 82},
        ],
        "personas": [{"person_id": 7, "name": "Persona Beta"}],
    }
    focus_person = {
        "name": "Persona Alfa", "role": None, "org": None,
        "id": 42, "aliases": ["Alias Alfa"], "client_id": 1,
    }
    before = copy.deepcopy((facts, focus_person))

    view = builder.digest_prompt_view(facts, focus_person=focus_person)

    assert view["focus_person"] == {"name": "Persona Alfa", "role": None, "org": None}
    assert [item["title"] for item in view["noticias"]] == [
        "Primera historia", "Segunda historia"
    ]
    assert view["noticias"][0]["sources"] == [
        {"source": "news_rss", "title": "Una publicación"}
    ]
    assert all("event_id" not in item for item in view["noticias"])
    assert view["personas"] == [{"name": "Persona Beta"}]
    assert (facts, focus_person) == before
    assert "focus_person" not in builder.digest_prompt_view(facts)
    assert builder.digest_prompt_view(facts) == builder.digest_prompt_view(
        facts, focus_person=None
    )
    assert builder.digest_prompt_view({}) == {
        "noticias": [], "redes": {}, "personas": []
    }


def test_prompt_identifies_focus_person_and_preserves_previous_context():
    facts = {"noticias": [{"title": "Historia actual", "repeat": True}]}
    previous = [{"title": "Historia anterior", "tone": {"negative": 1}}]
    focus_person = {"name": "Persona Alfa", "role": "Candidata", "org": None}

    prompt = builder._digest_prompt(
        PUBLISHED.date(), facts, previous, focus_person=focus_person
    )
    payload = prompt_json(prompt)

    assert payload["focus_person"] == focus_person
    assert payload["dia_previo"] == [{"title": "Historia anterior", "tono": "negativo"}]
    assert payload["noticias"][0]["repeat"] is True
    assert "persona principal bajo seguimiento" in prompt
    assert "no necesariamente al lector ni al protagonista de cada noticia" in prompt
    assert "sin inventar competencias u objetivos" in prompt
    assert "Si la relación no puede establecerse, indica esa limitación" in prompt
    legacy_prompt = builder._digest_prompt(PUBLISHED.date(), facts, previous)
    assert "focus_person" not in legacy_prompt
    assert legacy_prompt == builder._digest_prompt(
        PUBLISHED.date(), facts, previous, focus_person=None
    )
    assert prompt.split("\nLas notas con repeat=true", 1)[1] == (
        legacy_prompt.split("\nLas notas con repeat=true", 1)[1]
    )


@pytest.mark.parametrize("focus_kind", ["absent", "nonexistent", "foreign_client"])
def test_build_omits_unresolvable_focus_without_substitute(session, focus_kind):
    client, alternative = seed_person(session, name="Persona Beta")
    _, foreign = seed_person(session, name="Persona Ajena")
    focus_id = {"absent": None, "nonexistent": 999_999, "foreign_client": foreign.id}[
        focus_kind
    ]
    session.add(ClientSettings(client_id=client.id, digest_focus_person_id=focus_id))
    mention = queries.insert_mention(
        session,
        client_id=client.id,
        source=MentionSource.news_rss,
        url="https://example.test/no-substitution",
        title="Persona Beta informa sobre el calendario de consulta",
        published_at=PUBLISHED,
    )
    assert mention is not None
    session.add(MentionPerson(mention_id=mention.id, person_id=alternative.id))
    session.flush()
    captured = []

    def generate(prompt):
        captured.append(prompt)
        return json.dumps({"headline": "Informe general sintético."})

    row = builder.build_daily_summary(
        session, client_id=client.id, day=PUBLISHED.date(), generate=generate
    )

    assert len(captured) == 1
    payload = prompt_json(captured[0])
    assert payload["personas"]
    assert payload["personas"][0]["name"] == alternative.name
    assert "focus_person" not in payload
    assert "persona principal bajo seguimiento" not in captured[0]
    assert foreign.name not in captured[0]
    assert row.mode == "llm"
    assert "focus_person" not in row.content


@pytest.mark.parametrize("skip_reason", ["empty_window", "no_generator"])
def test_build_resolves_focus_only_inside_generation_gate(session, monkeypatch, skip_reason):
    client, person = seed_person(session)
    session.add(ClientSettings(client_id=client.id, digest_focus_person_id=person.id))
    if skip_reason == "no_generator":
        queries.insert_mention(
            session, client_id=client.id, source=MentionSource.news_rss,
            url="https://example.test/no-generator", title="Se anuncia la consulta",
            published_at=PUBLISHED,
        )
    session.flush()
    lookups = []
    prompts = []

    def resolve_focus(*args):
        lookups.append(args)
        return {"name": person.name, "role": person.role, "org": person.org}

    def generate(prompt):
        prompts.append(prompt)
        return json.dumps({"headline": "No se debe generar."})

    monkeypatch.setattr(builder, "_focus_person_context", resolve_focus)
    monkeypatch.setattr(builder, "summary_generator", lambda effective: None)
    row = builder.build_daily_summary(
        session, client_id=client.id, day=PUBLISHED.date(),
        generate=generate if skip_reason == "empty_window" else None,
    )

    assert lookups == []
    assert prompts == []
    assert row.mode == "heuristic"
    assert "focus_person" not in row.content
