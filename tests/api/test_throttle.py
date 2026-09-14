"""`LoginThrottle`: bounded memory across many distinct IPs (no HTTP here).

Not exercised through `TestClient`: the memory-eviction behavior is a
property of `LoginThrottle` itself, and a fake clock lets the test move
time forward without sleeping.
"""

import threading

from inventory.api.auth import LoginThrottle

_THROTTLE_WINDOW_SECONDS = 15 * 60
_MAX_FAILURES = 5
# Mirrors `inventory.api.auth._SWEEP_CEILING`, which pyright's strict mode
# won't let a test import directly (`reportPrivateUsage`).
_SWEEP_CEILING = 256


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


def test_many_recent_failure_ips_hit_the_hard_cap_instead_of_growing_forever() -> None:
    """None of these failures ever age out, so only the hard cap bounds memory."""
    clock = _FakeClock()
    throttle = LoginThrottle(clock=clock)

    for i in range(_SWEEP_CEILING + 50):
        throttle.record_failure(f"10.1.0.{i}")

    assert throttle.tracked_ip_count <= _SWEEP_CEILING


def test_retry_after_seconds_rounds_up_to_the_next_whole_second() -> None:
    """899.4s of actual remaining window must report as 900, never 899."""
    clock = _FakeClock()
    throttle = LoginThrottle(clock=clock)

    for _ in range(_MAX_FAILURES):
        throttle.record_failure("10.2.0.1")
    clock.advance(0.6)

    assert throttle.retry_after_seconds("10.2.0.1") == 900


def test_concurrent_wrong_password_attempts_from_one_ip_never_record_past_the_ceiling() -> None:
    """20 threads racing through `attempt` with a wrong password from one IP.

    Before `attempt` held a single lock across the throttle check, the
    credential check, and the state update, several threads could each
    observe "not yet throttled" before any of them recorded its own
    failure, letting more than `_MAX_FAILURES` failures through the
    ceiling. `attempt` fully serializes each call, so with every thread
    failing its check the outcome is deterministic: exactly
    `_MAX_FAILURES` calls record a failure (return `"invalid"`) and
    every other call is throttled (returns an `int` retry-after), never
    the other way around.
    """
    clock = _FakeClock()
    throttle = LoginThrottle(clock=clock)
    ip = "10.3.0.1"
    thread_count = 20
    results: list[str | int] = []
    results_lock = threading.Lock()

    def worker() -> None:
        result = throttle.attempt(ip, lambda: False)
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    invalid_count = sum(1 for result in results if result == "invalid")
    throttled_count = sum(1 for result in results if isinstance(result, int))

    assert len(results) == thread_count
    assert invalid_count == _MAX_FAILURES
    assert throttled_count == thread_count - _MAX_FAILURES
    assert throttled_count >= 1
