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


TRANSACTION_USER_TIMEOUT = 20

class Voip():
    sipPort: int
    rtpPort: int
    rtcpPort: int
    sip: Sip
    rtpEndpoint: RtpEndpoint
    rtcpEndpoint: RtpEndpoint
    activeInvite: Transaction
    activeDialog: Dialog 
    answerCall: asyncio.Event
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
        self.activeInvite = None
        self.activeDialog = None
        self.answerCall = asyncio.Event()
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

    async def processMsg(self, msg):
        transactionID = msg.getTransactionID()
        transaction = Transaction.getTransaction(transactionID)

        if isinstance(msg, SipRequest):
            match msg.method:
                case 'INVITE':
                    if self.activeDialog:
                        response = transaction.buildResponse(StatusCodes(486, 'Busy Here'))
                        await transaction.recvQueue.put(response)
                    else:
                        response = transaction.buildResponse(StatusCodes(180, 'Ringing'))
                        await transaction.recvQueue.put(response)

                        # Call relevant event handler
                        await self.eventHandler.dispatch('inbound_call')

                        # Await an event signalling call has been answered
                        async with asyncio.timeout(TRANSACTION_USER_TIMEOUT):
                            try:
                                await self.answerCall.wait()
                                self.answerCall.clear()
                            except TimeoutError:
                                response = transaction.buildResponse(StatusCodes(504, 'Server Time-out'))
                                transaction.recvQueue.put(response)
                                return
                            
                        response = transaction.buildResponse(StatusCodes(200, 'OK'))

                        # TODO create a function for automatically building a Dialog from a transaction?
                        remoteTarget = msg.additionalHeaders['Contact']
                        transaction.dialog = Dialog(transaction.callID, transaction.toTag, f"sip:IPCall@{transaction.localIP}:{transaction.localPort}", 0, transaction.fromTag, f"sip:{transaction.remoteIP}:{transaction.remotePort}", remoteTarget, transaction.sequence)

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
                    inviteTransactionID = transactionID.replace('CANCEL', 'INVITE', 1)
                    inviteTransaction = Transaction.getTransaction(inviteTransactionID)

                    if inviteTransaction:
                        response = transaction.buildResponse(StatusCodes(200, 'OK'))
                        await transaction.recvQueue.put(response)

                        response = inviteTransaction.buildResponse(StatusCodes(487, 'Request Terminated'))
                        await inviteTransaction.recvQueue.put(response)

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
        #TODO raise an exception on call failure?
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