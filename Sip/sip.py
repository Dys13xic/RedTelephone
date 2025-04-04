# 1st Party Library
from .sipMessage import SipRequest, SipResponse
from .transport import Transport
from .transaction import Transaction
from .clientTransaction import ClientTransaction
from .serverTransaction import ServerTransaction
from .dialog import Dialog
from exceptions import InviteError

# Standard Library
import asyncio


class Sip():
    transactionUserQueue: asyncio.Queue
    transport: Transport
    publicIP: str
    port: int

    def __init__(self, transactionUserQueue, publicIP, port):
        self.transactionUserQueue = transactionUserQueue
        self.transport = None
        self.publicIP = publicIP
        self.port = port

    async def notifyTU(self, msg):
        await self.transactionUserQueue.put(msg)

    async def invite(self, address, port):
        print("Attempting to initiate a call with {}:{}".format(address, port))
        transaction = ClientTransaction(self.notifyTU, self.transport.send, "INVITE", (self.transport.ip, self.port), (address, port))
        dialog = await transaction.invite()
        
        if not dialog:
            raise InviteError('Failed to establish a dialog.')
        
        return dialog

    async def cancel(self, transaction):
        print("Cancelling call.")
        # TODO create a transaction w/ matching
        if transaction.state == 'Calling':
            transactionTimeout = 64 * Transaction.T1
            try:
                async with asyncio.timeout(transactionTimeout):
                    await transaction.receivedProvisional.wait()
            except TimeoutError:
                pass

        if self.state == 'Proceeding':
            cancelTransaction = ClientTransaction()
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

        transaction = ClientTransaction(self.notifyTU, self.transport.send, "BYE", (self.transport.ip, self.port), (remoteIP, remotePort), dialog)
        byeTask = asyncio.create_task(transaction.nonInvite('BYE'))
        await byeTask

    async def handleMsg(self, msg, addr):
        # Pass message to matching transaction if one exists
        key = msg.getTransactionID()
        transaction = Transaction.getTransaction(key)
        if transaction:
            await transaction.recvQueue.put(msg)

        elif isinstance(msg, SipRequest):
            # Ignore orphaned acks
            if msg.method == 'ACK':
                pass
        
            # Get matching dialog if one exists
            dialog = None
            if 'tag' in msg.toParams:
                key = msg.callID + msg.toParams['tag'] + msg.fromParams['tag']
                dialog = Dialog.getDialog(key)

            transaction = ServerTransaction(self.notifyTU, self.transport.send, msg, (self.transport.ip, self.port), dialog)
            if msg.method == 'INVITE':
                # TODO handle re-invite
                asyncio.create_task(transaction.invite())
            else:
                asyncio.create_task(transaction.nonInvite())

    async def run(self):
        loop = asyncio.get_event_loop()
        _, self.transport = await loop.create_datagram_endpoint(
        lambda: Transport(self.publicIP, self.port, handleMsgCallback=self.handleMsg),
        local_addr=("0.0.0.0", self.port),
        )