# 1st Party
from Sip.sip import Sip
from Sip.sipMessage import SipMessage, SipRequest, SipResponse, StatusCodes
from Sip.transaction import Transaction
from Sip.clientTransaction import ClientTransaction
from Sip.dialog import Dialog
from rtp import RtpEndpoint
from Utils.events import EventHandler
from Utils.addressFilter import AddressFilter
from Sip.exceptions import InviteError

# Standard Library
import asyncio
from os import urandom

DEFAULT_SIP_PORT = 5060
DEFAULT_RTP_PORT = 5004
DEFAULT_RTCP_PORT = 5005

TRANSACTION_USER_TIMEOUT = 20

class Voip():
    """Manages the VoIP service."""
    def __init__(self, publicIP, sipPort=DEFAULT_SIP_PORT, rtpPort=DEFAULT_RTP_PORT, rtcpPort=DEFAULT_RTCP_PORT, allowList=[]):
        self.sipPort: int = sipPort
        self.rtpPort: int = rtpPort
        self.rtcpPort: int = rtcpPort or rtpPort + 1
        self.addressFilter: AddressFilter = AddressFilter(allowList)
        self.eventHandler: EventHandler = EventHandler()
        self.recvQueue: asyncio.Queue = asyncio.Queue()
        self.sipEndpoint: Sip = Sip(self.recvQueue, publicIP, self.sipPort)
        self.rtpEndpoint: RtpEndpoint = None
        self.rtcpEndpoint: RtpEndpoint = None
        self.activeInvite: Transaction = None
        self.activeDialog: Dialog = None
        self.remoteRtpPort: int = None
        self.remoteRtcpPort: int = None
        self.answerCall: asyncio.Event = asyncio.Event()
        self.sessionStarted: asyncio.Event = asyncio.Event()
    
    async def run(self):
        """Begin listening for SIP signaling messages and maintain an up-to-date address filter list."""
        await asyncio.gather(self.sipEndpoint.run(), self.manageSip(), self.addressFilter.run())

    async def manageSip(self):
        while True:
            msg = await self.recvQueue.get()
            if isinstance(msg, Exception):
                raise msg
            elif isinstance(msg, SipMessage):
                asyncio.create_task(self.processMsg(msg))
            else:
                pass

    async def processMsg(self, msg):
        transactionID = msg.getTransactionID()
        transaction = Transaction.getTransaction(transactionID)

        if isinstance(msg, SipRequest):
            match msg.method:
                case 'INVITE':
                    viaIP, viaPort = msg.viaAddress
                    
                    if self.activeInvite or self.activeDialog:
                        response = transaction.buildResponse(StatusCodes(486, 'Busy Here'))
                        await transaction.recvQueue.put(response)

                    elif viaIP in self.addressFilter.getAddresses():
                        self.activeInvite = transaction
                        response = transaction.buildResponse(StatusCodes(180, 'Ringing'))
                        await transaction.recvQueue.put(response)

                        # Call relevant event handler
                        await self.eventHandler.dispatch('inbound_call')

                        # Await an event signaling the call has been answered
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

                    else:
                        response = transaction.buildResponse(StatusCodes(403, 'Forbidden'))
                        await transaction.recvQueue.put(response)

                case 'BYE':
                    response = transaction.buildResponse(StatusCodes(200, 'OK'))
                    await transaction.recvQueue.put(response)
                    
                    transaction.dialog.terminate()
                    self.cleanup()
                    await self.eventHandler.dispatch('inbound_call_ended')

                case 'CANCEL':
                    inviteTransactionID = transactionID.replace('CANCEL', 'INVITE')
                    inviteTransaction = Transaction.getTransaction(inviteTransactionID)

                    if inviteTransaction:                      
                        response = transaction.buildResponse(StatusCodes(200, 'OK'))
                        await transaction.recvQueue.put(response)

                        response = inviteTransaction.buildResponse(StatusCodes(487, 'Request Terminated'))
                        await inviteTransaction.recvQueue.put(response)

                        self.cleanup()
                        await self.eventHandler.dispatch('inbound_call_ended')

                case _:
                    print('Unsupported request method')

        elif isinstance(msg, SipResponse):
            match msg.method:
                case 'INVITE':
                    self.activeInvite = transaction
                    if msg.statusCode.isSuccessful():
                        # Create a new dialog
                        transaction.dialog = Dialog(transaction.callID, transaction.fromTag, f'sip:IPCall@{transaction.localIP}:{transaction.localPort}', transaction.sequence, msg.toParams['tag'], f'sip:{transaction.remoteIP}:{transaction.remotePort}', msg.additionalHeaders['Contact'].strip('<>'))
                        # Get media ports from Session Description Protocol
                        self.remoteRtpPort, self.remoteRtcpPort = msg.parseSDP()
                        # TODO this isn't correct w/ respect to the RFC: the UAC Core should handle acking 200 OK directly without creating a new transaction
                        # Review RFC section 13.2.2.4 for more details
                        # Ack in seperate transaction
                        newTransaction = ClientTransaction(self.notifyTU, self.sendToTransport, "ACK", (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.dialog)
                        newTransaction.ack(autoClean=True)

                case 'BYE':
                    transaction.dialog.terminate()
                    self.cleanup()
                case 'CANCEL':
                    self.cleanup()
                case _:
                    print('Unsupported response method')

        elif isinstance(msg, Exception):
            raise msg

        else:
            print('Unsupported message type')

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
        self.activeInvite = None
        self.sessionStarted.set()

    def cleanup(self):
        if self.rtpEndpoint:
            self.rtpEndpoint.stop()
        if self.rtcpEndpoint:
            self.rtcpEndpoint.stop()

        self.activeInvite = None
        self.activeDialog = None
        self.rtpEndpoint, self.rtcpEndpoint = None, None
        self.remoteRtpPort, self.remoteRtcpPort = None, None

        self.answerCall.clear()
        self.sessionStarted.clear()

    @staticmethod
    def genSSRC():
        return int.from_bytes(urandom(4))