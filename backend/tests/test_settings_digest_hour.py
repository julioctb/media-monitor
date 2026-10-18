"""digest_hour schedule setting: default 21, validated 0..23, resolver-clamped."""

import pytest

from app.models.client import Client
from app.models.queries import upsert_settings
from app.settings_runtime import resolve_effective_settings


def _client(session) -> int:
    client = Client(name="t")
    session.add(client)
    session.commit()
    return client.id


def test_digest_hour_defaults_to_21(session) -> None:
    client_id = _client(session)
    eff = resolve_effective_settings(session, client_id=client_id)
    assert eff.digest_hour == 21


def test_digest_hour_roundtrip(session) -> None:
    client_id = _client(session)
    row = upsert_settings(session, client_id, {"digest_hour": 6})
    assert row.digest_hour == 6
    eff = resolve_effective_settings(session, client_id=client_id)
    assert eff.digest_hour == 6


def test_digest_hour_validation(session) -> None:
    client_id = _client(session)
    with pytest.raises(ValueError):
        upsert_settings(session, client_id, {"digest_hour": 24})
    with pytest.raises(ValueError):
        upsert_settings(session, client_id, {"digest_hour": "7am"})
    with pytest.raises(ValueError):
        upsert_settings(session, client_id, {"digest_hour": -1})
