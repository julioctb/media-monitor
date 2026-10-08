"""Sentiment package: pluggable analyzers producing (label, score) results.

- base.py     — SentimentAnalyzer interface + SentimentResult
- laya_analyzer.py — Laya choice-based analyzer (Apache-2.0, self-hosted, lazy load)
- baseline.py — KeywordBaselineAnalyzer fallback (no model, ES+EN word lists)

pysentimiento is intentionally NOT used: its Spanish model trains on the
TASS dataset under a non-commercial license — legal risk for a client
project (see odd/tasks/media-monitor-mvp.md).
"""
