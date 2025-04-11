from collections import defaultdict
import asyncio

class EventHandler:
    """Handle listeners and dispatching of events."""
    def __init__(self):
        self.events = defaultdict(list)

    def on(self, eventName, callback):
        """Register an event listener."""
        self.events[eventName].append(callback)

    def event(self, func):
        """Register an event listener through a function decorator."""
        async def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result
        
        self.on(func.__name__.removeprefix('on_'), wrapper)
        return wrapper

    async def dispatch(self, eventName, *args):
        """Dispatch an event to registered listeners."""
        if eventName in self.events:
            for callback in self.events[eventName]:
                # Run asynchronous code as task
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(*args))
                # Run synchronous code normally
                else:
                    callback(*args)