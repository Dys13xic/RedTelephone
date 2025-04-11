from datetime import datetime, timezone
from enum import Enum


class Weekdays(Enum):
    """Enum class for days of the week."""
    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    SAT = 5
    SUN = 6

class DoNotDisturb():
    """Holds do-not-disturb timeframes and manages validation."""
    timeFrame: tuple
    weekdayOverride: dict

    def __init__(self,  timeFrames=[], weekdayOverride={}, tz=timezone.utc):
        self.timeFrames = timeFrames
        self.weekdayOverride = weekdayOverride
        self.tz = tz

    def violated(self):
        """Return whether the current time falls within a do-not-disturb window."""
        currentDateTime = datetime.now(tz=self.tz)
        weekday = Weekdays(currentDateTime.weekday())

        # Override for specific weekdays
        if weekday in self.weekdayOverride:
            for timeFrame in self.weekdayOverride.get(weekday, []):
                startHr, endHr = timeFrame
                if startHr <= currentDateTime.hour < endHr:
                    return True
                
        # Generic
        else:
            for timeFrame in self.timeFrames:
                startHr, endHr = timeFrame
                if startHr <= currentDateTime.hour < endHr:
                    return True
            
        return False