from .sipMessage import SipMessage, SipRequest, SipResponse, StatusCodes
from .transaction import Transaction
from .dialog import Dialog

import asyncio
from collections.abc import Callable

class ServerTransaction(Transaction):
    notifyTU: Callable
    sendToTransport: Callable
    request: SipRequest
    localAddress: tuple
    dialog: Dialog

    def __init__(self, notifyTU, sendToTransport, request, localAddress, dialog=None):
        super().__init__(notifyTU, sendToTransport, request.method, localAddress, request.viaAddress, dialog)

        if(self.dialog):
            self.toTag = dialog.remoteTag
        else:
            self.toTag = self._genTag()
        
        self.callID = request.callID
        self.branch = request.viaParams['branch']
        self.fromTag = request.fromParams['tag']
        self.sequence = request.seqNum
        self.request = request
        self.id = self.branch + self.remoteIP + str(self.remotePort)
        Transaction._transactions[self.id] = self

    def buildResponse(self, statusCode):
        viaAddress = (self.remoteIP, self.remotePort)
        viaParams = {'branch': self.branch}
        fromURI = f'<sip:IPCall@{self.remoteIP}:{self.remotePort}>'
        fromParams = {'tag': self.fromTag}
        toURI = f'<sip:{self.localIP}:{self.localPort}>'
        if statusCode == StatusCodes(100, 'Trying'):
            toParams = {}
        else:
            toParams = {'tag': self.toTag}
            
        additionalHeaders = {'Contact': toURI}
        if self.request.method == 'INVITE' and statusCode == StatusCodes.OK:
            body = SipMessage._buildSDP(self.localIP, 5004)
            additionalHeaders['Content-Type'] = 'application/sdp'
        else:
            body = ''
            
        return SipResponse(statusCode, self.request.method, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, self.callID, self.sequence, body, additionalHeaders)

    # TODO handle possible transport error during request
    async def invite(self):
        self.state = 'Proceeding'
        await self.notifyTU(self.request)

        response = self.buildResponse(StatusCodes(100, 'Trying'))
        while response.statusCode.isProvisional():
            self.sendToTransport(response, (self.remoteIP, self.remotePort))
            msg = await self.recvQueue.get()
            if isinstance(msg, SipResponse):
                response = msg

        if response.statusCode.isSuccessful():
            self.sendToTransport(response, (self.remoteIP, self.remotePort))

        elif response.statusCode.isUnsuccessful():
            # TODO
            # If timer H fires while in the "Completed" state, it implies that the
            # ACK was never received.  In this case, the server transaction MUST
            # transition to the "Terminated" state, and MUST indicate to the TU
            # that a transaction failure has occurred.
            self.state = 'Completed'
            transactionTimeout = 64 * Transaction.T1
            async with asyncio.timeout(transactionTimeout):
                msg = None
                attempts = 0
                while not isinstance(msg, SipRequest) or msg.method != 'ACK':
                    self.sendToTransport(response, (self.remoteIP, self.remotePort))

                    retransmitInterval = (pow(2, attempts) * Transaction.T1)
                    retransmitInterval = min(Transaction.T2, retransmitInterval)

                    try:
                        async with asyncio.timeout(retransmitInterval):
                            while not isinstance(msg, SipRequest):
                                msg = await self.recvQueue.get()
                    except TimeoutError:
                        attempts += 1

            # Keep transaction alive to absorb ACK messages from final response retransmissions
            self.state = 'Confirmed'
            asyncio.sleep(Transaction.T4)

        # TODO The remote target MUST be set to the URI from the Contact header field of the request.
        # remoteTarget = None
        # self.dialog = Dialog(self.callID, self.toTag, "sip:IPCall@{}:{}".format(self.localIP, self.localPort), 0, self.fromTag, "sip:{}:{}".format(self.remoteIP, self.remotePort), remoteTarget, self.sequence)
        self.terminate()

        return self.dialog
        
    async def nonInvite(self):
        self.state = 'Trying'
        await self.notifyTU(self.request)

        response = None
        while not response:
            msg = await self.recvQueue.get()
            if isinstance(msg, SipResponse):
                response = msg
                self.sendToTransport(response, (self.remoteIP, self.remotePort))

        if response.statusCode.isProvisional():        
            self.state = 'Proceeding'
            while response.statusCode.isProvisional():
                msg = await self.recvQueue.get()
                if isinstance(msg, SipResponse):
                    response = msg
                
                self.sendToTransport(response, (self.remoteIP, self.remotePort))

        self.state = 'Completed'
        retransmissionTimeout = 64 * Transaction.T1
        try:
            async with asyncio.timeout(retransmissionTimeout):
                while True:
                    msg = await self.recvQueue.get()
                    if isinstance(msg, SipRequest):
                        self.sendToTransport(response, (self.remoteIP, self.remotePort))
        except TimeoutError:
            pass
        
        # if self.request.method == 'BYE':
        #     self.dialog.terminate()

        self.terminate()