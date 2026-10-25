"""Field-report Telegram bot: closed access by phone allowlist.

Access model (odd/tasks/field-reports-telegram.md, cierre 23/oct):

- Operators are PRE-loaded by an admin (name + phone) in /campo/operadores.
- A first-time sender is asked to share the contact; the phone is matched
  against the allowlist. Match => the account binds to that operator
  (telegram id + accepted stamp) and the intake opens.
- No match => "número no registrado"; NOTHING is persisted — unknowns do
  not exist for the system until an admin loads their phone.
- An invite deep-link (t.me/bot?start=TOKEN) only pre-selectes the
  operator; the binding proof is always the phone. The token is a
  reference, never the credential.

Run as its own compose service (long polling; no webhook, no public URL):

    docker compose up -d field-bot

The in-progress conversation lives in memory per chat: a restarted process
drops half-answered intakes; reports only persist on confirmation.
"""

import logging
import os
import re
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
from sqlalchemy import select

from app.db import SessionLocal
from app.models import FieldOperator
from app.models import queries
from app.models.field import FieldReportStatus

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
    "Reporte de Campo: te guío en 4 preguntas y el reporte se publica tras "
    "revisión. /cancelar empieza de nuevo."
)

CONFIRM_PROMPT = "¿Confirmas el reporte? Responde OK para enviarlo o NO para volver a empezar."

CONFIRM_WORDS = {"ok", "si", "sí", "dale", "confirmo"}
CANCEL_WORDS = {"no", "cancelar", "restart"}

CONTACT_KEYBOARD = {
    "keyboard": [[{"text": "Compartir mi teléfono", "request_contact": True}]],
    "resize_keyboard": True,
    "one_time_keyboard": True,
}

ASK_CONTACT = "Para validarte necesito tu teléfono: toca el botón para compartirlo."
NOT_REGISTERED = "Ese número no está registrado. Contacta al administrador del proyecto."
ALREADY_BOUND = "Ese teléfono ya está vinculado a otro acceso. Avísale al administrador."
DEACTIVATED = "Tu acceso está desactivado. Contactá al administrador."

_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str | None) -> str:
    """Digits only, keyed by the last 10 (MX): +52/lada prefixes vanish.

    The allowlist stores whatever the admin typed; the contact share adds
    country codes. Comparing the 10-digit tail makes both shapes equal.
    """
    if not raw:
        return ""
    digits = _DIGITS.sub("", raw)
    return digits[-10:] if len(digits) > 10 else digits


def _display_name(from_user: dict) -> str:
    for key in ("first_name", "username", "title"):
        value = from_user.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"user {from_user.get('id', '?')}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Session:
    """In-progress contact validation or intake, per chat."""

    phase: str = "contact"  # 'contact' | 'intake'
    step: int = 0  # index into STEPS; len(STEPS) = awaiting confirmation
    answers: dict = field(default_factory=dict)
    operator_id: int | None = None
    invite_token: str | None = None

    @property
    def awaiting_confirm(self) -> bool:
        return self.phase == "intake" and self.step >= len(STEPS)


