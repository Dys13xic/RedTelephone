# Standard Library
import asyncio
from typing import Callable

class Transport():
    """Manage UDP transport for sending/receiving of SIP messages."""
    def __init__(self, handleMsg):
        self.handleMsg: Callable = handleMsg
        self._transport: asyncio.DatagramTransport = None

    def connection_made(self, transport):
        """Configure transport on connection established."""
        self._transport = transport

    def send(self, msg, addr):
        """Send a Sip message to the specified address"""
        data = str(msg).encode('utf-8')
        self._transport.sendto(data, addr)
        print(data)

    def datagram_received(self, data, addr):
        """Convert datagram to Sip message and pass to callback function."""
        try:
            msg = data.decode('utf-8')
            asyncio.create_task(self.handleMsg(msg, addr))
        except Exception as e:
            pass

    def error_received(e):
        """Log transport error."""
        pass

    def connection_lost(e):
        """Log connection lost."""
        pass

    def stop(self):
        """Gracefully shutdown transport."""
        self._transport.close()