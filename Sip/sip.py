# 1st Party Library
from .transport import Transport
from .messageHandler import MessageHandler
from .userAgent import UserAgent

# Standard Library
import asyncio

class Sip(UserAgent):
    def __init__(self, publicAddress, sessionManager):
        self.messageHandler: MessageHandler = MessageHandler(userAgent=self)
        transport = None
        super().__init__(transport, publicAddress, sessionManager)

    async def run(self):
        loop = asyncio.get_event_loop()
        _, self.transport = await loop.create_datagram_endpoint(
        lambda: Transport(self.publicIP, handleMsgCallback=self.messageHandler.route),
        local_addr=("0.0.0.0", self.publicPort),
        )