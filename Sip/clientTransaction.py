# 1st Party
from .sipMessage import SipMessage, SipRequest
from .transaction import Transaction, States

# Standard Library
import asyncio
import time
import random
import hashlib

class ClientTransaction(Transaction):
    """Manage the state of a SIP request across many independent messages."""
    def __init__(self, notifyTU, sendToTransport, requestMethod, localAddress, remoteAddress, dialog=None, overrideTransaction=None):
        super().__init__(notifyTU, sendToTransport, requestMethod, localAddress, remoteAddress, dialog)
        
        if(self.dialog):
            # Get header values from existing dialog
            self.fromTag = self.dialog.localTag
            self.toTag = self.dialog.remoteTag
            self.callID = self.dialog.callID
            # Increment dialog sequence number
            if self.requestMethod != "ACK":
                self.dialog.localSeq += 1
            self.sequence = self.dialog.localSeq
        else:
            # Generate new header values
            self.fromTag = self._genTag()
            self.toTag = ""
            self.callID = self._genCallID()
            self.sequence = 1
        
        self.branch = self._genBranch()
        self.receivedProvisional: asyncio.Event = asyncio.Event()

        # If included, override properties with those of an existing transaction (used for cancelling invites)
        if overrideTransaction:
            self.branch = overrideTransaction.branch
            self.fromTag = overrideTransaction.fromTag                                                                                                              
            self.toTag = overrideTransaction.toTag
            self.callID = overrideTransaction.callID
            self.sequence = overrideTransaction.sequence

        # Register new transaction
        self.id = self.branch + self.requestMethod
        Transaction._transactions[self.id] = self

    def cancelFromInvite(self):
        """Construct a cancel transaction from an existing invite transaction."""
        if self.requestMethod != 'INVITE':
            raise ValueError('Non-Invite transaction.')
        
        return ClientTransaction(self.notifyTU, self.sendToTransport, 'CANCEL', (self.localIP, self.localPort), (self.remoteIP, self.remotePort), dialog=None, overrideTransaction=self)

    def buildRequest(self, method):
        """Build a SIP request of the specified method."""
        # Configure mandatory headers
        targetAddress = (self.remoteIP, self.remotePort)
        viaAddress = (self.localIP, self.localPort)
        fromURI = f'<sip:IPCall@{self.localIP}:{self.localPort}>'
        toURI = f'<sip:{self.remoteIP}:{self.remotePort}>'

        # Configure header parameters
        viaParams = {'branch': self.branch}
        fromParams = {'tag': self.fromTag}
        if self.toTag:
            toParams = {'tag': self.toTag}
        else:
            toParams = {}

        # Configure non-mandatory headers
        additionalHeaders = {'Contact': fromURI, 'Max-Forwards': 70}

        # Configure message body
        if method == 'INVITE':
            additionalHeaders['Content-Type'] = 'application/sdp'
            # TODO replace magic numbers
            body = SipMessage._buildSDP(self.localIP, 5004)
        else:
            body = ''

        return SipRequest(method, targetAddress, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, self.callID, self.sequence, body, additionalHeaders)

    async def invite(self):
        """Manage a SIP invite request."""
        self.dialog = None
        self.state = States.CALLING
        request = self.buildRequest("INVITE")
        transactionTimeout = 64 * Transaction.T1
        response = None

        try:
            # Send request with exponential back-off until a response is received or transaction timeout reached.
            async with asyncio.timeout(transactionTimeout):
                attempts = 0
                while(not response):
                    # Send/resend request
                    self.sendToTransport(request, (self.remoteIP, self.remotePort))
                    retransmitInterval = (pow(2, attempts) * Transaction.T1)
                    try:
                        # Wait (up to) the retransmit interval duration for a response before re-attempting
                        async with asyncio.timeout(retransmitInterval):
                            response = await self.recvQueue.get()
                    except TimeoutError:
                        attempts += 1

            # Await a non-Provisional response
            if response.statusCode.isProvisional():
                self.state = States.PROCEEDING
                self.receivedProvisional.set()
                while response.statusCode.isProvisional():
                    await self.notifyTU(response)
                    response = await self.recvQueue.get()

            if response.statusCode.isSuccessful():
                await self.notifyTU(response)
                self.terminate()
            elif response.statusCode.isUnsuccessful():
                self.state = States.COMPLETED
                await self.notifyTU(response)
                self.ack()
                # Acknowledge duplicate final responses for duration before terminating transaction
                asyncio.create_task(self._handleRetransmissions(duration=Transaction.ANSWER_DUPLICATES_DURATION))
            else:
                raise ValueError('Invalid SIP response code')

        except (ConnectionError, TimeoutError, ValueError) as e:
            # Pass exceptions to the Transaction User and terminate the transaction
            self.notifyTU(e)
            self.terminate()

        return self.dialog

    async def nonInvite(self, method):
        """Manage a SIP non-invite request."""
        if not self.dialog and method != 'Cancel':
            raise ValueError('Missing dialog.')

        self.state = States.TRYING
        request = self.buildRequest(method)
        transactionTimeout = 64 * Transaction.T1
        response = None

        try:
            # Send request with exponential back-off until a final response is received or transaction timeout reached.
            async with asyncio.timeout(transactionTimeout):
                attempts = 0
                while(not response or response.statusCode.isProvisional()):
                    # Send/resend request
                    self.sendToTransport(request, (self.remoteIP, self.remotePort))
                    # Cap retransmit interval at T2
                    retransmitInterval = (pow(2, attempts) * Transaction.T1)
                    retransmitInterval = min(Transaction.T2, retransmitInterval)
                    try:
                        # Wait (up to) the retransmit interval duration for a final response before re-attempting
                        async with asyncio.timeout(retransmitInterval):
                            response = await self.recvQueue.get()
                            if response.statusCode.isProvisional():
                                self.state = States.PROCEEDING
                                await self.notifyTU(response)
                    except TimeoutError:
                        attempts += 1

            if response.statusCode.isFinal():
                self.state = States.COMPLETED
                await self.notifyTU(response)
                # Buffer response retransmissions for duration before terminating transaction
                asyncio.create_task(self._handleRetransmissions(duration=Transaction.T4))
            else:
                raise ValueError('Invalid SIP response code')

        except (ConnectionError, TimeoutError, ValueError) as e:
            # Pass exceptions to the Transaction User and terminate the transaction
            self.notifyTU(e)
            self.terminate()

    def ack(self, autoClean=False):
        """Send a SIP ACK message."""
        request = self.buildRequest("ACK")
        self.sendToTransport(request, (self.remoteIP, self.remotePort))
        if autoClean:
            self.terminate()

    async def _handleRetransmissions(self, duration):
        """Acks Invite and absorbs Non-Invite response retransmissions for the specified duration before terminating transaction."""
        try:
            async with asyncio.timeout(duration):
                while(True):
                    response = await self.recvQueue.get()
                    if response.method == 'INVITE':
                        self.ack()
        except:
            raise
        finally:
            self.terminate()

    def _genCallID(self):
        """Generates and returns a suitable SIP Call ID."""
        return hex(time.time_ns())[2:] + hex(int(random.getrandbits(32)))[2:]
    
    def _genBranch(self):
        """Generates and returns a suitable SIP branch parameter."""
        # Calculated in accordance with loop-detection method described in Step 6 of RFC section 16.6
        return Transaction.BRANCH_MAGIC_COOKIE + hashlib.md5((self.toTag + self.fromTag + self.callID + f'SIP/2.0/UDP {self.localIP}:{self.localPort};' + str(self.sequence)).encode()).hexdigest()
