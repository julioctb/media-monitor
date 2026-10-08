"""SentimentAnalyzer contract shared by every engine."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models.base import Sentiment


@dataclass(frozen=True, slots=True)
class SentimentResult:
    """One classification: label plus the engine's confidence in it.

    `score` is the probability assigned to the chosen label when the
    engine produces one (Laya does), else a heuristic strength in [0, 1].
    """

    label: Sentiment
    score: float


class SentimentAnalyzer(ABC):
    """Classify the sentiment of a mention text."""

    @abstractmethod
    def analyze(self, text: str, lang: str) -> SentimentResult:
        """Return the sentiment of `text` (`lang` is an ISO code hint)."""
        raise NotImplementedError
