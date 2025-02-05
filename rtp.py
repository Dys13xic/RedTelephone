# 3rd Party
import nacl.secret

# Standard Library
import asyncio
from dataclasses import dataclass

class PayloadType():
    RTP = 120
    RCTP = 200

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

        # https://git.kaydax.xyz/w/algos/src/branch/main/doc/crypt.md

        # RTCP packet
        if 200 <= self.payloadType <= 204:
            self.payloadType = PayloadType.RCTP
            headerLength = 8

        # RTP packet
        else:
            self.payloadType = PayloadType.RTP
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

    def byteStringify(self):
        return self.header + self.payload + self.nonce[:4]
    
    def stripExtensionHeader(self):
        if self.payloadType == PayloadType.RTP:
            xMask = int('00010000', 2)
            if self.versionFlags & xMask:
                self.versionFlags = self.versionFlags ^ xMask
                extensionLength = int.from_bytes(self.header[14:16])

                self.header = int(self.versionFlags).to_bytes(1) + self.header[1:12]
                self.payload = self.payload[extensionLength * RtpMessage.EXTENSION_SIZE:]

    
    def setSSRC(self, ssrc):
        match self.payloadType:
            case PayloadType.RTP:
                self.header = self.header[:8] + int.to_bytes(ssrc, 4) + self.header[12:]

            case PayloadType.RCTP:
                self.header = self.header[:4] + int.to_bytes(ssrc, 4)

            case _:
                raise ValueError("Unsupported payload type in RTP message.")


class RtpEndpointProtocol:
    def __init__(self):
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport

    def send(self, data):
        raise NotImplementedError

    def datagram_received(self, data, addr):
        raise NotImplementedError

    def error_received(self, e):
        print("Error Received: ", e)

    def connection_lost(self, e):
        print("Connection Lost: ", e)

    def stop(self):
        self._transport.close()
        self._transport = None


class RtpEndpoint(RtpEndpointProtocol):
    def __init__(self, ssrc=None, encrypted=False):
        super().__init__()

        self.ssrc = ssrc
        self.encrypted = encrypted
        self._nonceCount = 0

        self._secretBox = None
        self.proxyEndpoint = None
        self.ctrlProxyEndpoint = None

    def send(self, msgObj):
        if self.ssrc:
            msgObj.setSSRC(self.ssrc)

        if self.encrypted:
            if self._secretBox:
                self.encrypt(msgObj)
            else:
                return
        else:
            # Grandstream HT801 doesn't support RTP header extensions.
            msgObj.stripExtensionHeader()
        
        if self._transport:
            try:
                self._transport.sendto(msgObj.byteStringify())
            except Exception as e:
                print(e)

    def datagram_received(self, data, addr):
        msgObj = RtpMessage(data, self.encrypted)

        if self.encrypted:
            if self._secretBox:
                self.decrypt(msgObj)
            else:
                return

        if msgObj.payloadType == PayloadType.RCTP and self.ctrlProxyEndpoint:
            self.ctrlProxyEndpoint.send(msgObj)

        elif self.proxyEndpoint:
            self.proxyEndpoint.send(msgObj)

    def encrypt(self, msgObj):
        self._nonceCount += 1
        msgObj.nonce = int.to_bytes(self._nonceCount, 4, byteorder='big') + b'\00' * 20
        msgObj.payload = self._secretBox.encrypt(msgObj.payload, msgObj.header, msgObj.nonce).ciphertext

    def decrypt(self, msgObj):
        msgObj.payload = self._secretBox.decrypt(msgObj.payload, msgObj.header, msgObj.nonce)
        msgObj.nonce = b''

    def setSecretKey(self, secretKey):
        self._secretBox = nacl.secret.Aead(bytes(secretKey))

    @staticmethod
    def proxy(x, y, xCtrl=None, yCtrl=None):
        x.proxyEndpoint = y
        x.ctrlProxyEndpoint = yCtrl
        y.proxyEndpoint = x
        y.ctrlProxyEndpoint = xCtrl

        if xCtrl:
            xCtrl.ctrlProxyEndpoint = yCtrl
        if yCtrl:
            yCtrl.ctrlProxyEndpoint = xCtrl

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