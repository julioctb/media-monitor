"""GET /api/mentions: client-scoped mention feed with filters."""

from datetime import datetime
from typing import Literal, Sequence

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import ClientIdDep, SessionDep
from app.api.schemas import MentionPage, PersonRefOut
from app.models import Event, Mention, MentionPerson, Person, MentionSource, Sentiment, queries

router = APIRouter(tags=["mentions"])

# "none" is the explicit NULL-sentiment filter (analyzer failures leave
# sentiment NULL; those rows must stay visible and filterable).
SentimentFilter = Literal["positive", "negative", "neutral", "none"]


@router.get("/mentions", response_model=MentionPage)
def list_mentions(
    session: SessionDep,
    client_id: ClientIdDep,
    source: MentionSource | None = None,
    sentiment: SentimentFilter | None = None,
    keyword_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    q: str | None = None,
    classifier: str | None = None,
    label: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> MentionPage:
    """Mention feed, newest first.

    Filters: source, sentiment (or 'none' for unclassified), keyword,
    published-at window, `q` substring search over title/content, and a
    classification probe (classifier, optionally narrowed to label).
    """
    sentiment_value = None
    sentiment_null = False
    if sentiment == "none":
        sentiment_null = True
    elif sentiment is not None:
        sentiment_value = Sentiment(sentiment)

    common = {
        "source": source,
        "sentiment": sentiment_value,
        "sentiment_null": sentiment_null,
        "keyword_id": keyword_id,
        "since": since,
        "until": until,
        "q": q,
        "classifier": classifier,
        "label": label,
    }
    items = queries.list_mentions(session, client_id, limit=limit, offset=offset, **common)
    total = queries.count_mentions(session, client_id, **common)
    _attach_persons(session, items)
    _attach_event_titles(session, items)
    return MentionPage(items=items, total=total)


def _attach_persons(session: SessionDep, items: Sequence[Mention]) -> None:
    """One query for the page's person links; transient attr for pydantic.

    from_attributes picks ``persons`` up off the instance even though the
    ORM model has no such column — it is a plain instance attribute.
    """
    ids = [mention.id for mention in items]
    if not ids:
        return
    rows = session.execute(
        select(MentionPerson.mention_id, Person.id, Person.name)
        .join(Person, Person.id == MentionPerson.person_id)
        .where(MentionPerson.mention_id.in_(ids))
        .order_by(MentionPerson.id)
    ).all()
    by_mention: dict[int, list[PersonRefOut]] = {}
    for mention_id, person_id, name in rows:
        by_mention.setdefault(mention_id, []).append(PersonRefOut(id=person_id, name=name))
    for mention in items:
        mention.persons = by_mention.get(mention.id, [])


def _attach_event_titles(session: SessionDep, items: Sequence[Mention]) -> None:
    """One query for the page's canonical-event titles; transient attr.

    Mirrors _attach_persons: event_id rides on the column, the title is
    looked up in batch and set as a plain attribute for pydantic.
    """
    event_ids = {mention.event_id for mention in items if mention.event_id is not None}
    if not event_ids:
        for mention in items:
            mention.event_title = None
        return
    titles: dict[int, str] = dict(
        session.execute(select(Event.id, Event.title).where(Event.id.in_(event_ids))).all()
    )
    for mention in items:
        mention.event_title = titles.get(mention.event_id) if mention.event_id else None