class Bot:
    """Telegram long-polling loop plus the gated intake state machine.

    ``send``/``_call`` are overridable so conversation tests run without
    network; ``db_factory`` is the session maker.
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
            f"{self.api_base}/bot{self.token}/{method}",
            json=payload or {},
            timeout=HTTP_TIMEOUT_S,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            logger.warning("telegram %s failed: %s", method, body)
            return None
        return body.get("result")

    def send(self, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
        payload: dict = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            self._call("sendMessage", payload)
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

    # -- dispatch --------------------------------------------------------------

    def handle_update(self, update: dict) -> None:
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = (message.get("text") or "").strip()
        from_user = message.get("from") or {}
        contact = message.get("contact") or {}
        if not chat_id or (not text and not contact):
            return
        try:
            self._handle(chat_id, text, from_user, contact)
        except Exception:  # noqa: BLE001 - one bad update never kills the loop
            logger.exception("field bot failed handling chat %s", chat_id)

    def _handle(self, chat_id: int, text: str, from_user: dict, contact: dict) -> None:
        lowered = text.lower()
        is_reset = lowered in {"/start", "/cancelar"} or lowered in CANCEL_WORDS

        operator = self._operator_for_telegram(from_user.get("id"))
        if operator is not None and not operator.active:
            self.sessions.pop(chat_id, None)
            self.send(chat_id, DEACTIVATED)
            return

        session = self.sessions.get(chat_id)

        # Access phase: bound accounts flow straight to the intake; everyone
        # else must pass the phone gate first.
        if operator is None or session is None or session.phase == "contact" or is_reset:
            self._handle_access(chat_id, session, text, from_user, contact, operator)
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

    # -- access: allowlist + phone match ---------------------------------------

    def _handle_access(
        self,
        chat_id: int,
        session: Session | None,
        text: str,
        from_user: dict,
        contact: dict,
        bound_operator: FieldOperator | None,
    ) -> None:
        invite_token = None
        if text.startswith("/start") and " " in text:
            invite_token = text.split(" ", 1)[1].strip() or None

        phone = normalize_phone((contact or {}).get("phone_number"))
        if phone:
            self._finalize_access(chat_id, session, phone, from_user, invite_token)
            return

        if bound_operator is not None:
            # Bound but landed here via /reset: straight back to intake.
            cancelled = session is not None and text.lower() in CANCEL_WORDS
            self._restart_intake(chat_id, bound_operator.id, cancelled=cancelled)
            return

        fresh = session is None or session.phase != "contact"
        if fresh:
            self.sessions[chat_id] = Session(phase="contact", invite_token=invite_token)
            self.send(
                chat_id,
                "Bienvenido a Reporte de Campo. El acceso es para operadores "
                "registrados: valida tu teléfono para continuar.",
            )
        self.send(chat_id, ASK_CONTACT, CONTACT_KEYBOARD)

    def _finalize_access(
        self,
        chat_id: int,
        session: Session | None,
        phone: str,
        from_user: dict,
        invite_token: str | None,
    ) -> None:
        operator, conflict = self._match_allowlist(phone, from_user.get("id"))
        if operator is None:
            self.sessions.pop(chat_id, None)
            self.send(chat_id, ALREADY_BOUND if conflict else NOT_REGISTERED)
            return

        if not operator.active:
            # Deactivated alta: recognized but gated; the admin re-enable
            # plus a new contact share opens the intake. Nothing binds.
            self.send(chat_id, DEACTIVATED)
            return

        with self.db_factory() as db:
            attached = db.get(FieldOperator, operator.id)
            attached.telegram_user_id = from_user.get("id")
            attached.active = True
            attached.accepted_at = utcnow()
            db.commit()

        self.sessions[chat_id] = Session(
            phase="intake", operator_id=operator.id, invite_token=invite_token
        )
        logger.info(
            "operator %s bound to telegram %s (chat %s)",
            operator.id,
            from_user.get("id"),
            chat_id,
        )
        self.send(chat_id, f"Listo, {operator.display_name}: acceso validado.")
        self.send(chat_id, WELCOME)
        self.send(chat_id, STEPS[0][1])

    def _operator_for_telegram(self, telegram_user_id) -> FieldOperator | None:
        if not isinstance(telegram_user_id, int):
            return None
        with self.db_factory() as db:
            operator = db.scalar(
                select(FieldOperator).where(
                    FieldOperator.client_id == self.client_id,
                    FieldOperator.telegram_user_id == telegram_user_id,
                )
            )
            if operator is None:
                return None
            db.expunge(operator)
            return operator

    def _match_allowlist(self, phone: str, telegram_user_id) -> tuple[FieldOperator | None, bool]:
        """Phone against the allowlist. Returns (operator, conflict).

        The decision is ALWAYS the phone; the invite token plays no role
        here. Operators already bound to a DIFFERENT account conflict; the
        same account rebinds silently.
        """
        wanted = normalize_phone(phone)
        with self.db_factory() as db:
            rows = db.query(FieldOperator).filter_by(client_id=self.client_id).all()
            candidates = [
                o for o in rows if normalize_phone(o.phone) and normalize_phone(o.phone) == wanted
            ]
            for operator in candidates:
                if operator.telegram_user_id is None or (
                    isinstance(telegram_user_id, int)
                    and operator.telegram_user_id == telegram_user_id
                ):
                    return operator, False
            return (None, True) if candidates else (None, False)

    # -- intake lifecycle --------------------------------------------------------

    def _handle_confirm(self, chat_id: int, session: Session, lowered: str) -> None:
        if lowered in CONFIRM_WORDS:
            report_id = self._persist(chat_id, session, session.operator_id)
            self.sessions.pop(chat_id, None)
            self.send(chat_id, "Listo: el reporte quedó en revisión. Gracias.")
            self._enrich(report_id)  # best effort, after the ack
        elif lowered in CANCEL_WORDS:
            self._restart_intake(chat_id, session.operator_id, cancelled=True)
        else:
            self.send(chat_id, CONFIRM_PROMPT)

    def _restart_intake(
        self, chat_id: int, operator_id: int | None = None, *, cancelled: bool = False
    ) -> None:
        self.sessions[chat_id] = Session(phase="intake", operator_id=operator_id)
        if cancelled:
            # Visible ack: otherwise the restart is indistinguishable from
            # the first run and reads as "ignored".
            self.send(chat_id, "Ok, cancelado. Empezamos de nuevo.")
        else:
            self.send(chat_id, WELCOME)
        self.send(chat_id, STEPS[0][1])

    def _summary(self, session: Session) -> str:
        lines = [
            f"• {key.capitalize()}: {session.answers.get(key, '—')}" for key, _prompt in STEPS
        ]
        return "Repaso del reporte:\n" + "\n".join(lines)

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
