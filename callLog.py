from collections import deque
from datetime import datetime, timezone, timedelta

class CallLog:

    def __init__(self, hourlyLimit, tz=timezone.utc):
        self.calls = deque(maxlen=hourlyLimit)
        self.tz = tz

    def record(self):
        currentDateTime = datetime.now(tz=self.tz)
        self.calls.append(currentDateTime)

    def callLimitExceeded(self):
        return bool(self.nextAllowedTime())

    def nextAllowedTime(self):
        currentDateTime = datetime.now(tz=self.tz)

        if len(self.calls) == self.calls.maxlen:
            nextAllowedTime = self.calls[0] + timedelta(hours=1)
            if nextAllowedTime > currentDateTime:
                return nextAllowedTime.strftime('%I:%M:%S')

        return None