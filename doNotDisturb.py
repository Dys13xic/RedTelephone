from datetime import datetime
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
    def __init__(self,  timeFrames=[], weekdayOverride={}):
        self.timeFrames = timeFrames
        self.weekdayOverride = weekdayOverride

    def violated(self, dateTimeObj):
        weekday = Weekdays(dateTimeObj.weekday())

        if weekday in self.weekdayOverride:
            for timeFrame in self.weekdayOverride.get(weekday, []):
                startHr, endHr = timeFrame
                if startHr <= dateTimeObj.hour < endHr:
                    return True
        else:
            for timeFrame in self.timeFrames:
                startHr, endHr = timeFrame
                if startHr <= dateTimeObj.hour < endHr:
                    return True
            
        return False