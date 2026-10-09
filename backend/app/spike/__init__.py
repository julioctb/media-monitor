"""Spike detection over saved searches (T2) and AI spike summaries (T3)."""

from app.spike.detect import (
    DEFAULT_BASELINE_WINDOW,
    DEFAULT_THRESHOLD,
    MIN_BASELINE_BUCKETS,
    detect_spike,
)
from app.spike.scan import run_spike_scan, scan_saved_search

__all__ = [
    "DEFAULT_BASELINE_WINDOW",
    "DEFAULT_THRESHOLD",
    "MIN_BASELINE_BUCKETS",
    "detect_spike",
    "run_spike_scan",
    "scan_saved_search",
]
