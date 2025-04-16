# Standard Library
import asyncio
from typing import Callable

# 1st Party
from .sipMessage import SipMessageFactory

class Transport():
    def __init__(self, publicIP, port, handleMsgCallback):
        self.ip: str = publicIP
        self.port: int = port
        self.handleMsgCallback: Callable = handleMsgCallback
        self._transport: asyncio.DatagramTransport = None

    def connection_made(self, transport):
        """Called on UDP transport established"""
        self._transport = transport

    def send(self, msgObj, addr):
        """Send a Sip message to the specified address"""
        data = str(msgObj).encode('utf-8')
        self._transport.sendto(data, addr)
        print(data)

    def datagram_received(self, data, addr):
        try:
            msg = data.decode('utf-8')
            msgObj = SipMessageFactory.fromStr(msg, addr)
            asyncio.create_task(self.handleMsgCallback(msgObj, addr))
        except Exception as e:
            pass

    def error_received(e):
        """Called on UDP transport error. Log event."""
        pass

    def connection_lost(e):
        """Called on UDP transport connection lost. Log event."""
        pass

    def stop(self):
        """Gracefully shutdown UDP transport."""
        self._transport.close()