from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return a timezone-aware UTC datetime.

    Python 3.14+ deprecates datetime.utcnow(); use timezone-aware timestamps instead.
    """

    return datetime.now(timezone.utc)
