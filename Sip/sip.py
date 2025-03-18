# 1st Party Library
from .sipMessage import SipRequest, SipResponse
from .transport import Transport
from .transaction import Transaction
from .clientTransaction import ClientTransaction
from .serverTransaction import ServerTransaction
from .dialog import Dialog

# Standard Library
import asyncio

SIP_PORT = 5060

class Sip():
    transport: Transport
    port: int

    def __init__(self, transactionUserQueue, port=SIP_PORT):
        self.transactionUserQueue = transactionUserQueue
        self.transport = None
        self.port = port

    async def notifyTU(self, msg):
        await self.transactionUserQueue.put(msg)

    async def invite(self, address, port):
        print("Attempting to initiate a call with {}:{}".format(address, port))
        transaction = ClientTransaction(self.notifyTU, self.transport.send, "INVITE", (self.transport.ip, self.port), (address, port))
        dialog = await transaction.invite()
        return dialog

    # TODO implement
    def cancel(self, address, port):
        print("Call cancelled")
        raise NotImplementedError

    async def bye(self, dialog):
        print("Ending call")
        _, remoteIP, remotePort = dialog.remoteTarget.strip('<>').split(':', 2)
        # TODO add proper regex instead of this hack for removing username
        try:
            username, remoteIP = remoteIP.split('@')
        except:
            pass

        remotePort = int(remotePort)

        transaction = ClientTransaction(self.notifyTU, self.transport.send, "BYE", (self.transport.ip, self.port), (remoteIP, remotePort), dialog)
        byeTask = asyncio.create_task(transaction.nonInvite('BYE'))
        await byeTask

    async def handleMsg(self, msg, addr):

        if isinstance(msg, SipResponse):
            # Pass response to matching transaction if one exists
            key = msg.getTransactionID()
            transaction = Transaction.getTransaction(key)
            if transaction:
                await transaction.recvQueue.put(msg)

        elif isinstance(msg, SipRequest):
            # Get matching dialog if one exists
            dialog = None
            if 'tag' in msg.toParams:
                key = msg.callID + msg.toParams['tag'] + msg.fromParams['tag']
                dialog = Dialog.getDialog(key)
            
            # Determine if message belongs to existing transaction
            key = msg.getTransactionID()
            transaction = Transaction.getTransaction(key)
            # TODO fix this so I can remove the 2nd part of "or" statement (maybe change the transaction field to originatingRequestMethod?)
            if transaction and (msg.method == transaction.requestMethod or 
                                                                        (msg.method == 'ACK' and transaction.requestMethod == "INVITE")):
                await transaction.recvQueue.put(msg)
            
            # TODO handle re-invite
            elif msg.method == 'INVITE':
                transaction = ServerTransaction(self.notifyTU, self.transport.send, msg, (self.transport.ip, self.port), dialog=None)
                dialog = await transaction.invite()

            # Ignore orphaned acks
            elif msg.method == 'ACK':
                pass

            elif dialog:
                transaction = ServerTransaction(self.notifyTU, self.transport.send, msg, (self.transport.ip, self.port), dialog)
                asyncio.create_task(transaction.nonInvite())

        else:
            raise Exception('Unsupported message type')

    async def run(self):
        loop = asyncio.get_event_loop()
        _, self.transport = await loop.create_datagram_endpoint(
        lambda: Transport(self.port, handleMsgCallback=self.handleMsg),
        local_addr=("0.0.0.0", self.port),
        )