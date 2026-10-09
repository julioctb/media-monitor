"""Spike detection over saved searches (T2) and AI spike summaries (T3)."""

from app.spike.detect import (
    DEFAULT_BASELINE_WINDOW,
    DEFAULT_THRESHOLD,
    MIN_BASELINE_BUCKETS,
    detect_spike,
)
from app.spike.scan import run_spike_scan, scan_saved_search
from app.spike.summary import build_summary_generator, summarize_spike  # noqa: F401

__all__ = [
    "DEFAULT_BASELINE_WINDOW",
    "DEFAULT_THRESHOLD",
    "MIN_BASELINE_BUCKETS",
    "build_summary_generator",
    "detect_spike",
    "run_spike_scan",
    "scan_saved_search",
    "summarize_spike",
]
