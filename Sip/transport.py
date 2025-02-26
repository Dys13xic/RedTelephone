# Standard Library
import socket
import asyncio
from typing import Callable

# 1st Party
from .sipMessage import SipMessageFactory

class Transport():
    ip: str
    port: int
    handleMsgCallback: Callable


    def __init__(self, port, handleMsgCallback):
        self.port = port
        self.handleMsgCallback = handleMsgCallback
        self._transport = None

        # Retrieve local IP
        try:
            tempSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            tempSock.connect(("8.8.8.8", 80))
            self.ip = tempSock.getsockname()[0]
            tempSock.close()
        except:
            "Failed to determine local IP address"
            exit()

    def connection_made(self, transport):
        self._transport = transport

    def send(self, data, addr):
        try:
            print(data)
            self._transport.sendto(data, addr)
        except Exception as e:
            print("Failed to Send: ", e)
            exit(1)

    def datagram_received(self, data, addr):
        msg = SipMessageFactory.createFromStr(data.decode('utf-8'))
        asyncio.create_task(self.handleMsgCallback(msg, addr))

    def error_received(e):
        print("Error Received: ", e)
        exit(1)

    def connection_lost(e):
        print("Connection Lost: ", e)
        exit(1)

    def stop(self):
        self._transport.close()