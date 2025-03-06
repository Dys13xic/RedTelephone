# 1st Party
from Sip.sip import Sip
from Sip.sipMessage import SipRequest, SipResponse
from rtp import RtpEndpoint
from events import EventHandler

# Standard Library
import asyncio
from os import urandom


class Voip():

    sipPort: int
    rtpPort: int
    rtcpPort: int
    sip: Sip
    rtpEndpoint: RtpEndpoint
    rtcpEndpoint: RtpEndpoint
    # activeDialog: 
    sessionStarted: asyncio.Event
    eventHandler: EventHandler
    sipEventHandler: EventHandler
    recvQueue: asyncio.Queue


    def __init__(self, sipPort, rtpPort, rtcpPort):
        self.sipPort = sipPort
        self.rtpPort = rtpPort

        if rtcpPort:
            self.rtcpPort = rtcpPort
        else:
            self.rtcpPort = rtpPort + 1

        self.eventHandler = EventHandler()
        self.sipEventHandler = EventHandler()

        self.recvQueue = asyncio.Queue()
        self.sipEndpoint = Sip(self.recvQueue, self.sipEventHandler.dispatch, sipPort)
        self.rtpEndpoint = None
        self.rtcpEndpoint = None
        self.activeDialog = None
        self.sessionStarted = asyncio.Event()
        
        # Register listeners
        self.sipEventHandler.on('inboundCallAccepted', self.inboundCallAccepted)
        self.sipEventHandler.on('inboundCallEnded', self.inboundCallEnded)

    # Register voip events through function decorator
    def event(self, func):
        async def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result
        
        self.eventHandler.on(func.__name__.removeprefix('on_'), wrapper)
        return wrapper
    
    async def run(self):
        await self.sipEndpoint.run()

    async def manageSip(self):
        while True:
            msg = await self.recvQueue.get()
            
            if isinstance(msg, SipRequest):
                match msg.method:
                    case 'INVITE':
                        pass
                    case 'BYE':
                        pass
                    case 'CANCEL':
                        pass
                    case _:
                        print('Unsupported request method')

            elif isinstance(msg, SipResponse):
                match msg.method:
                    case 'INVITE':
                        pass
                    case 'BYE':
                        pass
                    case 'CANCEL':
                        pass
                    case _:
                        print('Unsupported response method')

            else:
                print('Unsupported message type')


    async def call(self, remoteIP):
        dialog = await self.sipEndpoint.invite(remoteIP, self.sipPort)
        endpoint = None

        if dialog:
            remoteRtpPort, remoteRtcpPort = dialog.getRtpPorts()
            if not remoteRtpPort:
                remoteRtpPort = self.rtpPort
            if not remoteRtcpPort:
                remoteRtcpPort = self.rtcpPort

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

            if not remoteRtpPort:
                remoteRtpPort = self.rtpPort
            if not remoteRtcpPort:
                remoteRtcpPort = self.rtcpPort

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
        await self.eventHandler.dispatch('inbound_call_accepted')

    async def inboundCallEnded(self):
        self.cleanup()

        # Call relevant event handler
        await self.eventHandler.dispatch('inbound_call_ended')

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