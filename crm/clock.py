"""Business-day clock.

Bills, expenses and reports are dated in the shop's timezone, not the server's:
a hosted server running in UTC must still date a 1 AM IST bill as today in India.
"""
import datetime as dt

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception

# Used when the OS has no timezone database (e.g. Windows without the tzdata package).
FIXED_OFFSETS = {'Asia/Kolkata': dt.timezone(dt.timedelta(hours=5, minutes=30), 'IST')}


def resolve_timezone(name):
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return FIXED_OFFSETS.get(name, dt.timezone.utc)


class Clock:
    def __init__(self, timezone='Asia/Kolkata'):
        self.tz = resolve_timezone(timezone)

    def now(self):
        return dt.datetime.now(self.tz)

    def now_iso(self):
        return self.now().isoformat(timespec='seconds')

    def today(self):
        return self.now().date()

    def today_iso(self):
        return self.today().isoformat()

    def timestamp(self):
        return int(self.now().timestamp())
