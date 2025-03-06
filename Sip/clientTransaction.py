from .sipMessage import SipMessage
from .transaction import Transaction
from .dialog import Dialog

import asyncio
import time
import random
import hashlib

class ClientTransaction(Transaction):
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
                self.sequence = dialog.locaSeq + 1
        
        else:
            self.fromTag = self._genTag()
            self.toTag = ""
            self.callID = self._genCallID()
            self.sequence = 1

        self.branch = self._genBranch()
        self.id = self.branch + self.requestMethod
        Transaction._transactions[self.id] = self

    def buildRequest(self, method):
        messageBody = ""

        if method == "INVITE":
            # TODO add parameter for specifiying RTP port
            messageBody = SipMessage._buildSDP(self.localIP, 5004)

        return SipMessage._buildMessage(method, (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.branch, self.callID, self.sequence, method, self.fromTag, self.toTag, messageBody)

    async def invite(self):
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

            # Await non-Provisional response
            while 100 <= response.statusCode <= 199:
                response = await self.recvQueue.get()

            # Successfully opened dialog
            if 200 <= response.statusCode <= 299:
                rtpPort, rtcpPort = SipMessage._parseSDP(response.body)
                self.dialog = Dialog(self.callID, self.fromTag, "sip:IPCall@{}:{}".format(self.localIP, self.localPort), self.sequence, response.toTag, "sip:{}:{}".format(self.remoteIP, self.remotePort), response.additionalHeaders['Contact'].strip('<>'), rtpPort=rtpPort, rtcpPort=rtcpPort)

                # Ack in seperate transaction
                newTransaction = ClientTransaction(self.sendToTransport, "ACK", (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.dialog)
                newTransaction.ack(autoClean=True)

            # Failed to open dialog
            elif 300 <= response.statusCode <= 699:
                self.state = "Completed"
                self.ack()

                # Answer duplicate final responses for 32 seconds before terminating transaction
                try:
                    async with asyncio.timeout(Transaction.ANSWER_DUPLICATES_DURATION):
                        while(True):
                            response = await self.recvQueue.get()
                            if 300 <= response.statusCode <= 699:
                                self.ack()
                            else:
                                # TODO Maybe return a malformed response? *at the very least shouldn't cause program exit
                                print("Invalid status code")
                                exit()
                except TimeoutError:
                    pass

            else:
                # Invalid response code TODO generate a malformed request response? *Note: could also do this at a lower level.
                print("Invalid response code")
                exit()

        self.terminate()
        # TODO fix if no response, self.dialog undefined
        return self.dialog

    async def nonInvite(self, method):
        # TODO Ensure dialog established
        # if not self.dialog:
        #     print("No dialog")
        #     exit()
        self.state = "Trying"
        request = self.buildRequest(method)

        transactionTimeout = 64 * Transaction.T1
        response = None

        async with asyncio.timeout(transactionTimeout):
            attempts = 0
            while(not response or 100 <= response.statusCode <= 199):
                self.sendToTransport(request, (self.remoteIP, self.remotePort))

                retransmitInterval = (pow(2, attempts) * Transaction.T1)
                retransmitInterval = min(Transaction.T2, retransmitInterval)

                try:
                    async with asyncio.timeout(retransmitInterval):
                        response = await self.recvQueue.get()
                        # TODO does this state update provide any value?
                        if 100 <= response.statusCode <= 199:
                            self.state = 'Proceeding'
                except TimeoutError:
                    attempts += 1

        # TODO handle possible transport error during request

        if response:
            if 300 <= response.statusCode <= 699:
                self.state = 'Completed'
                # Buffer response retransmissions
                try:
                    async with asyncio.timeout(Transaction.T4):
                        while(True):
                            response = await self.recvQueue.get()
                except TimeoutError:
                    pass
        
        self.terminate()
        if method == 'BYE':
            self.dialog.terminate()

    # TODO why is autoclean necessary again? Is there a better way to handle this?
    def ack(self, autoClean=False):
        outgoingMsg = self.buildRequest("ACK")
        self.sendToTransport(outgoingMsg, (self.remoteIP, self.remotePort))

        if autoClean:
            self.terminate()
    
    def _genCallID(self):
        return hex(time.time_ns())[2:] + hex(int(random.getrandbits(32)))[2:]
    
    def _genBranch(self):
        return Transaction.BRANCH_MAGIC_COOKIE + hashlib.md5((self.toTag + self.fromTag + self.callID + "SIP/2.0/UDP {}:{};".format(self.localIP, self.localPort) + str(self.sequence)).encode()).hexdigest()
