"""One freshness rule for source UI and native operation-bound session authority."""

from datetime import datetime, timedelta


def step_up_is_fresh(timestamp: datetime | None, now: datetime, window_seconds: int) -> bool:
    if (
        timestamp is None
        or timestamp.tzinfo is None
        or timestamp.utcoffset() is None
        or now.tzinfo is None
        or now.utcoffset() is None
        or window_seconds < 1
    ):
        return False
    return 0 <= (now - timestamp).total_seconds() <= window_seconds


def step_up_valid_until(
    timestamp: datetime | None, now: datetime, window_seconds: int
) -> datetime | None:
    if timestamp is None or not step_up_is_fresh(timestamp, now, window_seconds):
        return None
    return timestamp + timedelta(seconds=window_seconds)
