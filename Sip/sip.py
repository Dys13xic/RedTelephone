# 1st Party Library
from .sipMessage import SipRequest, SipResponse
from .transport import Transport
from .transaction import Transaction, States
from .clientTransaction import ClientTransaction
from .serverTransaction import ServerTransaction
from .dialog import Dialog
from .messageHandler import MessageHandler
from .userAgent import UserAgent

# Standard Library
import asyncio

class Sip(UserAgent):
    def __init__(self, publicAddress):
        self.messageHandler: MessageHandler = MessageHandler(userAgent=self)
        super.__init__(self.transport, publicAddress)

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

            transaction = ServerTransaction(self.notifyTU, self.transport.send, msg, (self.publicIP, self.publicPort), dialog)
            if msg.method == 'INVITE':
                # TODO handle re-invite
                asyncio.create_task(transaction.invite())
            else:
                asyncio.create_task(transaction.nonInvite())

    async def run(self):
        loop = asyncio.get_event_loop()
        _, self.transport = await loop.create_datagram_endpoint(
        lambda: Transport(self.publicIP, handleMsgCallback=self.messageHandler.route),
        local_addr=("0.0.0.0", self.publicPort),
        )
        