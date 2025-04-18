# 1st Party
from .sipMessage import SipMessage, SipRequest, SipResponse, StatusCodes
from .transaction import Transaction, States

# Standard Library
import asyncio

class ServerTransaction(Transaction):
    """Manage the state of a SIP response across many independent messages."""
    def __init__(self, notifyTU, sendToTransport, request, localAddress, dialog=None):
        super().__init__(notifyTU, sendToTransport, request.method, localAddress, request.viaAddress, dialog)

        # Get to tag from existing dialog
        if(self.dialog):
            self.toTag = dialog.remoteTag
        else:
            self.toTag = self._genTag()
        
        # Retrieve values from request
        self.callID = request.callID
        self.branch = request.viaParams['branch']
        self.fromTag = request.fromParams['tag']
        self.sequence = request.seqNum
        self.request: SipRequest = request
        
        # Register new transaction
        self.id = self.branch + self.remoteIP + str(self.remotePort) + self.requestMethod
        Transaction._transactions[self.id] = self

    def buildResponse(self, statusCode):
        """Build a SIP response of the specified status code."""
        # Configure mandatory headers
        viaAddress = (self.remoteIP, self.remotePort)
        fromURI = f'<sip:IPCall@{self.remoteIP}:{self.remotePort}>'
        toURI = f'<sip:{self.localIP}:{self.localPort}>'

        # Configure header parameters
        viaParams = {'branch': self.branch}
        fromParams = {'tag': self.fromTag}
        if statusCode == StatusCodes(100, 'Trying'):
            toParams = {}
        else:
            toParams = {'tag': self.toTag}
            
        # Configure non-mandatory headers
        additionalHeaders = {'Contact': toURI}

        # Configure message body
        if self.request.method == 'INVITE' and statusCode == StatusCodes.OK:
            additionalHeaders['Content-Type'] = 'application/sdp'
            # TODO replace magic numbers
            body = SipMessage._buildSDP(self.localIP, 5004)
        else:
            body = ''
            
        return SipResponse(self.request.method, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, self.callID, self.sequence, body, additionalHeaders, statusCode)

    async def invite(self):
        """Manage response to an Invite Sip request."""
        self.state = States.PROCEEDING
        # Notify transaction user of request and set inital response to "100 Trying" provisional.
        await self.notifyTU(self.request)
        response = self.buildResponse(StatusCodes(100, 'Trying'))

        try:
            # Send provisional responses received from transaction user, on request retransmission send latest provisional response
            while response.statusCode.isProvisional():
                self.sendToTransport(response, (self.remoteIP, self.remotePort))
                msg = await self.recvQueue.get()
                if isinstance(msg, SipResponse):
                    response = msg

            if response.statusCode.isSuccessful():
                self.sendToTransport(response, (self.remoteIP, self.remotePort))
                self.terminate()
            elif response.statusCode.isUnsuccessful():
                self.state = States.COMPLETED
                transactionTimeout = 64 * Transaction.T1

                # Send response with exponential back-off until an acknowledgment is received or transaction timeout reached
                async with asyncio.timeout(transactionTimeout):
                    msg = None
                    attempts = 0
                    while not isinstance(msg, SipRequest) or msg.method != 'ACK':
                        # Send/resend response
                        self.sendToTransport(response, (self.remoteIP, self.remotePort))
                        # Cap retransmit interval at T2
                        retransmitInterval = (pow(2, attempts) * Transaction.T1)
                        retransmitInterval = min(Transaction.T2, retransmitInterval)
                        try:
                            # Wait (up to) the retransmit interval duration for an ACK before re-attempting
                            async with asyncio.timeout(retransmitInterval):
                                while not isinstance(msg, SipRequest):
                                    msg = await self.recvQueue.get()
                        except TimeoutError:
                            attempts += 1

                self.state = States.CONFIRMED
                # Keep transaction alive to absorb ACK messages from final response retransmissions
                asyncio.create_task(self._handleRetransmissions(response=None, duration=Transaction.T4))
            else:
                raise ValueError('Invalid Sip response code.')
            
        except (ConnectionError, TimeoutError) as e:
            # Pass exceptions to the Transaction User and terminate the transaction
            await self.notifyTU(e)
            self.terminate()

        return self.dialog
        
    async def nonInvite(self):
        """Manage response to a Non-Invite Sip request."""
        # Ensure dialog established for Non-Cancel requests
        if not self.dialog and self.requestMethod != 'Cancel':
            raise ValueError('Missing dialog.')
        
        self.state = States.TRYING
        await self.notifyTU(self.request)
        response = None

        try:
            # Send response from TU
            while not response:
                msg = await self.recvQueue.get()
                if isinstance(msg, SipResponse):
                    response = msg
                    self.sendToTransport(response, (self.remoteIP, self.remotePort))

            # If response was provisional, await a final response from TU
            if response.statusCode.isProvisional():        
                self.state = States.PROCEEDING
                while response.statusCode.isProvisional():
                    msg = await self.recvQueue.get()
                    if isinstance(msg, SipResponse):
                        response = msg
                    
                    self.sendToTransport(response, (self.remoteIP, self.remotePort))

            self.state = States.COMPLETED
            # Resend final response on request re-transmission
            retransmissionTimeout = 64 * Transaction.T1
            asyncio.create_task(self._handleRetransmissions(response, duration=retransmissionTimeout))

        except (ConnectionError, TimeoutError, ValueError) as e:
            # Pass exceptions to the Transaction User and termiante the transaction
            await self.notifyTU(e)
            self.terminate()

    async def _handleRetransmissions(self, response, duration):
        """Re-send response on request retransmission and absorb ACK retransmissions for the specified duration before terminating transaction."""
        try:
            async with asyncio.timeout(duration):
                while(True):
                    msg = await self.recvQueue.get()
                    if isinstance(msg, SipRequest) and response:
                        self.sendToTransport(response, (self.remoteIP, self.remotePort))
        except:
            raise
        finally:
            self.terminate()