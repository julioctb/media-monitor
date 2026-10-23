"""Agenda auto-detection from digest content (feature agenda-detect).

The digest's ``content.agenda`` entries (``when``+``title`` required) are
promoted to real ``agenda_items`` rows after every cut, so the /agenda page
fills itself from the editorial digest. Rules:

- Idempotent: an existing item with the same normalized title is skipped,
  never duplicated (regens and multi-cut days converge to one row).
- Dates are best-effort Spanish parsing («27 oct.», «15 noviembre 2026»);
  unparsable whens keep the raw text in ``date_label`` and stay undated
  («Sin fecha completa», editable from the UI).
- Kind heuristic: inscription/deadline wording in title or status means
  ``deadline``; anything else is an ``activity``.

Deliberately NOT here: matching against mention events, human edits
propagating back, deletion of items that leave the digest. The sync only
adds what is missing.
"""

import logging
import re
import unicodedata
from datetime import date

from sqlalchemy.orm import Session

from app.models import AgendaItem, queries

log = logging.getLogger(__name__)

_MONTHS_ES = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}

_DEADLINE_WORDS = (
    "inscripc",
    "cierre",
    "plazo",
    "vence",
    "vencimiento",
    "fecha límite",
    "limite",
    "until",
)

_MONTH_RE = re.compile(r"\b(\d{1,2})\s*(?:de\s*)?([a-záéíóú]+)(?:\s+de\s*)?(\d{4})?", re.I)
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def normalize_title(title: str) -> str:
    """Case/accent/punctuation-insensitive key for dedup matching."""

    lowered = unicodedata.normalize("NFKD", title.strip().lower())
    without_marks = "".join(c for c in lowered if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


def _month_from(token: str) -> int | None:
    token = token[:3].lower()
    token = unicodedata.normalize("NFKD", token)
    token = "".join(c for c in token if not unicodedata.combining(c))
    return _MONTHS_ES.get(token)


def parse_spanish_date(text: str, year: int) -> date | None:
    """Best-effort date from a digest ``when`` string; None when unclear.

    Accepts «27 oct.», «15 noviembre», «2 de diciembre de 2027»,
    ISO «2026-11-02» and prefixes like «Hasta el 15 nov.» — the first
    day+month pair wins. Without an explicit year the digest's year is
    assumed (the mockup's rule).
    """

    if not text:
        return None
    iso = _ISO_RE.search(text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    match = _MONTH_RE.search(text)
    if not match:
        return None
    day = int(match.group(1))
    month = _month_from(match.group(2))
    if month is None or not 1 <= day <= 31:
        return None
    resolved_year = int(match.group(3)) if match.group(3) else year
    try:
        return date(resolved_year, month, day)
    except ValueError:
        return None


def detect_kind(title: str | None, status: str | None) -> str:
    """``deadline`` on inscription wording, else ``activity``."""

    haystack = " ".join(part for part in (title, status) if part).lower()
    normalized = unicodedata.normalize("NFKD", haystack)
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    if any(word in normalized for word in _DEADLINE_WORDS):
        return "deadline"
    return "activity"


def sync_agenda_from_digest(
    session: Session, client_id: int, content: dict, *, year: int
) -> int:
    """Promote ``content['agenda']`` entries into agenda_items; return count.

    Idempotent by normalized title: existing items (any origin) suppress
    their detected twin, so repeated cuts and regens never pile up.
    """
    entries = content.get("agenda")
    if not isinstance(entries, list):
        return 0

    existing = queries.list_agenda_items(session, client_id)
    known = {normalize_title(item.title) for item in existing}

    created = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        when = str(entry.get("when") or "").strip()
        if not title or not when:
            continue
        key = normalize_title(title)
        if not key or key in known:
            continue
        status = str(entry.get("status") or "").strip() or None
        source = str(entry.get("source") or "").strip() or None
        session.add(
            AgendaItem(
                client_id=client_id,
                title=title[:240],
                kind=detect_kind(title, status),
                event_date=parse_spanish_date(when, year),
                date_label=when[:64],
                source=source[:200] if source else None,
                notes=status[:500] if status else None,
            )
        )
        known.add(key)
        created += 1

    if created:
        session.commit()
        log.info("agenda detect: %s new item(s) from digest", created)
    return created
