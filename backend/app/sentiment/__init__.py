"""Sentiment package: pluggable analyzers producing (label, score) results.

- base.py         — SentimentAnalyzer interface + SentimentResult
- api_analyzer.py — OpenAI-compatible analyzer (worker fallback + probe)
- canonical.py    — enrichment-wins policy for mentions.sentiment

The local Laya layer is gone: the enrichment pass (app.enrich.llm) is the
canonical classifier and the API analyzer is the only sentiment engine.
"""
