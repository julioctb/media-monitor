"""Field bot: the guided intake state machine, no network.

The conversation must land a review-status report whose intake keeps the
verbatim answers; identity auto-registers on first contact.
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

    def send(self, chat_id: int, text: str) -> None:
        self.replies.append(text)


def _update(text: str, chat: int = CHAT) -> dict:
    return {"update_id": 1, "message": {"chat": {"id": chat}, "text": text, "from": dict(FROM)}}


def test_full_intake_lands_review_with_verbatim_answers(db):
    bot = FakeBot(db)

    bot.handle_update(_update("/start"))
    assert "1/4" in bot.replies[-1]
    bot.handle_update(_update("Bache gigante"))
    assert "2/4" in bot.replies[-1]
    bot.handle_update(_update("Hundimiento fuerte"))
    assert "3/4" in bot.replies[-1]
    bot.handle_update(_update("Puebla centro"))
    assert "4/4" in bot.replies[-1]
    bot.handle_update(_update("Hoy a las 10 de la maana"))
    # summary + confirmation prompt
    assert "Repaso" in bot.replies[-2]
    assert "OK" in bot.replies[-1]

    bot.handle_update(_update("ok"))

    report = db.scalar(select(FieldReport))
    assert report is not None
    assert report.status == "review"
    assert report.title == "Bache gigante"
    assert "Hundimiento fuerte" in (report.content or "")
    assert report.place == "Puebla centro"
    assert report.intake["when"] == "Hoy a las 10 de la maana"
    assert report.mention_id is None  # publication is the queue's job

    operator = db.scalar(select(FieldOperator))
    assert operator is not None
    assert operator.telegram_user_id == 42
    assert operator.display_name == "Julio"
    assert report.operator_id == operator.id


def test_cancel_restarts_conversation(db):
    bot = FakeBot(db)
    bot.handle_update(_update("/start"))
    bot.handle_update(_update("Bache"))
    bot.handle_update(_update("cancelar"))
    assert "1/4" in bot.replies[-1]
    # the old answer is gone: the next reply is step 2 for the fresh intake
    bot.handle_update(_update("Otra cosa"))
    assert "2/4" in bot.replies[-1]


def test_confirm_rejects_unknown_and_reprompts(db):
    bot = FakeBot(db)
    for answer in ("/start", "T", "D", "L", "W"):
        bot.handle_update(_update(answer))
    prompts = bot.replies.count(
        "Confirmás el reporte? Respondé OK para enviarlo o NO para volver a empezar."
    )
    bot.handle_update(_update("quizas"))
    assert bot.replies.count(
        "Confirmás el reporte? Respondé OK para enviarlo o NO para volver a empezar."
    ) == prompts + 1
    assert db.scalar(select(FieldReport)) is None  # nothing persisted yet


def test_no_empty_reports_even_without_text(db):
    bot = FakeBot(db)
    bot.handle_update({"update_id": 2, "message": {"chat": {"id": CHAT}}})
    assert bot.replies == []  # silence, no crash


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
