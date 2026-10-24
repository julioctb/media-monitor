"""Field bot: phone-gated intake, no network.

The allowlist is the door: a shared contact whose phone matches a
pre-loaded operator binds the account (id + accepted stamp) and opens the
intake; unknown numbers never persist anything.
"""

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.field_bot import Bot
from app.models import Base, FieldOperator
from app.models.field import FieldReport

CHAT = 777
FROM = {"id": 42, "first_name": "Julio"}


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()
    engine.dispose()


class FakeBot(Bot):
    """Records replies instead of touching Telegram."""

    def __init__(self, db) -> None:
        super().__init__("test:token", db_factory=lambda: db, client_id=1)
        self.replies: list[str] = []
        self.markups: list[dict | None] = []

    def send(self, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
        self.replies.append(text)
        self.markups.append(reply_markup)


def _text_update(text: str, chat: int = CHAT) -> dict:
    return {
        "update_id": 1,
        "message": {"chat": {"id": chat}, "text": text, "from": dict(FROM)},
    }


def _contact_update(phone: str, chat: int = CHAT) -> dict:
    return {
        "update_id": 2,
        "message": {
            "chat": {"id": chat},
            "contact": {"phone_number": phone},
            "from": dict(FROM),
        },
    }


def _seed_operator(db, phone: str = "52 222 123-4567", **overrides) -> FieldOperator:
    operator = FieldOperator(client_id=1, phone=phone, display_name="Julio", **overrides)
    db.add(operator)
    db.commit()
    return operator


def _run_intake(bot: FakeBot) -> None:
    bot.handle_update(_contact_update("+52 222 123 4567"))  # messy on purpose
    assert "1/4" in bot.replies[-1]
    for answer in ("Bache gigante", "Hundimiento fuerte", "Puebla centro", "Hoy 10am"):
        bot.handle_update(_text_update(answer))
    bot.handle_update(_text_update("ok"))


def test_phone_match_tolerates_country_code_forms(db):
    """Stored 10-digit vs Telegram's +52-prefixed contact: same line."""
    _seed_operator(db, phone="222 123 4567")
    bot = FakeBot(db)

    bot.handle_update(_text_update("/start"))
    bot.handle_update(_contact_update("+52 222 123 4567"))

    assert "1/4" in bot.replies[-1]


def test_phone_match_binds_activates_and_intakes(db):
    operator = _seed_operator(db)
    bot = FakeBot(db)

    bot.handle_update(_text_update("/start"))
    assert "teléfono" in bot.replies[-1]
    assert bot.markups[-1] is not None  # the contact-share keyboard came along

    _run_intake(bot)

    db.expire_all()
    bound = db.get(FieldOperator, operator.id)
    assert bound.telegram_user_id == 42
    assert bound.active is True
    assert bound.accepted_at is not None

    report = db.scalar(select(FieldReport))
    assert report is not None
    assert report.status == "review"
    assert report.operator_id == operator.id
    assert report.intake["what"] == "Bache gigante"


def test_unknown_phone_never_persists(db):
    _seed_operator(db, phone="111222333")  # someone else's line
    bot = FakeBot(db)

    bot.handle_update(_text_update("/start"))
    bot.handle_update(_contact_update("5550001111"))

    assert "no está registrado" in bot.replies[-1]
    assert db.scalar(select(FieldReport)) is None
    assert len(db.scalars(select(FieldOperator)).all()) == 1  # no phantom rows


def test_conflicting_binding_reports_and_gates(db):
    _seed_operator(db, phone="5550001111", telegram_user_id=999)
    bot = FakeBot(db)

    bot.handle_update(_text_update("/start"))
    bot.handle_update(_contact_update("5550001111"))  # right number, wrong account

    assert "ya está vinculado" in bot.replies[-1]
    assert db.scalar(select(FieldReport)) is None


def test_deactivated_operator_is_gated(db):
    operator = _seed_operator(db, active=False)
    bot = FakeBot(db)

    bot.handle_update(_text_update("/start"))
    bot.handle_update(_contact_update("+52 222 123 4567"))
    assert "desactivado" in bot.replies[-1]

    # admin reactivates: the next contact exchange flows
    operator = db.get(FieldOperator, operator.id)
    operator.active = True
    db.commit()
    bot.handle_update(_contact_update("+52 222 123 4567"))
    assert "1/4" in bot.replies[-1]


def test_enrichment_writes_suggestions_and_flags_duplicates(db, monkeypatch):
    import json as _json

    from app import field_enrich
    from app.models import Mention
    from app.models.field import FieldReportStatus

    # one live mention whose normalized title matches the suggestion
    db.add(
        Mention(
            client_id=1,
            source=_enum("news_rss"),
            url="https://a/x",
            url_hash="h1",
            title="Bache gigante en la 11 sur",
        )
    )
    db.commit()

    class FakeEnricher:
        def complete(self, system, user, json_mode=False):
            return _json.dumps(
                {
                    "suggested_title": "Bache Gigante En La 11 Sur",
                    "summary": "Hundimiento fuerte.",
                    "tone": "negative",
                }
            )

    monkeypatch.setattr(field_enrich, "build_enricher", lambda session, client_id: FakeEnricher())

    report = queries_create(db)
    result = field_enrich.enrich_report(db, report)
    assert result is not None
    assert result["duplicate"] is True  # normalized-title match
    assert result["tone"] == "negative"

    db.expire_all()
    # the by-id wrapper owns its session; same engine, fresh view
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    persisted = field_enrich.enrich_report_by_id(lambda: factory(), 1, report.id)
    assert persisted is not None
    db.expire_all()
    stored = db.scalar(select(FieldReport))
    assert stored.enrichment["suggested_title"] == "Bache Gigante En La 11 Sur"


def queries_create(db):
    from app.models import queries
    from app.models.field import FieldReportStatus

    return queries.create_field_report(
        db,
        client_id=1,
        status=FieldReportStatus.REVIEW,
        title="Bache",
        content="Hundimiento",
    )


def _enum(name: str):
    from app.models import MentionSource

    return MentionSource(name)


def test_cancel_mid_intake_acks_and_restarts(db):
    _seed_operator(db, phone="222 123 4567", telegram_user_id=42)
    bot = FakeBot(db)
    bot.handle_update(_text_update("hola"))  # bound: intake opens
    bot.handle_update(_text_update("respuesta 1"))

    bot.handle_update(_text_update("cancelar"))

    assert bot.replies[-2] == "Ok, cancelado. Empezamos de nuevo."
    assert "1/4" in bot.replies[-1]
