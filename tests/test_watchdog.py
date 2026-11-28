# 🐶 READY ウォッチドッグのテスト
from makeitaquote.watchdog import ReadyWatchdog

LIMIT = 120.0


def test_not_expired_right_after_start():
    watchdog = ReadyWatchdog(now=1000.0)
    assert watchdog.is_expired(1000.0, LIMIT) is False
    assert watchdog.is_expired(1000.0 + LIMIT - 1, LIMIT) is False


def test_expired_when_ready_never_arrives():
    watchdog = ReadyWatchdog(now=1000.0)
    assert watchdog.is_expired(1000.0 + LIMIT, LIMIT) is True


def test_ready_clears_expiry():
    watchdog = ReadyWatchdog(now=1000.0)
    watchdog.observe(True, 1000.0 + LIMIT + 10)
    assert watchdog.is_expired(1000.0 + LIMIT + 20, LIMIT) is False


def test_counts_from_the_moment_ready_is_lost():
    watchdog = ReadyWatchdog(now=0.0)
    watchdog.observe(True, 10.0)  # READY を受信
    watchdog.observe(False, 50.0)  # ここから未 READY
    assert watchdog.is_expired(50.0 + LIMIT - 1, LIMIT) is False
    assert watchdog.is_expired(50.0 + LIMIT, LIMIT) is True


def test_on_fire_resets_the_base():
    watchdog = ReadyWatchdog(now=0.0)
    assert watchdog.is_expired(LIMIT, LIMIT) is True
    watchdog.on_fire(LIMIT)
    assert watchdog.is_expired(LIMIT, LIMIT) is False
    assert watchdog.is_expired(LIMIT * 2, LIMIT) is True
