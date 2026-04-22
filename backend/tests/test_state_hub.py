from datetime import datetime, timezone

from app.api.state_hub import Hub


def test_grace_remaining_counts_down():
    exited = datetime(2026, 4, 22, 10, 0, 0, tzinfo=timezone.utc).timestamp()
    rem = Hub._grace_remaining(
        "2026-04-22T10:00:00+00:00",
        grace_period_s=60,
        now_unix=exited + 30,
    )
    assert rem == 30


def test_grace_remaining_clamps_to_zero():
    exited = datetime(2026, 4, 22, 10, 0, 0, tzinfo=timezone.utc).timestamp()
    rem = Hub._grace_remaining(
        "2026-04-22T10:00:00+00:00",
        grace_period_s=60,
        now_unix=exited + 100,
    )
    assert rem == 0
