"""Pure spike math: z-score of the newest hourly bucket vs trailing baseline.

No session, no clock, no globals: `buckets` is an ascending list of
(hour_start, count) tuples and every threshold/window is an argument, so
tests pin behavior with frozen timestamps.
"""

import math
from datetime import timedelta

from app.models.spike_event import SpikeEvent

#: Trailing baseline: 14 days of completed hours.
DEFAULT_BASELINE_WINDOW = 14 * 24

#: Meltwater-style default sensitivity (z-score gate).
DEFAULT_THRESHOLD = 2.5

#: Below this many baseline buckets the z-score is noise, not signal.
MIN_BASELINE_BUCKETS = 24


def detect_spike(
    buckets: list[tuple],
    baseline_window: int = DEFAULT_BASELINE_WINDOW,
    threshold: float = DEFAULT_THRESHOLD,
) -> SpikeEvent | None:
    """Return a transient SpikeEvent when the last bucket is anomalous.

    The baseline is the `baseline_window` buckets preceding the last one;
    z = (count - mean) / population_std. A zero-std baseline spikes only
    when the last count exceeds the mean (z treated as infinite). Returns
    None for empty input or short history — never raises on quiet data.
    """
    if not buckets:
        return None
    window_start, count = buckets[-1]
    baseline = [value for _, value in buckets[-1 - baseline_window : -1]]
    if len(baseline) < MIN_BASELINE_BUCKETS:
        return None
    mean = sum(baseline) / len(baseline)
    variance = sum((value - mean) ** 2 for value in baseline) / len(baseline)
    stddev = math.sqrt(variance)
    if stddev == 0:
        if count <= mean:
            return None
        zscore = float("inf")
    else:
        zscore = (count - mean) / stddev
    if zscore < threshold:
        return None
    return SpikeEvent(
        window_start=window_start,
        window_end=window_start + timedelta(hours=1),
        count=count,
        baseline_mean=mean,
        baseline_stddev=stddev,
        zscore=zscore,
    )
