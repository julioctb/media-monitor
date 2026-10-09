"""Ingest package: source adapters that poll providers and insert mentions.

Adapters (transport only, no DB):
- base.py        — SourceAdapter contract + RawMention dataclass
- google_news.py — Google News RSS poll (free)
- gdelt.py       — GDELT 2.0 doc API poll (free)
- feeds.py       — arbitrary client-configured RSS/Atom feeds (rss_custom)
- twitter_x.py   — X/Twitter third-party provider poll (paid, pluggable)
- matching.py    — accent/case-insensitive keyword matching engine (ES+EN)
- pipeline.py    — fetch -> match -> sentiment -> dedupe insert orchestration

Every adapter returns RawMention values; persistence goes exclusively
through app.models.queries.insert_mention (url_hash dedupe, client scoping).
Polling cadence comes from INGEST_INTERVAL_MIN (app.worker); enabled
adapters and their configuration come from the cycle's effective settings
(app.settings_runtime).
"""
