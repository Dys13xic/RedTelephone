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
LOGGING = True


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
    lastSequence: int
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

    def setToken(self, token):
        self.token = token

    def setEndpoint(self, endpoint):
        self._endpoint = endpoint

    def setParams(self, params):
        self._params = params

    def setHeartbeatInterval(self, ms):
        self._heartbeatInterval = ms / 1000

    async def connect(self):
        raise NotImplementedError

    async def _start(self):
        if LOGGING:
            logging.basicConfig(format='%(message)s', level=logging.DEBUG)
            os.environ['WEBSOCKETS_MAX_LOG_SIZE'] = '1000'

        async with websockets.connect(self._endpoint + '?v={}'.format(API_VERSION) + self._params, open_timeout=15) as websock:
            self._websock = websock
            self._tasks = asyncio.gather(self._recvLoop(websock), self._heartbeatLoop())
            await self._tasks

    def _stop(self, clean=True):
        self._tasks.cancel()      
        if clean:
            self._clean()

    async def _recvLoop(self, websock):
        while True:
            try:
                msg = await websock.recv()
                msgObj = GatewayMessage.objectify(msg)
                await self.processMsg(msgObj)
            except TypeError as e:
                print(e)
            except asyncio.CancelledError:
                print('Receive task cancelled.')
                # TODO for some reason this is being called by the regular Gateway as well as voice Gateway on leaveVoice
                # break

    async def _heartbeatLoop(self):
        while True:
            msgObj = self.genHeartBeat()
            await self.send(msgObj)
            await asyncio.sleep(self._heartbeatInterval)

    async def send(self, msgObj):
        await self._websock.send(msgObj.stringify())

    # TODO is clean the correct term seeing as we're not overwriting the token?
    def _clean(self):
        self.lastSequence = None
        # self._endpoint = ''
        self._params = ''
        self._heartbeatInterval = 1
        self._sendQueue = asyncio.Queue()
        self._tasks = None

    async def processMsg(self, msgObj):
        raise NotImplementedError

    def genHeartBeat(self):
        raise NotImplementedError