"""Ingest package: source adapters that poll providers and insert mentions.

Planned adapters (implemented by ingest writers):
- google_news.py — Google News RSS poll
- gdelt.py       — GDELT 2.0 doc API poll
- twitter_x.py   — X/Twitter third-party provider poll

Every adapter MUST insert mentions scoped to a client_id and dedupe on
mentions.url_hash. Polling cadence comes from INGEST_INTERVAL_MIN.
"""
