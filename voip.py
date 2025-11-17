# 1st Party
from Sip.sip import Sip
from Sip.transaction import Transaction
from Sip.dialog import Dialog
from rtp import RtpEndpoint
from Utils.addressFilter import AddressFilter
from Sip.exceptions import InviteError
from Sip.sessionManager import SessionManager

# Standard Library
import asyncio
from os import urandom

DEFAULT_SIP_PORT = 5060
DEFAULT_RTP_PORT = 5004
DEFAULT_RTCP_PORT = 5005

class Voip(SessionManager):
    """Manages the VoIP service."""
    def __init__(self, publicIP, sipPort=DEFAULT_SIP_PORT, rtpPort=DEFAULT_RTP_PORT, rtcpPort=DEFAULT_RTCP_PORT, allowList=[]):
        super().__init__()
        self.sipPort: int = sipPort
        self.rtpPort: int = rtpPort
        self.rtcpPort: int = rtcpPort or rtpPort + 1
        self.remoteRtpPort: int = None
        self.remoteRtcpPort: int = None
        self.addressFilter: AddressFilter = AddressFilter(allowList)
        self.sipEndpoint: Sip = Sip((publicIP, self.sipPort), self)
        self.rtpEndpoint: RtpEndpoint = None
        self.rtcpEndpoint: RtpEndpoint = None
    
    async def run(self):
        await asyncio.gather(self.sipEndpoint.run(), self.addressFilter.run())
    
    async def call(self, remoteIP):
        try:
            dialog = await self.sipEndpoint.invite(remoteIP, self.sipPort)
        except InviteError:
            raise

        await self.buildSession(dialog)

    # TODO possibllity of a race condition where a Dialog is created after the if statement and cleanup causes issues?
    async def endCall(self):
        if self.activeDialog:
            await self.sipEndpoint.bye(self.activeDialog)
        elif self.activeInvite:
            await self.sipEndpoint.cancel(self.activeInvite)

    async def buildSession(self, dialog):
        remoteIP = dialog.getRemoteIP()
        remoteRtpPort = self.remoteRtpPort or self.rtpPort
        remoteRtcpPort = self.remoteRtcpPort or self.rtcpPort
        ssrc = Voip.genSSRC()

        loop = asyncio.get_event_loop()
        _, self.rtpEndpoint = await loop.create_datagram_endpoint(
        lambda: RtpEndpoint(ssrc, encrypted=False),
        local_addr=("0.0.0.0", self.rtpPort),
        remote_addr=(remoteIP, remoteRtpPort)
        )

        _, self.rtcpEndpoint = await loop.create_datagram_endpoint(
            lambda: RtpEndpoint(ssrc, encrypted=False),
            local_addr=('0.0.0.0', self.rtcpPort),
            remote_addr=(remoteIP, remoteRtcpPort)
            )

        self.activeDialog = dialog
        self.activeInvite = None
        self.sessionStart.set()

    def cleanup(self):
        super().cleanup()

        if self.rtpEndpoint:
            self.rtpEndpoint.stop()
        if self.rtcpEndpoint:
            self.rtcpEndpoint.stop()

        self.rtpEndpoint, self.rtcpEndpoint = None, None
        self.remoteRtpPort, self.remoteRtcpPort = None, None

    @staticmethod
    def genSSRC():
        return int.from_bytes(urandom(4))