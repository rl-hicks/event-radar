from datetime import datetime, timedelta


def upcoming_weekend_window(now: datetime) -> tuple[datetime, datetime]:
    """Return the remaining current or next Friday-through-Sunday window."""
    if now.utcoffset() is None:
        raise ValueError("Weekend calculation requires a timezone-aware datetime.")

    if now.weekday() >= 4:
        friday = now - timedelta(days=now.weekday() - 4)
    else:
        friday = now + timedelta(days=4 - now.weekday())

    friday = friday.replace(hour=0, minute=0, second=0, microsecond=0)
    end = friday + timedelta(days=3)
    return max(now, friday), end
