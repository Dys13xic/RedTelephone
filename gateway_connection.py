# 3rd Party
import websockets

# Standard library
import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace

URI = "wss://gateway.discord.gg"
API_VERSION = 10

@dataclass
class GatewayMessage:
    op: int
    d: dict = None
    s: int = None
    t: int = None

    def stringify(self):
        pass

    @staticmethod
    def objectify(string):
        jsonDict = json.loads(string)
        classObj = GatewayMessage(**jsonDict)
        # Convert data field to a Simple Namespace
        # print(classObj.d)
        # classObj.d = json.loads(classObj.d, object_hook=lambda data: SimpleNamespace(**data))
        # return classObj

class Gateway:
    token: str
    _heartbeatInterval: float
    _lastSequence: int = None
    _sendQueue: asyncio.Queue

    def __init__(self, token):
        self.token = token
        self._heartbeatInterval = 1
        self._lastSequence = None
        self._sendQueue = asyncio.Queue()

    async def _run(self):
        webSocketURI = "{}/?v={}&encoding=json".format(URI, API_VERSION)
        async with websockets.connect(webSocketURI, open_timeout=15) as websocket:
            self._recvTask = asyncio.create_task(self._msgRecv(websocket))
            self._sendTask = asyncio.create_task(self._msgSend(websocket))
            self._heartbeatTask = asyncio.create_task(self._heartbeat())
            # asyncio.gather(self._msgRecv(websocket), self._msgSend(websocket), self._heartbeat())
            await self._recvTask
            await self._heartbeatTask
            await self._sendTask
        
    async def _stop(self):
        self._recvTask.cancel()
        self._sendTask.cancel()
        self._heartbeatTask.cancel()

    async def _heartbeat(self):
        while True:
            lastSequence = self._lastSequence if self._lastSequence else "null"
            msg = {"op": 1, "d": lastSequence}
            await self._sendQueue.put(json.dumps(msg))
            await asyncio.sleep(self._heartbeatInterval)

    async def _msgSend(self, websocket):
        while True:
            msg = await self._sendQueue.get()
            print(msg)
            try:
                await websocket.send(msg)
            except websockets.exceptions.ConnectionClosed as e:
                print(e)
                await self._stop()
            except Exception as e:
                print(e)

    async def _msgRecv(self, websocket):
            try:
                async for msg in websocket:
                    print(msg)
                    msgObj = GatewayMessage.objectify(msg)
                    await self.processMsg(msgObj)
            except websockets.exceptions.ConnectionClosed as e:
                print(e)
                await self._stop()

    async def processMsg(msgObj):
        raise NotImplementedError

    def setHeartbeatInterval(self, ms):
        self._heartbeatInterval = ms / 1000

    # def setLastSequence(self, sequence):
    #     self._lastSequence = sequence

g = Gateway()
# asyncio.run(g._run())
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(g._run())
finally:
    loop.close()
