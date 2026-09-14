"""`LoginThrottle`: bounded memory across many distinct IPs (no HTTP here).

Not exercised through `TestClient`: the memory-eviction behavior is a
property of `LoginThrottle` itself, and a fake clock lets the test move
time forward without sleeping.
"""

from inventory.api.auth import LoginThrottle

_THROTTLE_WINDOW_SECONDS = 15 * 60


class _FakeClock:
    """A `time.monotonic`-shaped callable a test can advance on demand."""

    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_many_single_failure_ips_do_not_grow_the_dict_past_the_window() -> None:
    clock = _FakeClock()
    throttle = LoginThrottle(clock=clock)

    for i in range(300):
        throttle.record_failure(f"10.0.0.{i}")

    # every one of those 300 failures ages out of the window here.
    clock.advance(_THROTTLE_WINDOW_SECONDS + 1)

    throttle.record_failure("10.0.0.new")

    # the sweep shrank the dict back down instead of holding one stale
    # entry per IP forever.
    assert throttle.tracked_ip_count == 1
