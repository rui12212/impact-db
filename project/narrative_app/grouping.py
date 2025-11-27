from datetime import datetime, timedelta, timezone
from core.config import NARRATIVE_WINDOW_MINUTES

def parse_iso(ts: str) -> datetime:
    # Helper to parse ISO8601(str) to datetime(UTC)

    # handling the case including/excluding Z
    if ts.endswith("Z"):
        ts = ts[:-1]
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)

def to_iso(dt: datetime) -> str:
    # Helper to parse datetime to ISO8601
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def is_within_window(
        first_timestamp: datetime,
        new_timestamp: datetime,
) -> bool:
# Check if new_timestamp is qithin NARRATIVE_WINDOW_MINUTES compared to the first_timestamp
    window = timedelta(minutes=NARRATIVE_WINDOW_MINUTES)
    return (new_timestamp - first_timestamp) <= window