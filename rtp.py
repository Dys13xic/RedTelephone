# 3rd Party
import nacl.secret

# Standard Library
import asyncio
from dataclasses import dataclass


class RtpMessage():
    DEFAULT_HEADER_SIZE = 12
    CSRC_SIZE = 4
    EXTENSION_SIZE = 4
    NONCE_SIZE = 24
    NONCE_COUNT_SIZE = 4

    payloadType: bytes = None
    header: bytes = None
    payload: bytes = None
    nonce: bytes = b''

    def __init__(self, packet, encrypted=False):
        self.encrypted = encrypted
        self.versionFlags = packet[0]
        self.payloadType = packet[1]  

        # RTP packet
        # https://git.kaydax.xyz/w/algos/src/branch/main/doc/crypt.md
        if not (200 <= self.payloadType <= 204):
            xMask = int('00010000', 2)
            cMask = int('00001111', 2)

            extendHeader = (self.versionFlags & xMask) > 0
            csrcCount = self.versionFlags & cMask

            headerLength = RtpMessage.DEFAULT_HEADER_SIZE + (csrcCount * RtpMessage.CSRC_SIZE) + (extendHeader * RtpMessage.EXTENSION_SIZE)
            self.header = packet[0:headerLength]

            if encrypted:
                self.payload = packet[headerLength:-RtpMessage.NONCE_COUNT_SIZE]
                self.nonce = packet[-RtpMessage.NONCE_COUNT_SIZE:] + b'\00' * (RtpMessage.NONCE_SIZE - RtpMessage.NONCE_COUNT_SIZE)
            else:
                self.payload = packet[headerLength:]

        # RTCP packet
        # else:

    def byteStringify(self):
        return self.header + self.payload + self.nonce[:4]
    
    def setSSRC(self, ssrc):
        self.header = self.header[:8] + int.to_bytes(ssrc, 4) + self.header[12:]


class RtpEndpointProtocol:
    def __init__(self):
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport

    def send(self, data):
        raise NotImplementedError

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
    def __init__(self, ssrc=None, encrypted=False):
        super().__init__()

        self.ssrc = ssrc
        self.encrypted = encrypted
        self._nonceCount = 0

        self._secretBox = None
        self.proxyEndpoint = None

    def send(self, msgObj):
        if self.ssrc:
            msgObj.setSSRC(self.ssrc)

        if self.encrypted:
            self.encrypt(msgObj)
        
        try:
            self._transport.sendto(msgObj.byteStringify())
        except Exception as e:
            print(e)

    def datagram_received(self, data, addr):
        # TODO clean up this fix for RTCP packets getting encrypted...
        if data[1] == 97 or (200 <= data[1] <= 204):
            return
        
        msgObj = RtpMessage(data, self.encrypted)

        if self._secretBox:
            self.decrypt(msgObj)

        if self.proxyEndpoint:
            self.proxyEndpoint.send(msgObj)

    def encrypt(self, msgObj):
        self._nonceCount += 1
        msgObj.nonce = int.to_bytes(self._nonceCount, 4, byteorder='big') + b'\00' * 20
        msgObj.payload = self._secretBox.encrypt(msgObj.payload, msgObj.header, msgObj.nonce).ciphertext

    def decrypt(self, msgObj):
        msgObj.payload = self._secretBox.decrypt(msgObj.payload, msgObj.header, msgObj.nonce)
    
    def setSecretKey(self, secretKey):
        self._secretBox = nacl.secret.Aead(bytes(secretKey))

    def setProxyEndpoint(self, proxyEndpoint):
        self.proxyEndpoint = proxyEndpoint


# Test code
async def main():
    loop = asyncio.get_event_loop()
    _, phoneEndpoint = await loop.create_datagram_endpoint(
        lambda: RtpEndpoint(encrypted=False),
        local_addr=("0.0.0.0", 5004)
    )
    await asyncio.sleep(360)

if __name__ == "__main__":
    asyncio.run(main())