from datetime import datetime, timezone
from enum import Enum


class Weekdays(Enum):
    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    SAT = 5
    SUN = 6

class DoNotDisturb():
    timeFrame: tuple
    weekdayOverride: dict

    def __init__(self,  timeFrames=[], weekdayOverride={}, tz=timezone.utc):
        self.timeFrames = timeFrames
        self.weekdayOverride = weekdayOverride
        self.tz = tz

    def violated(self):
        currentDateTime = datetime.now(tz=self.tz)
        weekday = Weekdays(currentDateTime.weekday())

        if weekday in self.weekdayOverride:
            for timeFrame in self.weekdayOverride.get(weekday, []):
                startHr, endHr = timeFrame
                if startHr <= currentDateTime.hour < endHr:
                    return True
        else:
            for timeFrame in self.timeFrames:
                startHr, endHr = timeFrame
                if startHr <= currentDateTime.hour < endHr:
                    return True
            
        return False