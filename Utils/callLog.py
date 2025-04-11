from collections import deque
from datetime import datetime, timezone, timedelta

class CallLog:
    """Manage a log of the last 'hourlyLimit' calls."""

    def __init__(self, hourlyLimit, tz=timezone.utc):
        self.calls = deque(maxlen=hourlyLimit)
        self.tz = tz

    def record(self):
        """Record a new call to the log."""
        currentDateTime = datetime.now(tz=self.tz)
        self.calls.append(currentDateTime)

    def callLimitExceeded(self):
        """Determine if the hourly call limit was exceeded."""
        return bool(self.nextAllowedTime())

    def nextAllowedTime(self):
        """If the call limit has been reached, Returns the next available time in hours:mins:seconds. Otherwise returns None."""
        currentDateTime = datetime.now(tz=self.tz)

        if len(self.calls) == self.calls.maxlen:
            # Add an hour to the oldest entry in the call log.
            nextAllowedTime = self.calls[0] + timedelta(hours=1)
            if nextAllowedTime > currentDateTime:
                return nextAllowedTime.strftime('%I:%M:%S')

        return None