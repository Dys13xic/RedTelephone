# 3rd Party
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

# Standard library
import asyncio
import os
from dataclasses import dataclass

@dataclass
class RtpMessage:
    def __init__(self):
        pass

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
        self.encrypted = encrypted

    def datagram_received(self, data, addr):
        print(data, addr)

        if(self.proxyEndpoint):
            # TODO encrypt or decrypt depending on direction
            self.proxyEndpoint.send(data)

    def encrypt(self, data):
        pass

    def decrypt(self, data):
        pass
            
    def getEncrypted(self):
        return self.encrypted
    
    def setProxyEndpoint(self, proxyEndpoint):
        self.proxyEndpoint = proxyEndpoint

async def main():
    loop = asyncio.get_event_loop()
    _, phoneEndpoint = await loop.create_datagram_endpoint(
        lambda: RtpEndpoint(encrypted=False),
        local_addr=("0.0.0.0", 5060),
        remote_addr=("10.13.0.6", 5060)
    )

    _, discordEndpoint = await loop.create_datagram_endpoint(
        lambda: RtpEndpoint(encrypted=True),
        local_addr=("0.0.0.0", 9998),
        remote_addr=("10.13.0.247", 9998)
    )

    phoneEndpoint.setProxyEndpoint(discordEndpoint)
    discordEndpoint.setProxyEndpoint(phoneEndpoint)

    await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())