# 1st Party
from Sip.sip import Sip
from Sip.sipMessage import SipRequest, SipResponse, StatusCodes
from Sip.transaction import Transaction
from Sip.dialog import Dialog
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
    activeDialog: Dialog 
    sessionStarted: asyncio.Event
    eventHandler: EventHandler
    recvQueue: asyncio.Queue


    def __init__(self, sipPort, rtpPort, rtcpPort):
        self.sipPort = sipPort
        self.rtpPort = rtpPort

        if rtcpPort:
            self.rtcpPort = rtcpPort
        else:
            self.rtcpPort = rtpPort + 1

        self.eventHandler = EventHandler()

        self.recvQueue = asyncio.Queue()
        self.sipEndpoint = Sip(self.recvQueue, sipPort)
        self.rtpEndpoint = None
        self.rtcpEndpoint = None
        self.activeDialog = None
        self.sessionStarted = asyncio.Event()

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
        await asyncio.gather(self.sipEndpoint.run(), self.manageSip())

    async def manageSip(self):
        while True:
            msg = await self.recvQueue.get()
            asyncio.create_task(self.processMsg(msg))

    # TODO Implement behaviour for not accepting every call, i.e. 300 - 699 responses
    async def processMsg(self, msg):
        
        if isinstance(msg, SipRequest):
            transactionID = msg.getTransactionID()
            transaction = Transaction.getTransaction(transactionID)

            match msg.method:
                case 'INVITE':
                    # TODO determine if an existing call is in progress and if so send a Busy Here response

                    response = transaction.buildResponse(StatusCodes(180, 'Ringing'))
                    await transaction.recvQueue.put(response)

                    # TODO await an event/signal that secret key has been received
                    response = transaction.buildResponse(StatusCodes(200, 'OK'))

                    # TODO create a function for automatically building a Dialog from a function
                    remoteTarget = msg.additionalHeaders['Contact']
                    transaction.dialog = Dialog(transaction.callID, transaction.toTag, "sip:IPCall@{}:{}".format(transaction.localIP, transaction.localPort), 0, transaction.fromTag, "sip:{}:{}".format(transaction.remoteIP, transaction.remotePort), remoteTarget, transaction.sequence)

                    await transaction.recvQueue.put(response)
                    await self.buildSession(transaction.dialog)

                    # Call relevant event handler
                    await self.eventHandler.dispatch('inbound_call_accepted')

                case 'BYE':
                    response = transaction.buildResponse(StatusCodes(200, 'OK'))
                    await transaction.recvQueue.put(response)
                    
                    transaction.dialog.terminate()
                    self.cleanup()
                    await self.eventHandler.dispatch('inbound_call_ended')

                case 'CANCEL':
                    raise NotImplementedError
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

        elif isinstance(msg, Exception):
            raise msg

        else:
            print('Unsupported message type')

    async def call(self, remoteIP):
        dialog = await self.sipEndpoint.invite(remoteIP, self.sipPort)
        await self.buildSession(dialog)

    async def endCall(self):
        await self.sipEndpoint.bye(self.activeDialog)
        self.cleanup()

    async def buildSession(self, dialog):
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

    def cleanup(self):
        self.rtpEndpoint.stop()
        self.rtcpEndpoint.stop()

        self.activeDialog = None
        self.rtpEndpoint, self.rtcpEndpoint = None, None

        self.sessionStarted.clear()

    @staticmethod
    def genSSRC():
        return int.from_bytes(urandom(4))