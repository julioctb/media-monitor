"""Declarative base and shared enum types for the domain model."""

import enum

from sqlalchemy import BigInteger, Column, Integer
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base. All models derive from this class."""


# BIGINT on PostgreSQL; plain INTEGER on SQLite, whose dialect only
# autoincrements single-column INTEGER primary keys.
BigIntPk = BigInteger().with_variant(Integer(), "sqlite")


class IntPk:
    """Mixin for BigInteger autoincrement primary keys."""

    id = Column(BigIntPk, primary_key=True, autoincrement=True)


class MentionSource(str, enum.Enum):
    """Ingest source of a mention."""

    news_rss = "news_rss"
    gdelt = "gdelt"
    x_twitter = "x_twitter"


class Sentiment(str, enum.Enum):
    """Sentiment classification assigned by the sentiment stage."""

    positive = "positive"
    negative = "negative"
    neutral = "neutral"


class AlertChannel(str, enum.Enum):
    """Delivery channel for alerts (email only in MVP)."""

    email = "email"


class AlertDigest(str, enum.Enum):
    """Alert cadence: per-mention email or periodic digest."""

    instant = "instant"
    daily = "daily"
    weekly = "weekly"
