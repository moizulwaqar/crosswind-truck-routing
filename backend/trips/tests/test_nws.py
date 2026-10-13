from datetime import datetime, timedelta, timezone

from trips.providers.nws import duration_hours, value_at


def test_duration_hours():
    assert duration_hours("PT1H") == 1
    assert duration_hours("PT6H") == 6
    assert duration_hours("P1DT2H") == 26
    assert duration_hours("PT30M") == 0.5


def test_period_total_becomes_an_hourly_rate():
    start = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
    intervals = [(start, start + timedelta(hours=6), 25.4, 6)]  # 25.4 mm over 6 h
    # 25.4 mm / 6 h = 1 in / 6 h
    assert value_at(intervals, start + timedelta(hours=2), rate=True, scale=1 / 25.4) == 1 / 6
    assert value_at(intervals, start + timedelta(hours=6), rate=True) == 0
