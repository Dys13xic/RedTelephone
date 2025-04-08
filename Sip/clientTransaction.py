from .sipMessage import SipMessage, SipRequest, SipResponse
from .transaction import Transaction
from .dialog import Dialog

import asyncio
import time
import random
import hashlib

class ClientTransaction(Transaction):
    receivedProvisional: asyncio.Event

    def __init__(self, notifyTU, sendToTransport, requestMethod, localAddress, remoteAddress, dialog=None):
        super().__init__(notifyTU, sendToTransport, requestMethod, localAddress, remoteAddress, dialog)
        
        if(self.dialog):
            self.fromTag = dialog.localTag
            self.toTag = dialog.remoteTag
            self.callID = dialog.callID

            # TODO update dialog settings after request sent
            if self.requestMethod == "ACK":
                self.sequence = dialog.localSeq
            else:
                self.sequence = dialog.localSeq + 1
        
        else:
            self.fromTag = self._genTag()
            self.toTag = ""
            self.callID = self._genCallID()
            self.sequence = 1

        self.branch = self._genBranch()
        self.id = self.branch + self.requestMethod
        self.receivedProvisional = asyncio.Event()
        Transaction._transactions[self.id] = self

    def cancelFromInvite(self):
        if self.requestMethod != 'INVITE':
            raise ValueError
        
        cancel = ClientTransaction(self.notifyTU, self.sendToTransport, 'CANCEL', (self.localIP, self.localPort), (self.remoteIP, self.remotePort), dialog=None)
        del Transaction._transactions[cancel.id]

        cancel.branch = self.branch
        cancel.fromTag = self.fromTag
        cancel.toTag = self.toTag
        cancel.callID = self.callID
        cancel.sequence = self.sequence
        cancel.id = cancel.branch + cancel.requestMethod
        cancel.receivedProvisional = asyncio.Event()
        Transaction._transactions[cancel.id] = cancel
        return cancel

    def buildRequest(self, method):
        targetAddress = (self.remoteIP, self.remotePort)
        viaAddress = (self.localIP, self.localPort)
        viaParams = {'branch': self.branch}
        fromURI = f'<sip:IPCall@{self.localIP}:{self.localPort}>'
        fromParams = {'tag': self.fromTag}
        toURI = f'<sip:{self.remoteIP}:{self.remotePort}>'
        if self.toTag:
            toParams = {'tag': self.toTag}
        else:
            toParams = {}
        additionalHeaders = {'Contact': fromURI, 'Max-Forwards': 70}
        if method == 'INVITE':
            body = SipMessage._buildSDP(self.localIP, 5004)
            additionalHeaders['Content-Type'] = 'application/sdp'
        else:
            body = ''

        return SipRequest(method, targetAddress, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, self.callID, self.sequence, body, additionalHeaders)

    async def invite(self):
        self.dialog = None
        self.state = "Calling"
        request = self.buildRequest("INVITE")

        transactionTimeout = 64 * Transaction.T1
        response = None

        async with asyncio.timeout(transactionTimeout):
            attempts = 0
            while(not response):
                self.sendToTransport(request, (self.remoteIP, self.remotePort))
                retransmitInterval = (pow(2, attempts) * Transaction.T1)

                try:
                    async with asyncio.timeout(retransmitInterval):
                        response = await self.recvQueue.get()
                except TimeoutError:
                    attempts += 1

        # TODO handle possible transport error during request
        if response:

            if response.statusCode.isProvisional():
                self.state = "Proceeding"
                self.receivedProvisional.set()
                # Await non-Provisional response
                while response.statusCode.isProvisional():
                    await self.notifyTU(response)
                    response = await self.recvQueue.get()

            if response.statusCode.isSuccessful():
                await self.notifyTU(response)
                rtpPort, rtcpPort = SipMessage._parseSDP(response.body)
                self.dialog = Dialog(self.callID, self.fromTag, "sip:IPCall@{}:{}".format(self.localIP, self.localPort), self.sequence, response.toParams['tag'], "sip:{}:{}".format(self.remoteIP, self.remotePort), response.additionalHeaders['Contact'].strip('<>'), rtpPort=rtpPort, rtcpPort=rtcpPort)

                # Ack in seperate transaction
                newTransaction = ClientTransaction(self.notifyTU, self.sendToTransport, "ACK", (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.dialog)
                newTransaction.ack(autoClean=True)
                self.terminate()

            elif response.statusCode.isUnsuccessful():
                self.state = "Completed"
                await self.notifyTU(response)
                self.ack()
                # Answer duplicate final responses for 32 seconds before terminating transaction
                asyncio.create_task(self._handleRetransmissions(duration=Transaction.ANSWER_DUPLICATES_DURATION))

            else:
                # Invalid response code TODO generate a malformed request response? *Note: could also do this at a lower level.
                print("Invalid response code")
                self.terminate()
                exit()

        return self.dialog

    async def nonInvite(self, method):
        # TODO Ensure dialog established (Except for Cancel)
        # if not self.dialog:
        #     print("No dialog")
        #     exit()
        self.state = "Trying"
        request = self.buildRequest(method)

        transactionTimeout = 64 * Transaction.T1
        response = None

        async with asyncio.timeout(transactionTimeout):
            attempts = 0
            while(not response or response.statusCode.isProvisional()):
                self.sendToTransport(request, (self.remoteIP, self.remotePort))

                retransmitInterval = (pow(2, attempts) * Transaction.T1)
                retransmitInterval = min(Transaction.T2, retransmitInterval)

                try:
                    async with asyncio.timeout(retransmitInterval):
                        response = await self.recvQueue.get()
                        if response.statusCode.isProvisional():
                            self.state = 'Proceeding'
                            await self.notifyTU(response)
                except TimeoutError:
                    attempts += 1

        # TODO handle possible transport error during request
        if response:
            if response.statusCode.isFinal():
                self.state = 'Completed'
                await self.notifyTU(response)
                # Buffer response retransmissions
                asyncio.create_task(self._handleRetransmissions(duration=Transaction.T4))

    # TODO why is autoclean necessary again? Is there a better way to handle this?
    def ack(self, autoClean=False):
        request = self.buildRequest("ACK")
        self.sendToTransport(request, (self.remoteIP, self.remotePort))

        if autoClean:
            self.terminate()

    async def _handleRetransmissions(self, duration):
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
        return hex(time.time_ns())[2:] + hex(int(random.getrandbits(32)))[2:]
    
    def _genBranch(self):
        return Transaction.BRANCH_MAGIC_COOKIE + hashlib.md5((self.toTag + self.fromTag + self.callID + "SIP/2.0/UDP {}:{};".format(self.localIP, self.localPort) + str(self.sequence)).encode()).hexdigest()
