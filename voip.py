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
        self.rtpEndpoint = None
        self.rtcpEndpoint = None
        self.activeDialog = None
        self._eventListeners = {}
        self.sessionStarted = asyncio.Event()

    def event(self, func):
        self._eventListeners[func.__name__] = func
    
    async def run(self):
        loop = asyncio.get_event_loop()
        _, self.sipEndpoint = await loop.create_datagram_endpoint(
        lambda: Sip(port=self.sipPort, inviteReceivedCallback=self.inboundCallAccepted, byeReceivedCallback=self.inboundCallEnded),
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
        # TODO why are these outside the if statement, and what happens if the call times out?
        self.rtpEndpoint = endpoint
        self.rtcpEndpoint = ctrlEndpoint
        self.activeDialog = dialog
        self.sessionStarted.set()

    async def endCall(self):
        await self.sipEndpoint.bye(self.activeDialog)
        self._cleanup()

    async def inboundCallAccepted(self, dialog):
        endpoint = None

        if dialog:
            remoteIP = dialog.getRemoteIP()
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

        # TODO why are these outside the if statement, and what happens if the call times out?
        self.rtpEndpoint = endpoint
        self.rtcpEndpoint = ctrlEndpoint
        self.activeDialog = dialog
        self.sessionStarted.set()

        # Call relevant event handler
        if 'inbound_call_accepted' in self._eventListeners.keys():
            await self._eventListeners['inbound_call_accepted']()

    async def inboundCallEnded(self):
        self.cleanup()

        # Call relevant event handler
        if 'inbound_call_ended' in self._eventListeners.keys():
            await self._eventListeners['inbound_call_ended']()

    def cleanup(self):
        self.rtpEndpoint.stop()
        self.rtcpEndpoint.stop()

        self.activeDialog = None
        self.rtpEndpoint, self.rtcpEndpoint = None, None

        self.sessionStarted.clear()

    def getRTPEndpoint(self):
        return self.rtpEndpoint
    
    def getRTCPEndpoint(self):
        return self.rtcpEndpoint
    
    def getSessionStarted(self):
        return self.sessionStarted

    @staticmethod
    def genSSRC():
        return int.from_bytes(urandom(4))