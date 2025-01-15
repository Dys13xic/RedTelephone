# 3rd Party
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

# Standard library
import asyncio
import os
from dataclasses import dataclass

class RtpMessage:
    version: bytes = None
    payloadType: bytes = None
    payload: bytes = None
    header: bytes = None
    sequence: bytes = None
    timestamp: bytes = None
    SSRC: bytes = None
    audio: bytes = None
    nonce: bytes = None

    def __init__(self, packet):
        if len(packet) < 28:
            print('audio packet too small')
            exit()

        self.version = packet[0]
        self.payloadType = packet[1]

        # TODO add constant so not a magic number
        if self.payloadType == 120:
            self.header = packet[0:14]
            self.payload = packet[14:-4]
            self.nonce = packet[-4:] + packet[16:24]
            
            # self.sequence = packet[2:4]
            # self.timestamp = packet[4:8]
            # self.SSRC = packet[8:12]
            # self.nonce = packet[12:24]
            # self.audio = packet[24:-4]
            # self.append = packet[-4:]

class RtpEndpointProtocol:
    def __init__(self):
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport

    def send(self, data):
        try:
            self._transport.sendto(data)
        except Exception as e:
            print("Failed to Send: ", e)
            exit(1)

    def datagram_received(self, data, addr):
        raise NotImplementedError

    def error_received(e):
        print("Error Received: ", e)
        exit(1)

    def connection_lost(e):
        print("Connection Lost: ", e)
        exit(1)

    def stop(self):
        self._transport.close()

class RtpEndpoint(RtpEndpointProtocol):
    def __init__(self, encrypted):
        super().__init__()
        self.proxyEndpoint = None
        self._secretKey = None

    def datagram_received(self, data, addr):
        # print(data, addr)
        msgObj = RtpMessage(data)

        if msgObj.payload:
            if(self._secretKey):
                self.decrypt(msgObj)
                # print(msgObj.payload)

            if(self.proxyEndpoint):
                # TODO encrypt or decrypt depending on direction
                self.proxyEndpoint.send(data)

    def encrypt(self, data):
        pass

    def decrypt(self, msgObj):
        print(msgObj.header)
        print(msgObj.payload)
        print(msgObj.nonce)
        print(self._secretKey)
        print('\n\n')

        msgObj.payload = ChaCha20Poly1305(self._secretKey).decrypt(msgObj.nonce, msgObj.payload, msgObj.header)
            
    def getEncrypted(self):
        return self.encrypted
    
    def setSecretKey(self, secretKey):
        print('vvv')
        self._secretKey = bytes(secretKey)

    def setProxyEndpoint(self, proxyEndpoint):
        self.proxyEndpoint = proxyEndpoint

    # Potentially rejig this to be in the constructor (and not have RTPEndpoint inherit from RTPEndpoint Protocol)
    # @staticmethod
    # async def newEndpoint(remoteIP, remotePort, localPort, localAddress='0.0.0.0'):
    #     loop = asyncio.get_event_loop()
    #     _, endpoint = await loop.create_datagram_endpoint(
    #         lambda: RtpEndpoint(encrypted=False),
    #         local_addr=("0.0.0.0", localPort),
    #         remote_addr=(remoteIP, remotePort)
    #     )
    #     return endpoint

async def main():
    loop = asyncio.get_event_loop()
    _, phoneEndpoint = await loop.create_datagram_endpoint(
        lambda: RtpEndpoint(encrypted=False),
        local_addr=("0.0.0.0", 5004)
    )

    # _, phoneEndpoint = await loop.create_datagram_endpoint(
    #     lambda: RtpEndpoint(encrypted=False),
    #     local_addr=("0.0.0.0", 5060),
    #     remote_addr=("10.13.0.6", 5060)
    # )

    # _, discordEndpoint = await loop.create_datagram_endpoint(
    #     lambda: RtpEndpoint(encrypted=True),
    #     local_addr=("0.0.0.0", 9998),
    #     remote_addr=("10.13.0.247", 9998)
    # )

    # phoneEndpoint.setProxyEndpoint(discordEndpoint)
    # discordEndpoint.setProxyEndpoint(phoneEndpoint)

    await asyncio.sleep(360)

if __name__ == "__main__":
    asyncio.run(main())