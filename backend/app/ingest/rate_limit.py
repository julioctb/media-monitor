"""Thread-safe token bucket for client-side rate limiting.

Bursty up to `capacity`, then sustained at `rate_per_minute`. The clock is
injectable so tests verify refill behavior deterministically.
"""

import threading
import time
from collections.abc import Callable


class TokenBucket:
    """Token bucket: capacity tokens, refilled at rate_per_minute."""

    def __init__(
        self,
        rate_per_minute: float,
        capacity: float | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        self._rate = rate_per_minute / 60.0  # tokens per second
        self._capacity = float(capacity if capacity is not None else rate_per_minute)
        if self._capacity <= 0:
            raise ValueError("capacity must be positive")
        self._tokens = self._capacity
        self._clock = clock
        self._last = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Acquire without waiting; False if not enough tokens right now."""
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def acquire(self, tokens: float = 1.0, max_wait_s: float = 60.0) -> bool:
        """Acquire, sleeping until tokens are available (bounded by max_wait_s)."""
        deadline = self._clock() + max_wait_s
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                deficit = tokens - self._tokens
            if self._clock() + deficit / self._rate > deadline:
                return False
            time.sleep(min(deficit / self._rate, 0.25))

    @property
    def tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens
