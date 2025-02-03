# 1st Party
from sip import Sip
from rtp import RtpEndpoint

# Standard Library
import asyncio
from os import urandom


class Voip():
    def __init__(self, sipPort, rtpPort, rtcpPort):
        self.sipPort = sipPort
        self.rtpPort = rtpPort

        if rtcpPort:
            self.rtcpPort = rtcpPort
        else:
            self.rtcpPort = rtpPort + 1

        self.sipEndpoint = None
        self.activeDialog = None
        self.rtpEndpoint = None
        self.rtcpEndpoint = None
    
    async def run(self):
        loop = asyncio.get_event_loop()
        _, self.sipEndpoint = await loop.create_datagram_endpoint(
        lambda: Sip(self.sipPort),
        local_addr=("0.0.0.0", self.sipPort),
        )

    async def call(self, remoteIP):
        dialog = await self.sipEndpoint.invite(remoteIP, self.sipPort)
        endpoint = None

        if dialog:
            remoteRtpPort, remoteRtcpPort = dialog.getRtpPorts()
            ssrc = Voip.genSSRC()

            loop = asyncio.get_event_loop()
            _, endpoint = await loop.create_datagram_endpoint(
            lambda: RtpEndpoint(ssrc, encrypted=False),
            local_addr=("0.0.0.0", self.rtpPort),
            remote_addr=(remoteIP, remoteRtpPort)
            )

            _, ctrlEndpoint = await loop.create_datagram_endpoint(
                lambda: RtpEndpoint(ssrc, encrypted=False),
                local_addr=('0.0.0.0', self.rtcpPort),
                remote_addr=(remoteIP, remoteRtcpPort)
            )

        self.rtpEndpoint = endpoint
        self.rtcpEndpoint = ctrlEndpoint
        self.activeDialog = dialog

    async def end(self, session):
        # await self.sipEndpoint.bye()
        pass

    async def callReceived(self):
        pass

    def getRTPEndpoint(self):
        return self.rtpEndpoint
    
    def getRTCPEndpoint(self):
        return self.rtcpEndpoint

    @staticmethod
    def genSSRC():
        return int.from_bytes(urandom(4))