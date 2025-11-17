# 1st Party Library
from .sipMessage import SipRequest, SipResponse, StatusCodes
from .transport import Transport
from .transaction import Transaction, States
from .clientTransaction import ClientTransaction
from .serverTransaction import ServerTransaction
from .dialog import Dialog
from .exceptions import InviteError
from Utils.events import EventHandler
from .sessionManager import SessionManager

# Standard Library
import asyncio

TRANSACTION_USER_TIMEOUT = 20

class UserAgent:
    def __init__(self, transport, publicAddress, sessionManager):
        self.transport: Transport = transport
        self.publicIP: str
        self.publicPort: int
        self.publicIP, self.publicPort = publicAddress
        self.eventHandler: EventHandler = EventHandler()
        self.sessionManager: SessionManager = sessionManager

    async def invite(self, address, port):
        print("Attempting to initiate a call with {}:{}".format(address, port))
        transaction = ClientTransaction(self.notify, self.transport.send, "INVITE", (self.publicIP, self.publicPort), (address, port))
        dialog = await transaction.invite()
        
        if not dialog:
            raise InviteError('Failed to establish a dialog.')
        
        return dialog

    async def cancel(self, inviteTransaction):
        print("Cancelling call.")
        if inviteTransaction.state == States.CALLING:
            transactionTimeout = 64 * Transaction.T1
            try:
                async with asyncio.timeout(transactionTimeout):
                    await inviteTransaction.receivedProvisional.wait()
            except TimeoutError:
                pass

        if inviteTransaction.state == States.PROCEEDING:
            cancelTransaction = inviteTransaction.cancelFromInvite()
            await cancelTransaction.nonInvite('CANCEL')

    async def bye(self, dialog):
        print("Ending call")
        _, remoteIP, remotePort = dialog.remoteTarget.strip('<>').split(':', 2)
        # TODO add proper regex instead of this hack for removing username
        try:
            username, remoteIP = remoteIP.split('@')
        except:
            pass

        remotePort = int(remotePort)

        transaction = ClientTransaction(self.notify, self.transport.send, "BYE", (self.publicIP, self.publicPort), (remoteIP, remotePort), dialog)
        byeTask = asyncio.create_task(transaction.nonInvite('BYE'))
        await byeTask

    async def createTransaction(self, msg):
        dialog = Dialog.getDialog(msg.getDialogID())
        transaction = ServerTransaction(self.notify, self.transport.send, msg, (self.publicIP, self.publicPort), dialog)
        transactionID = transaction.id
        
        if msg.method == 'INVITE':
            await transaction.invite()
        else:
            await transaction.nonInvite()


    async def notify(self, msg):
        transactionID = msg.getTransactionID()
        transaction = Transaction.getTransaction(transactionID)

        if isinstance(msg, SipRequest):
            match msg.method:
                case 'INVITE':
                    viaIP, viaPort = msg.viaAddress
                    
                    if self.sessionManager.busy():
                        response = transaction.buildResponse(StatusCodes(486, 'Busy Here'))
                        await transaction.recvQueue.put(response)

                    elif viaIP in self.sessionManager.addressFilter.getAddresses():
                        self.sessionManager.activeInvite = transaction
                        response = transaction.buildResponse(StatusCodes(180, 'Ringing'))
                        await transaction.recvQueue.put(response)

                        # Call relevant event handler
                        await self.eventHandler.dispatch('inbound_call')

                        # Await an event signaling the call has been answered
                        async with asyncio.timeout(TRANSACTION_USER_TIMEOUT):
                            try:
                                await self.sessionManager.waitForAnswer()
                            except TimeoutError:
                                response = transaction.buildResponse(StatusCodes(504, 'Server Time-out'))
                                transaction.recvQueue.put(response)
                                return
                            
                        response = transaction.buildResponse(StatusCodes(200, 'OK'))

                        # TODO create a function for automatically building a Dialog from a transaction?
                        remoteTarget = msg.additionalHeaders['Contact']
                        transaction.dialog = Dialog(transaction.callID, transaction.toTag, f"sip:IPCall@{transaction.localIP}:{transaction.localPort}", 0, transaction.fromTag, f"sip:{transaction.remoteIP}:{transaction.remotePort}", remoteTarget, transaction.sequence)

                        await transaction.recvQueue.put(response)
                        await self.sessionManager.buildSession(transaction.dialog)

                        # Call relevant event handler
                        await self.eventHandler.dispatch('inbound_call_accepted')

                    else:
                        response = transaction.buildResponse(StatusCodes(403, 'Forbidden'))
                        await transaction.recvQueue.put(response)

                case 'BYE':
                    response = transaction.buildResponse(StatusCodes(200, 'OK'))
                    await transaction.recvQueue.put(response)
                    
                    transaction.dialog.terminate()
                    self.sessionManager.cleanup()
                    await self.eventHandler.dispatch('inbound_call_ended')

                case 'CANCEL':
                    inviteTransactionID = transactionID.replace('CANCEL', 'INVITE')
                    inviteTransaction = Transaction.getTransaction(inviteTransactionID)

                    if inviteTransaction:                      
                        response = transaction.buildResponse(StatusCodes(200, 'OK'))
                        await transaction.recvQueue.put(response)

                        response = inviteTransaction.buildResponse(StatusCodes(487, 'Request Terminated'))
                        await inviteTransaction.recvQueue.put(response)

                        self.sessionManager.cleanup()
                        await self.eventHandler.dispatch('inbound_call_ended')

                case 'ACK':
                    pass

                case _:
                    print('Unsupported request method')

        elif isinstance(msg, SipResponse):
            match msg.method:
                case 'INVITE':
                    self.sessionManager.activeInvite = transaction
                    if msg.statusCode.isSuccessful():
                        # Create a new dialog
                        transaction.dialog = Dialog(msg.callID, msg.fromParams['tag'], msg.fromURI, msg.seqNum, msg.toParams['tag'], msg.toURI, msg.additionalHeaders['Contact'].strip('<>'))
                        # Get media ports from Session Description Protocol
                        self.remoteRtpPort, self.remoteRtcpPort = msg.parseSDP()
                        # Ack response
                        ack = SipRequest.ackFromResponse(msg)
                        self.transport.send(ack, ack.targetAddress)

                case 'BYE':
                    transaction.dialog.terminate()
                    self.sessionManager.cleanup()
                case 'CANCEL':
                    pass
                    self.sessionManager.cleanup()
                case _:
                    print('Unsupported response method')

        elif isinstance(msg, Exception):
            raise msg

        else:
            print('Unsupported message type')