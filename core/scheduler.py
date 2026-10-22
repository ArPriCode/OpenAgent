import datetime
from typing import Tuple
from config.settings import settings

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

class TimeWindowScheduler:
    """
    Validates whether the current local time falls inside the user-configured
    active contribution window (e.g. 12:00 to 14:00).
    Outside this window, the agent stays dormant and does not perform uninvited actions.
    """

    def __init__(self, start_time_str: str = None, end_time_str: str = None, tz_name: str = None):
        self.start_str = start_time_str or settings.WORK_WINDOW_START
        self.end_str = end_time_str or settings.WORK_WINDOW_END
        self.tz_name = tz_name or settings.TIMEZONE

    def _parse_time(self, time_str: str) -> datetime.time:
        parts = time_str.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return datetime.time(hour=hour, minute=minute)

    def get_current_time(self) -> datetime.datetime:
        if ZoneInfo and self.tz_name:
            try:
                return datetime.datetime.now(ZoneInfo(self.tz_name))
            except Exception:
                pass
        return datetime.datetime.now()

    def is_active_now(self) -> Tuple[bool, str]:
        """
        Returns (is_active, human_readable_status)
        Supports both same-day windows (e.g. 12:00 to 14:00) and overnight windows (e.g. 23:00 to 02:00)
        """
        now = self.get_current_time()
        curr_t = now.time()
        start_t = self._parse_time(self.start_str)
        end_t = self._parse_time(self.end_str)

        if start_t <= end_t:
            # Standard window (e.g., 12:00 to 14:00)
            active = start_t <= curr_t <= end_t
        else:
            # Spans overnight (e.g., 23:00 to 02:00)
            active = curr_t >= start_t or curr_t <= end_t

        status_msg = (
            f"Active Window [{self.start_str} - {self.end_str}] "
            f"(Current time: {curr_t.strftime('%H:%M:%S')}) -> {'🟢 RUNNING' if active else '⏸️ DORMANT/WAITING'}"
        )
        return active, status_msg

    def seconds_until_next_window(self) -> int:
        now = self.get_current_time()
        curr_t = now.time()
        start_t = self._parse_time(self.start_str)

        start_dt = now.replace(hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0)
        if curr_t > start_t:
            # Next window is tomorrow
            start_dt += datetime.timedelta(days=1)

        diff = (start_dt - now).total_seconds()
        return max(10, int(diff))
