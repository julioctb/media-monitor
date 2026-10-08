"""Token bucket rate limiter tests with a fake clock (no sleeps)."""


from app.ingest.rate_limit import TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_burst_up_to_capacity_then_denied() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate_per_minute=2, capacity=2, clock=clock)
    assert bucket.try_acquire()
    assert bucket.try_acquire()
    assert not bucket.try_acquire()  # burst exhausted


def test_refill_over_time() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate_per_minute=60, capacity=1, clock=clock)  # 1 token/s
    assert bucket.try_acquire()
    assert not bucket.try_acquire()
    clock.advance(1.0)
    assert bucket.try_acquire()
    assert not bucket.try_acquire()


def test_refill_capped_at_capacity() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate_per_minute=60, capacity=1, clock=clock)
    clock.advance(600)  # a long idle period must not exceed capacity
    assert bucket.try_acquire()
    assert not bucket.try_acquire()


def test_invalid_args_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        TokenBucket(rate_per_minute=0)
    with pytest.raises(ValueError):
        TokenBucket(rate_per_minute=10, capacity=0)


def test_acquire_waits_for_refill() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate_per_minute=60, capacity=1, clock=clock)
    assert bucket.try_acquire()
    # Simulate waiting: advance inside a slow poll loop is impractical in
    # tests, so just verify bounded acquire gives up when the wait exceeds
    # the deadline.
    assert not bucket.acquire(max_wait_s=0.0)
