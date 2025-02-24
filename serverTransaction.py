from sipMessage import SipMessage
from transaction import Transaction
from dialog import Dialog

import asyncio

class ServerTransaction(Transaction):
    def __init__(self, sendToTransport, requestMethod, localAddress, remoteAddress, callID, branch, fromTag, sequence, dialog=None):
        super().__init__(sendToTransport, requestMethod, localAddress, remoteAddress, dialog)

        if(self.dialog):
            self.toTag = dialog.remoteTag
        else:
            self.toTag = self._genTag()
        
        self.callID = callID
        self.branch = branch
        self.fromTag = fromTag
        self.sequence = sequence
        self.id = self.branch + self.remoteIP + str(self.remotePort)
        Transaction._transactions[self.id] = self

    @classmethod
    def fromMessage(cls, sendToTransport, message, localAddress, dialog):
        return cls(sendToTransport, message.method, localAddress, message.viaAddress, message.callID, message.branch, message.fromTag, 
                   message.seqNum, dialog)

    def buildResponse(self, status):
        messageBody = ""

        if status == "200 OK":
            # TODO add parameter for specifiying RTP port
            messageBody = SipMessage._buildSDP(self.localIP, 5004)

        return SipMessage._buildMessage(status, (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.branch, self.callID, self.sequence, self.requestMethod, self.fromTag, self.toTag, messageBody)

    async def invite(self):
        self.state = 'Proceeding'
        response = self.buildResponse('100 Trying')
        self.sendToTransport(response, (self.remoteIP, self.remotePort))

        response = self.buildResponse('180 Ringing')
        self.sendToTransport(response, (self.remoteIP, self.remotePort))

        # TODO replace condition to implement behaviour for not accepting every call, i.e. 300 - 699 responses
        if True:
            # TODO, keep phone ringing until secret received?
            response = self.buildResponse('200 OK')
            self.sendToTransport(response, (self.remoteIP, self.remotePort))
        else:
            response = self.buildResponse('486 Busy Here')
            self.state = 'Completed'

            transactionTimeout = 64 * T1
            request = None

            # TODO
            # while in the "Completed" state, if a request retransmission is
            # received, the server SHOULD pass the response to the transport for
            # retransmission.

            # TODO handle possible timeout
            # If timer H fires while in the "Completed" state, it implies that the
            #    ACK was never received.  In this case, the server transaction MUST
            #    transition to the "Terminated" state, and MUST indicate to the TU
            #    that a transaction failure has occurred.
            async with asyncio.timeout(transactionTimeout):
                attempts = 0
                while(not request or request.method != 'ACK'):
                    self.sendToTransport(response, (self.remoteIP, self.remotePort))

                    retransmitInterval = (pow(2, attempts) * T1)
                    retransmitInterval = min(T2, retransmitInterval)

                    try:
                        async with asyncio.timeout(retransmitInterval):
                            request = await self.recvQueue.get()
                            # TODO does this state update provide any value?
                            if request.method == 'ACK':
                                self.state = 'Confirmed'
                    except TimeoutError:
                        attempts += 1

            # TODO handle possible transport error during request

            if request:
                if 300 <= response.statusCode <= 699:
                    self.state = 'Completed'
                    # Buffer response retransmissions
                    try:
                        async with asyncio.timeout(T4):
                            while(True):
                                response = await self.recvQueue.get()
                    except TimeoutError:
                        pass

        

        # TODO The remote target MUST be set to the URI from the Contact header field of the request.
        remoteTarget = None

        self.dialog = Dialog(self.callID, self.toTag, "sip:IPCall@{}:{}".format(self.localIP, self.localPort), 0, self.fromTag, "sip:{}:{}".format(self.remoteIP, self.remotePort), remoteTarget, self.sequence)
        self.terminate()

        return self.dialog
        
    async def nonInvite(self, method):
        self.state = 'Proceeding'

        if method == 'BYE':
            response = self.buildResponse('200 OK')
            self.dialog.terminate()
        else:
            # TODO implement additional requests
            print('Unsupported Request')

        
    async def ack(self):
        pass