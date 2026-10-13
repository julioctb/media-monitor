"""Source adapter contract shared by every ingest adapter.

Adapters are transport-only: they fetch raw items for a list of keyword
texts and return RawMention values. Persistence (dedupe, client scoping,
sentiment) lives in app.ingest.pipeline so adapters stay unit-testable
without a database.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.base import MentionSource

log = logging.getLogger("ingest.base")


@dataclass(slots=True)
class RawMention:
    """A single item fetched from a source, before persistence.

    `keyword` is the keyword text that surfaced the item (used to resolve
    keyword_id and to re-validate the match in the pipeline).
    """

    source: MentionSource
    keyword: str
    url: str
    external_id: str | None = None
    title: str | None = None
    content: str | None = None
    author: str | None = None
    lang: str | None = None
    published_at: datetime | None = None
    reach: int | None = None
    raw: dict[str, Any] | None = None


class SourceAdapter(ABC):
    """Polls one source and returns raw mentions for the given keywords."""

    #: Short identifier used in logs and stats.
    name: str = "adapter"

    @abstractmethod
    def fetch(
        self, keywords: Sequence[str], since: datetime | None = None
    ) -> list[RawMention]:
        """Fetch raw mentions matching any of `keywords`.

        `since` is the client's ingest watermark for this adapter (already
        overlap-adjusted) or None on the first run. Adapters that cannot
        filter by date may ignore it; those that can narrow the window
        SHOULD, so repeated cycles stop re-scanning the same items.

        Implementations must never raise for a single failing keyword:
        log and continue, so one bad source/keyword cannot stall the cycle.
        """
        raise NotImplementedError
