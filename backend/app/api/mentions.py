"""GET /api/mentions: client-scoped mention feed with filters."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query

from app.api.deps import ClientIdDep, SessionDep
from app.api.schemas import MentionPage
from app.models import MentionSource, Sentiment, queries

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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MentionPage:
    """Mention feed, newest first.

    Filters: source, sentiment (or 'none' for unclassified), keyword,
    published-at window, and `q` substring search over title/content.
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
    }
    items = queries.list_mentions(session, client_id, limit=limit, offset=offset, **common)
    total = queries.count_mentions(session, client_id, **common)
    return MentionPage(items=items, total=total)
