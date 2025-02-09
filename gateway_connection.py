# 3rd Party
import websockets

# Standard Library
import asyncio
from typing import Any
import json
from dataclasses import dataclass, asdict
import logging
import os

API_VERSION = 10


@dataclass
class GatewayMessage:
    op: int
    d: Any = None
    s: int = None
    t: str = None

    def stringify(self):
        classDict = asdict(self)
        jsonString = json.dumps(classDict)
        return jsonString

    @staticmethod
    def objectify(string):
        jsonDict = json.loads(string)
        classObj = GatewayMessage(**jsonDict)
        return classObj

class GatewayConnection:
    token: str
    lastSequence: int = None
    _endpoint: str
    _params: str
    _heartbeatInterval: float
    _sendQueue: asyncio.Queue
    _tasks: asyncio.Future

    def __init__(self, token, endpoint, params=''):
        self.token = token
        self.lastSequence = None
        self._endpoint = endpoint
        self._params = params
        self._heartbeatInterval = 1
        self._sendQueue = asyncio.Queue()
        self._tasks = None

    async def run(self):
        logging.basicConfig(format='%(message)s', level=logging.DEBUG)
        os.environ['WEBSOCKETS_MAX_LOG_SIZE'] = '1000'

        while True:
            try:
                await self._start()
            except websockets.exceptions.ConnectionClosedError as e:
                self._stop(e.code)
            except Exception as e:
                print(e)
            
    async def runAfter(self, event):
        await event.wait()
        await self.run()

    async def _start(self):
        async with websockets.connect(self._endpoint + '?v={}'.format(API_VERSION) + self._params, open_timeout=15) as websock:
            self._tasks = asyncio.gather(self._recvLoop(websock), self._sendLoop(websock), self._heartbeatLoop())
            await self._tasks
        
    def _stop(self, closeCode=None, alwaysClean=False):
        self._tasks.cancel()
        if closeCode and not self.isResumable(closeCode):
            self.clean()

    async def _sendLoop(self, websock):
        while True:
            # try:
            msg = await self._sendQueue.get()
            await websock.send(msg)
            # except websockets.exceptions.ConnectionClosedError as e:
            #     raise
            # except Exception as e:
            #     print(e)

    async def _recvLoop(self, websock):
        while True:
            # try:
            msg = await websock.recv()
            msgObj = GatewayMessage.objectify(msg)
            await self.processMsg(msgObj)
            # except websockets.exceptions.ConnectionClosedError as e:
            #     raise
            # except Exception as e:
            #     print(e)

    async def _heartbeatLoop(self):
        while True:
            msgObj = self.genHeartBeat()
            await self.send(msgObj)
            await asyncio.sleep(self._heartbeatInterval)

    def setToken(self, token):
        self.token = token

    def setEndpoint(self, endpoint):
        self._endpoint = endpoint

    def setHeartbeatInterval(self, ms):
        self._heartbeatInterval = ms / 1000

    async def send(self, msgObj):
        await self._sendQueue.put(msgObj.stringify())

    async def reconnect(self, resumable=True):
        self._stop()
        if not resumable:
            self.clean()

        await self._start()

    def clean(self):
        self.lastSequence = None
        # self._heartbeatInterval = 1
        self._sendQueue = asyncio.Queue()
        self._tasks = None

    async def processMsg(self, msgObj):
        raise NotImplementedError

    def genHeartBeat(self):
        raise NotImplementedError
    
    def isResumable(self, closeCode):
        raise NotImplementedError


if __name__ == "__main__":
    g = GatewayConnection("alksdjfdsklf")
    # asyncio.run(g._run())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(g.run())
    finally:
        loop.close()