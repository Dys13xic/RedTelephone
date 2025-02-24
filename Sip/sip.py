# 1st Party Library
from .sipMessage import SipRequest, SipResponse
from .transport import Transport
from .transaction import Transaction
from .clientTransaction import ClientTransaction
from .serverTransaction import ServerTransaction
from .dialog import Dialog
from events import EventHandler

# Standard Library
import asyncio

SIP_PORT = 5060
RTP_PORT = 5004

class Sip():
    eventDispatcher: EventHandler.dispatch
    transport: Transport
    port: int

    def __init__(self, eventDispatcher, port=SIP_PORT):
        self.eventDispatcher = eventDispatcher
        self.transport = None
        self.port = port

    async def invite(self, address, port):
        print("Attempting to intitate a call with {}:{}".format(address, port))
        transaction = ClientTransaction(self.transport.send, "INVITE", (self.transport.ip, self.port), (address, port))
        dialog = await transaction.invite()
        return dialog

    # TODO implement
    # def cancel(self, address, port):
    #     print("Call cancelled")

    async def bye(self, dialog):
        print("Ending call")
        _, remoteIP, remotePort = dialog.remoteTarget.split(':', 2)
        remotePort = int(remotePort)

        transaction = ClientTransaction(self.transport.send, "BYE", (self.transport.ip, self.port), (remoteIP, remotePort), dialog)
        byeTask = asyncio.create_task(transaction.nonInvite('BYE'))
        await byeTask

    async def handleMsg(self, msg, addr):

        if isinstance(msg, SipResponse):
            # Pass response to matching transaction if one exists
            key = msg.branch + msg.seqMethod
            transaction = Transaction.getTransaction(key)
            if transaction:
                await transaction.recvQueue.put(msg)

        # TODO ensure request received is not a duplicate
        elif isinstance(msg, SipRequest):
            # Get matching dialog if one exists
            dialog = None
            if msg.toTag:
                key = msg.callID + msg.toTag + msg.fromTag
                dialog = Dialog.getDialog(key)
            
            # Determine if message belongs to existing transaction
            viaIP, viaPort = msg.viaAddress
            key = msg.branch + viaIP + str(viaPort)
            transaction = Transaction.getTransaction(key)
            # TODO fix this so I can remove the 2nd part of "or" statement (maybe change the transaction field to originatingRequestMethod?)
            if transaction and (msg.method == transaction.requestMethod or 
                                                                        (msg.method == 'ACK' and transaction.requestMethod == "INVITE")):
                await transaction.recvQueue.put(msg)
            
            # TODO handle re-invite
            elif msg.method == 'INVITE':
                transaction = ServerTransaction.fromMessage(self.transport.send, msg, (self.transport.ip, self.port), dialog=None)
                dialog = await transaction.invite()
                await self.eventDispatcher('inboundCallAccepted', dialog)

            # Ignore orphaned acks
            elif msg.method == 'ACK':
                pass

            elif dialog:
                transaction = ServerTransaction.fromMessage(self.transport.send, msg, (self.transport.ip, self.port), dialog)
                await transaction.nonInvite(msg.method)
                if msg.method == 'BYE':
                    await self.eventDispatcher('inboundCallEnded')

        else:
            raise Exception('Unsupported message type')

    async def run(self):
        loop = asyncio.get_event_loop()
        _, self.transport = await loop.create_datagram_endpoint(
        lambda: Transport(self.port, handleMsgCallback=self.handleMsg),
        local_addr=("0.0.0.0", self.port),
        )

async def main():
    loop = asyncio.get_event_loop()
    _, sipEndpoint = await loop.create_datagram_endpoint(
    lambda: Sip(SIP_PORT),
    local_addr=("0.0.0.0", SIP_PORT),
    )
    dialog = await sipEndpoint.call("10.13.0.6", SIP_PORT)
    await asyncio.sleep(3600)
    # await sipEndpoint.end(dialog, "10.13.0.6", SIP_PORT)
    #await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())


#TODO what about implementing an abstract or interface TU class
# Then I can implement or inherit from it and pass and requests for the TU to it for handling.
# It can then call the Voip class instead of SIP doing it directly?