from collections import defaultdict
import asyncio

class EventHandler:
    def __init__(self):
        self.events = defaultdict(list)

    def on(self, eventName, callback):
        self.events[eventName].append(callback)

    async def dispatch(self, eventName, *args):
        if eventName in self.events:
            for callback in self.events[eventName]:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args)
                else:
                    callback(*args)