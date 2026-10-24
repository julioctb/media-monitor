"""Field-report Telegram bot: guided intake, never free-form parsing.

Design (odd/tasks/field-reports-telegram.md): the bot asks what happened,
where, when, plus optional detail context; answers travel verbatim in
``field_reports.intake`` and the row lands in ``review`` — the human queue
is the gate; the enrichment LLM arrives later and only suggests.

Identity is one-way anonymous: the operator sees a neutral bot; the admin
sees telegram id + name (auto-registered on first contact).

Run as its own compose service (long polling: no webhook, no public URL):

    docker compose up -d field-bot

The in-progress conversation lives in memory per chat: a restarted process
drops half answered intakes and the operator begins again with /start;
nothing is persisted until the operator confirms the summary.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
from sqlalchemy import select

from app.db import SessionLocal
from app.models import FieldOperator
from app.models.field import FieldReportStatus
from app.models import queries

logger = logging.getLogger("field.bot")

TELEGRAM_API = "https://api.telegram.org"
POLL_TIMEOUT_S = 50
HTTP_TIMEOUT_S = 60

#: (key, prompt) asked in order; keys land in intake verbatim.
STEPS: tuple[tuple[str, str], ...] = (
    ("what", "1/4 ¿Qué pasó? Titulalo en una línea."),
    ("detail", "2/4 El detalle: qué viste, cifras, personas."),
    ("where", "3/4 ¿Dónde? Lugar, colonia o edificio."),
    ("when", "4/4 ¿Cuándo? Fecha y hora aproximadas."),
)

WELCOME = (
    "Reporte de Campo: te guío en 4 preguntas y el reporte va a revisión "
    "antes de publicarse. /cancelar empieza de nuevo."
)

CONFIRM_PROMPT = "Confirmás el reporte? Respondé OK para enviarlo o NO para volver a empezar."

CONFIRM_WORDS = {"ok", "si", "sí", "dale", "confirmo"}
CANCEL_WORDS = {"no", "cancelar", "restart"}


@dataclass
class Session:
    """In-progress intake for one chat."""

    step: int = 0  # index into STEPS; len(STEPS) = awaiting confirmation
    answers: dict = field(default_factory=dict)
    operator_id: int | None = None

    @property
    def awaiting_confirm(self) -> bool:
        return self.step >= len(STEPS)


def _display_name(from_user: dict) -> str:
    for key in ("first_name", "username", "title"):
        value = from_user.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"user {from_user.get('id', '?')}"


class Bot:
    """Telegram long-polling loop plus the intake state machine.

    ``send`` and the Telegram call are overridable so the conversation
    logic tests without network; ``db_factory`` is the session maker.
    """

    def __init__(
        self,
        token: str,
        *,
        client: httpx.Client | None = None,
        db_factory: Callable[[], Any] | None = None,
        client_id: int | None = None,
    ) -> None:
        from app.config import settings

        self.token = token
        self.api_base = TELEGRAM_API
        self._client = client or httpx.Client(timeout=HTTP_TIMEOUT_S)
        self._owns_client = client is None
        self.db_factory = db_factory or SessionLocal
        self.client_id = client_id if client_id is not None else settings.default_client_id
        self.sessions: dict[int, Session] = {}
        self.offset: int = 0

    # -- telegram plumbing ---------------------------------------------------

    def _call(self, method: str, payload: dict | None = None) -> Any:
        response = self._client.post(
            f"{self.api_base}/bot{self.token}/{method}", json=payload or {}, timeout=HTTP_TIMEOUT_S
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            logger.warning("telegram %s failed: %s", method, body)
            return None
        return body.get("result")

    def send(self, chat_id: int, text: str) -> None:
        try:
            self._call("sendMessage", {"chat_id": chat_id, "text": text})
        except Exception:  # noqa: BLE001 - a failed reply must not kill the loop
            logger.exception("sendMessage to %s failed", chat_id)

    def poll(self) -> list[dict]:
        """Long poll; returns fresh updates and advances the offset."""
        updates = self._call(
            "getUpdates",
            {"offset": self.offset, "timeout": POLL_TIMEOUT_S},
        )
        if not updates:
            return []
        for update in updates:
            self.offset = max(self.offset, update["update_id"] + 1)
        return updates

    # -- conversation --------------------------------------------------------

    def handle_update(self, update: dict) -> None:
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = (message.get("text") or "").strip()
        from_user = message.get("from") or {}
        if not chat_id or not text:
            return
        try:
            self._handle(chat_id, text, from_user)
        except Exception:  # noqa: BLE001 - one bad update never kills the loop
            logger.exception("field bot failed handling chat %s", chat_id)

    def _handle(self, chat_id: int, text: str, from_user: dict) -> None:
        lowered = text.lower()
        is_reset = lowered in {"/start", "/cancelar"} or lowered in CANCEL_WORDS

        # Access gate: only operators with an ACTIVE alta get the intake.
        # Unknown senders auto-register as pending; waiting reply every time
        # (short, neutral) so the silence is never mistaken for a bug.
        operator, created = self._resolve_operator(from_user)
        if operator is None or not operator.active:
            self.sessions.pop(chat_id, None)
            self.send(
                chat_id,
                "Gracias. Tu acceso quedó en lista de espera; te avisaremos "
                "cuando esté activado." + (" (Registro nuevo.)" if created else ""),
            )
            return

        session = self.sessions.get(chat_id)
        if session is None or is_reset:
            self.sessions[chat_id] = Session(operator_id=operator.id)
            self.send(chat_id, WELCOME)
            self.send(chat_id, STEPS[0][1])
            return

        if session.awaiting_confirm:
            self._handle_confirm(chat_id, session, lowered)
            return

        key, _prompt = STEPS[session.step]
        session.answers[key] = text
        session.step += 1
        if session.awaiting_confirm:
            self.send(chat_id, self._summary(session))
            self.send(chat_id, CONFIRM_PROMPT)
        else:
            self.send(chat_id, STEPS[session.step][1])

    def _handle_confirm(self, chat_id: int, session: Session, lowered: str) -> None:
        if lowered in CONFIRM_WORDS:
            report_id = self._persist(chat_id, session, session.operator_id)
            self.sessions.pop(chat_id, None)
            self.send(chat_id, "Listo: el reporte quedó en revisión. Gracias.")
            self._enrich(report_id)  # best effort, after the ack
        elif lowered in CANCEL_WORDS:
            self.sessions[chat_id] = Session()
            self.send(chat_id, WELCOME)
            self.send(chat_id, STEPS[0][1])
        else:
            self.send(chat_id, CONFIRM_PROMPT)

    def _summary(self, session: Session) -> str:
        lines = [f"• {key.capitalize()}: {session.answers.get(key, '—')}" for key, _prompt in STEPS]
        return "Repaso del reporte:\n" + "\n".join(lines)

    def _resolve_operator(self, from_user: dict) -> tuple[FieldOperator | None, bool]:
        """Access-gate lookup. Unknown senders land as INACTIVE pending —
        the alta is an admin act (/campo), never a side effect of writing."""
        telegram_id = from_user.get("id")
        name = _display_name(from_user) if from_user else "operador"
        with self.db_factory() as db:
            if isinstance(telegram_id, int):
                existing = db.scalar(
                    select(FieldOperator).where(
                        FieldOperator.client_id == self.client_id,
                        FieldOperator.telegram_user_id == telegram_id,
                    )
                )
                if existing is not None:
                    return existing, False
            operator = FieldOperator(
                client_id=self.client_id,
                telegram_user_id=telegram_id if isinstance(telegram_id, int) else None,
                display_name=name,
                active=False,
            )
            db.add(operator)
            db.commit()
            return operator, True

    def _persist(self, chat_id: int, session: Session, operator_id: int | None) -> int | None:
        answers = session.answers
        detail = answers.get("detail", "")
        when = answers.get("when", "")
        content = f"{detail}\nCuándo: {when}".strip()
        with self.db_factory() as db:
            report = queries.create_field_report(
                db,
                client_id=self.client_id,
                operator_id=operator_id,
                status=FieldReportStatus.REVIEW,
                title=answers.get("what"),
                content=content or None,
                place=answers.get("where"),
                intake=dict(answers),
            )
            db.commit()
            logger.info("field report from chat %s -> review (#%s)", chat_id, report.id)
            return report.id

    def _enrich(self, report_id: int | None) -> None:
        """LLM suggestions for the queue; silence on any failure."""
        if report_id is None:
            return
        try:
            from app.field_enrich import enrich_report_by_id

            enrichment = enrich_report_by_id(self.db_factory, self.client_id, report_id)
            if enrichment:
                logger.info("field report %s enriched", report_id)
        except Exception:  # noqa: BLE001 - suggestions are best effort
            logger.exception("enrichment pass failed for report %s", report_id)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def run() -> None:
    """Compose entrypoint: long-poll forever; safe to restart any time."""
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required (env), exiting")

    bot = Bot(token)
    logger.info("field bot polling as %s...", token.split(":")[0])
    try:
        while True:
            try:
                for update in bot.poll():
                    bot.handle_update(update)
            except Exception:  # noqa: BLE001 - network hiccups recycle the loop
                logger.exception("poll cycle failed; backing off")
                time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        bot.close()


if __name__ == "__main__":
    run()
