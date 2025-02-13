# 3rd Party
import websockets

# Standard library
import asyncio
from typing import Any
import json
from dataclasses import dataclass, asdict
from types import SimpleNamespace

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
        # Convert data field to a Simple Namespace
        # print(classObj.d)
        # classObj.d = json.loads(classObj.d, object_hook=lambda data: SimpleNamespace(**data))
        return classObj

class GatewayConnection:
    token: str
    _endpoint: str
    _params: str
    _heartbeatInterval: float
    _lastSequence: int = None
    _sendQueue: asyncio.Queue

    def __init__(self, token, endpoint, params=''):
        self.token = token
        self._endpoint = endpoint
        self._params = params
        self._heartbeatInterval = 1
        self._lastSequence = None
        self._sendQueue = asyncio.Queue()

    async def _run(self):
        async with websockets.connect(self._endpoint + '?v={}'.format(API_VERSION) + self._params, open_timeout=15) as websock:
            self._recvTask = asyncio.create_task(self._recvLoop(websock))
            self._sendTask = asyncio.create_task(self._sendLoop(websock))
            self._heartbeatTask = asyncio.create_task(self._heartbeatLoop())
            # asyncio.gather(self._recvLoop(websock), self._sendLoop(websock), self._heartbeatLoop())
            await self._recvTask
            await self._heartbeatTask
            await self._sendTask

    async def _runAfter(self, event):
        await event.wait()
        await self._run()
        
    async def _stop(self):
        self._recvTask.cancel()
        self._sendTask.cancel()
        self._heartbeatTask.cancel()

    async def _sendLoop(self, websock):
        while True:
            msg = await self._sendQueue.get()
            print('\033[32m' + msg)
            try:
                await websock.send(msg)

            except websockets.exceptions.ConnectionClosed as e:
                print(e)
                await self._stop()       
            except Exception as e:
                print(e)


    async def _recvLoop(self, websock):
            try:
                async for msg in websock:
                    print('\033[31m' + msg)
                    msgObj = GatewayMessage.objectify(msg)
                    await self.processMsg(msgObj)

            except websockets.exceptions.ConnectionClosed as e:
                print(e)
                await self._stop()       
            except Exception as e:
                print(e)

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

    def setLastSequence(self, sequence):
        self._lastSequence = sequence

    async def send(self, msgObj):
        await self._sendQueue.put(msgObj.stringify())

    async def processMsg(self, msgObj):
        raise NotImplementedError
    
    def genHeartBeat(self):
        raise NotImplementedError

if __name__ == "__main__":
    g = GatewayConnection("alksdjfdsklf")
    # asyncio.run(g._run())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(g._run())
    finally:
        loop.close()