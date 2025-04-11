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
    """Data class representing the message format utillized by Discord gateways."""
    op: int
    d: Any = None
    s: int = None
    t: str = None

    def __str__(self):
        classDict = asdict(self)
        jsonString = json.dumps(classDict)
        return jsonString

    @staticmethod
    def fromStr(string):
        jsonDict = json.loads(string)
        classObj = GatewayMessage(**jsonDict)
        return classObj

class GatewayConnection:
    """Manage underlying websocket connection and maintenance."""
    token: str
    lastSequence: int
    endpoint: str
    params: str
    _heartbeatInterval: float
    _sendQueue: asyncio.Queue
    _tasks: asyncio.Future
    _connected: asyncio.Event

    def __init__(self, token, endpoint, params=''):
        self.token = token
        self.lastSequence = None
        self.endpoint = endpoint
        self.params = params
        self._heartbeatInterval = 1
        self._sendQueue = asyncio.Queue()
        self._tasks = None
        self._connected = asyncio.Event()
        self.attempts = 0

    def setHeartbeatInterval(self, ms):
        """Set the interval at which to generate heartbeat messages."""
        self._heartbeatInterval = ms / 1000

    async def connect(self):
        """Start a gateway connection and specify reconnect behaviour. To be implemented by child class."""
        raise NotImplementedError
    
    async def disconnect(self):
        """Disconnect from the gateway after connection is fully established."""
        # TODO Add a timeout to waiting on _connected (in order to prevent queueing a disconnect to be executed much later.)?
        await self._connected.wait()
        self._stop()

    async def _start(self):
        """Open a websocket connection to Discord and start recv and heartbeat task loops."""
        self.attempts += 1
        async with websockets.connect(f'{self.endpoint}?v={API_VERSION}{self.params}', open_timeout=15) as websock:
            self._websock = websock
            self._tasks = asyncio.gather(self._recvLoop(websock), self._heartbeatLoop())
            self._connected.set()
            await self._tasks

    def _stop(self, clean=True):
        """Close the websocket connection to Discord and cancel task loops. Clean the gateway connection if specified."""
        self._connected.clear()
        self._tasks.cancel()
        if clean:
            self._clean()

    async def _recvLoop(self, websock):
        """Receive weboscket messages, convert them into gateway messages and pass into a processing task."""
        while True:
            msg = await websock.recv()
            try:
                msgObj = GatewayMessage.fromStr(msg)
            except TypeError as e:
                print(e)
            else:
                await self.processMsg(msgObj)

    async def _heartbeatLoop(self):
        """Send a heartbeat message every heartBeatInterval."""
        while True:
            msgObj = self.genHeartBeat()
            await self.send(msgObj)
            await asyncio.sleep(self._heartbeatInterval)

    async def send(self, msgObj):
        """Send a gateway message to the websocket endpoint."""
        await self._websock.send(str(msgObj))

    def _clean(self):
        """Revert session specific properties to defaults."""
        self.lastSequence = None
        self._heartbeatInterval = 1
        self._sendQueue = asyncio.Queue()
        self._tasks = None
        self._connected.clear()
        self.attempts = 0

    async def processMsg(self, msgObj):
        """Process incoming gateway messages. To be implemented by child class."""
        raise NotImplementedError

    def genHeartBeat(self):
        """Generate a heartbeat gateway message. To be implemented by child class."""
        raise NotImplementedError