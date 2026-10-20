"""digest_hours runtime/api surface: parsing, upsert validation, legacy sync."""

from app.models.client import Client
from app.models.queries import upsert_settings
from app.settings_runtime import parse_digest_hours, resolve_effective_settings


def _client(session) -> int:
    client = Client(name="t")
    session.add(client)
    session.commit()
    return client.id


def test_parse_digest_hours_variants() -> None:
    assert parse_digest_hours("8,21") == [8, 21]
    assert parse_digest_hours("21,8,8") == [8, 21]  # dedupe + sort
    assert parse_digest_hours(" 7 , 25 , x , 22 ") == [7, 22]  # junk dropped
    assert parse_digest_hours("") == []
    assert parse_digest_hours("abc") == []
    assert parse_digest_hours(None) == []
    assert parse_digest_hours([3, 1, 1, 30]) == [1, 3]  # list input
    assert parse_digest_hours("24") == []
    assert parse_digest_hours("0,23") == [0, 23]  # bounds inclusive


def test_resolve_digest_hours_from_row(session) -> None:
    client_id = _client(session)
    row = upsert_settings(session, client_id, {"digest_hours": [21, 8, 8]})
    assert row.digest_hours == "8,21"  # stored as sorted CSV
    eff = resolve_effective_settings(session, client_id=client_id)
    assert eff.digest_hours == [8, 21]
    assert eff.digest_hour == 8  # compat: first cut


def test_resolve_digest_hours_falls_back_to_legacy_column(session) -> None:
    client_id = _client(session)
    row = upsert_settings(session, client_id, {"digest_hour": 6})
    row.digest_hours = "nonsense"
    session.commit()
    eff = resolve_effective_settings(session, client_id=client_id)
    assert eff.digest_hours == [6]


def test_upsert_digest_hours_validation(session) -> None:
    client_id = _client(session)
    for bad in ([], list(range(9)), [24], [-1], ["8"], 8):
        try:
            upsert_settings(session, client_id, {"digest_hours": bad})
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


def test_digest_hour_write_syncs_cut_list(session) -> None:
    """Legacy single-hour writes keep the cut list coherent (and vice versa)."""
    client_id = _client(session)
    row = upsert_settings(session, client_id, {"digest_hour": 9})
    assert row.digest_hours == "9"
    row = upsert_settings(session, client_id, {"digest_hours": [20, 10]})
    assert row.digest_hour == 10
