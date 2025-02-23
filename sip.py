# 1st Party Library
from sipMessage import SipMessageFactory, SipRequest, SipResponse
from transport import Transport
from dialog import Dialog
from events import EventHandler

# Standard Library
import asyncio
import socket
import time
import random
import hashlib
import json

SIP_PORT = 5060
RTP_PORT = 5004

T1 = 0.5
T2 = 4
T4 = 5
ANSWER_DUPLICATES_DURATION = 32

def _parseSDP(messageBody):
    rtpPort, rtcpPort = RTP_PORT, RTP_PORT + 1
    fields = messageBody.split('\r\n')

    # TODO clean up this brutal parsing code
    for f in fields:
        if f.startswith('m=audio'):
            args = f.split(' ')
            rtpPort = int(args[1])

        elif f.startswith('a=rtcp:'):
            firstArg, _ = f.split(' ', 1)
            rtcpPort = int(firstArg[len('a=rtcp:'):])

    return rtpPort, rtcpPort


class Transaction:
    def __init__(self, transactionUser, requestMethod, localAddress, remoteAddress, dialog):
        self.transactionUser = transactionUser
        self.localIP, self.localPort = localAddress
        self.remoteIP, self.remotePort = remoteAddress
        self.state = None
        self.dialog = dialog

        self.fromTag = None
        self.toTag = None
        self.callID = None
        self.branch = None
        self.sequence = None
        self.requestMethod = requestMethod

        self.recvQueue = asyncio.Queue()

    @staticmethod
    def genTag():
        return hex(int(random.getrandbits(32)))[2:]
    
    @staticmethod
    def genCallID():
        return hex(time.time_ns())[2:] + hex(int(random.getrandbits(32)))[2:]
    
    def genBranch(self):
        return Sip.BRANCH_MAGIC_COOKIE + hashlib.md5((self.toTag + self.fromTag + self.callID + "SIP/2.0/UDP {}:{};".format(self.localIP, self.localPort) + str(self.sequence)).encode()).hexdigest()
    
    def cleanup(self):
        self.transactionUser.removeTransaction(self)


class ClientTransaction(Transaction):
    def __init__(self, transactionUser, requestMethod, localAddress, remoteAddress, dialog=None):
        super().__init__(transactionUser, requestMethod, localAddress, remoteAddress, dialog)
        
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
            self.fromTag = Transaction.genTag()
            self.toTag = ""
            self.callID = Transaction.genCallID()
            self.sequence = 1

        self.branch = self.genBranch()
        self.transactionUser.addTransaction(self)

    def buildRequest(self, method):
        messageBody = ""

        if method == "INVITE":
            messageBody = Sip._buildSDP(self.localIP, RTP_PORT)

        return Sip._buildMessage(method, (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.branch, self.callID, self.sequence, method, self.fromTag, self.toTag, messageBody)

    async def invite(self):
        self.state = "Calling"
        request = self.buildRequest("INVITE")

        transactionTimeout = 64 * T1
        response = None

        async with asyncio.timeout(transactionTimeout):
            attempts = 0
            while(not response):
                self.transactionUser.transport.send(request, (self.remoteIP, self.remotePort))
                retransmitInterval = (pow(2, attempts) * T1)

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
                rtpPort, rtcpPort = _parseSDP(response.body)
                self.dialog = Dialog(self.callID, self.fromTag, "sip:IPCall@{}:{}".format(self.localIP, self.localPort), self.sequence, response.toTag, "sip:{}:{}".format(self.remoteIP, self.remotePort), response.additionalHeaders['Contact'].strip('<>'), rtpPort=rtpPort, rtcpPort=rtcpPort)

                # Ack in seperate transaction
                newTransaction = ClientTransaction(self.transactionUser, "ACK", (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.dialog)
                newTransaction.ack(autoClean=True)

            # Failed to open dialog
            elif 300 <= response.statusCode <= 699:
                self.state = "Completed"
                self.ack()

                # Answer duplicate final responses for 32 seconds before terminating transaction
                try:
                    async with asyncio.timeout(ANSWER_DUPLICATES_DURATION):
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

        self.cleanup()
        # TODO fix if no response, self.dialog undefined
        return self.dialog

    async def nonInvite(self, method):
        # TODO Ensure dialog established
        # if not self.dialog:
        #     print("No dialog")
        #     exit()
        self.state = "Trying"
        request = self.buildRequest(method)

        transactionTimeout = 64 * T1
        response = None

        async with asyncio.timeout(transactionTimeout):
            attempts = 0
            while(not response or 100 <= response.statusCode <= 199):
                self.transactionUser.transport.send(request, (self.remoteIP, self.remotePort))

                retransmitInterval = (pow(2, attempts) * T1)
                retransmitInterval = min(T2, retransmitInterval)

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
                    async with asyncio.timeout(T4):
                        while(True):
                            response = await self.recvQueue.get()
                except TimeoutError:
                    pass
        
        self.cleanup()
        if method == 'BYE':
            self.dialog.terminate()

    def ack(self, autoClean=False):
        outgoingMsg = self.buildRequest("ACK")
        self.transactionUser.transport.send(outgoingMsg, (self.remoteIP, self.remotePort))

        if autoClean:
            self.cleanup()

    def getID(self):
        return self.branch + self.requestMethod


class ServerTransaction(Transaction):
    def __init__(self, transactionUser, requestMethod, localAddress, remoteAddress, callID, branch, fromTag, sequence, dialog=None):
        super().__init__(transactionUser, requestMethod, localAddress, remoteAddress, dialog)

        if(self.dialog):
            self.toTag = dialog.remoteTag()    
        else:
            self.toTag = hex(int(random.getrandbits(32)))[2:]
        
        self.callID = callID
        self.branch = branch
        self.fromTag = fromTag
        self.sequence = sequence

        self.transactionUser.addTransaction(self)

    @classmethod
    def fromMessage(cls, transactionUser, message, localAddress, dialog):
        return cls(transactionUser, message.method, localAddress, message.viaAddress, message.callID, message.branch, message.fromTag, 
                   message.seqNum, dialog)

    def buildResponse(self, status):
        messageBody = ""

        if status == "200 OK":
            messageBody = Sip._buildSDP(self.localIP, RTP_PORT)

        return Sip._buildMessage(status, (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.branch, self.callID, self.sequence, self.requestMethod, self.fromTag, self.toTag, messageBody)

    async def invite(self):
        self.state = 'Proceeding'
        response = self.buildResponse('100 Trying')
        self.transactionUser.transport.send(response, (self.remoteIP, self.remotePort))

        response = self.buildResponse('180 Ringing')
        self.transactionUser.transport.send(response, (self.remoteIP, self.remotePort))

        # TODO replace condition to implement behaviour for not accepting every call, i.e. 300 - 699 responses
        if True:
            # TODO, keep phone ringing until secret received?
            response = self.buildResponse('200 OK')
            self.transactionUser.transport.send(response, (self.remoteIP, self.remotePort))
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
                    self.transactionUser.transport.send(response, (self.remoteIP, self.remotePort))

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
        self.cleanup()

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

    def getID(self):
        return self.branch + self.remoteIP + str(self.remotePort)


class Sip():
    BRANCH_MAGIC_COOKIE = "z9hG4bK"

    eventDispatcher: EventHandler.dispatch
    port: int
    transactions: dict

    def __init__(self, eventDispatcher, port=SIP_PORT):
        self.eventDispatcher = eventDispatcher
        self.transport = None
        self.port = port
        self.transactions = {}

    def addTransaction(self, transaction):
        self.transactions[transaction.getID()] = transaction

    def removeTransaction(self, transaction):
        del self.transactions[transaction.getID()]

    @staticmethod
    def _buildSDP(localAddress, port=RTP_PORT):
        #TODO make session id and version unique
        sessionID = 8000
        sessionVersion = 8000

        sdp = """v=0
o=Hotline {} {} IN IP4 {}\r
s=SIP Call\r
c=IN IP4 {}\r
t=0 0\r
m=audio {} RTP/AVP 120\r
a=sendrecv\r
a=rtpmap:120 opus/48000/2\r
a=ptime:20\r\n""".format(sessionID, sessionVersion, localAddress, localAddress, port)
        #a=fmtp:120\r

        return sdp

    @staticmethod
    def _buildMessage(type, localAddress, remoteAddress, branch, callID, sequence, sequenceRequestType, fromTag, toTag="", messageBody=""):

        (localIP, localPort) = localAddress
        (remoteIP, remotePort) = remoteAddress

        if(fromTag):
            fromTag = ';tag=' + fromTag

        if(toTag):
            if type == '100 Trying':
                toTag = ''
            else:
                toTag = ";tag=" + toTag

        # TODO may need to handle ;received            
        headers = {"Call-ID": callID}

        if(type in ["INVITE", "ACK", "CANCLE", "BYE"]):            
            startLine = "{} SIP:{}:{} SIP/2.0\r\n".format(type, remoteIP, remotePort)
            headers["Via"] = "SIP/2.0/UDP {}:{}".format(localIP, localPort)
            headers["From"] = "<sip:IPCall@{}:{}>{}".format(localIP, localPort, fromTag)
            headers["To"] = "<sip:{}:{}>{}".format(remoteIP, remotePort, toTag)
            headers["Max-Forwards"] = "70"
            if type == "INVITE":
                headers['Contact'] = '<sip:IPCall@{}>'.format(localIP)   # TODO I think we'd need the public ip for a request outside of LAN
            # elif type == "ACK":
            #     sequenceRequestType = "INVITE"
            else:
                sequenceRequestType = type

        elif(type in ["100 Trying", "180 Ringing", "200 OK", "400 Bad Request", "408 Request Timeout", "486 Busy Here", "487 Request Terminated"]):
            startLine = "SIP/2.0 {}\r\n".format(type)
            headers["Via"] = "SIP/2.0/UDP {}:{}".format(remoteIP, remotePort)
            headers["From"] = "<sip:IPCall@{}:{}>{}".format(remoteIP, remotePort, fromTag)
            headers["To"] = "<sip:{}:{}>{}".format(localIP, localPort, toTag)

            if type != '100 Trying':
                headers['Contact'] = '<sip:{}:{}>'.format(localIP, localPort)

        else:
            print("{} Not implemented".format(type))
            exit()
        
        headers["Via"] += ";branch=" + branch
        headers["CSeq"] = "{} {}".format(sequence, sequenceRequestType)

        if(messageBody):
            headers['Content-Type'] = "application/sdp"

        headers["Content-Length"] = str(len(messageBody.encode("utf-8")))

        # Build message
        message = startLine
        for key in headers.keys():
            message += key + ": " + headers[key] + "\r\n"

        message += "\r\n{}".format(messageBody)
        return message.encode("utf-8")

    async def invite(self, address, port):
        print("Attempting to intitate a call with {}:{}".format(address, port))
        transaction = ClientTransaction(self, "INVITE", (self.transport.ip, self.port), (address, port))
        dialog = await transaction.invite()
        return dialog

    # TODO implement
    # def cancel(self, address, port):
    #     print("Call cancelled")

    async def bye(self, dialog):
        print("Ending call")
        _, remoteIP, remotePort = dialog.remoteTarget.split(':', 2)
        remotePort = int(remotePort)

        transaction = ClientTransaction(self, "BYE", (self.transport.ip, self.port), (remoteIP, remotePort), dialog)
        byeTask = asyncio.create_task(transaction.nonInvite('BYE'))
        await byeTask

    async def handleMsg(self, msg, addr):

        if isinstance(msg, SipResponse):
            # Pass response to matching transaction if one exists
            key = msg.branch + msg.seqMethod
            if(key in self.transactions):
                await self.transactions[key].recvQueue.put(msg)

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
            # TODO fix this so I can remove the 2nd part of "or" statement (maybe change the transaction field to originatingRequestMethod?)
            if (key in self.transactions and(msg.method == self.transactions[key].requestMethod or
                                                    (msg.method == 'ACK' and self.transactions[key].requestMethod == "INVITE"))):
                await self.transactions[key].recvQueue.put(msg)
            
            # TODO handle re-invite
            elif msg.method == 'INVITE':
                transaction = ServerTransaction.fromMessage(self, msg, (self.transport.ip, self.port), dialog=None)
                dialog = await transaction.invite()
                await self.eventDispatcher('inboundCallAccepted', dialog)

            # Ignore orphaned acks
            elif msg.method == 'ACK':
                pass

            elif dialog:
                transaction = ServerTransaction.fromMessage(self, msg, (self.transport.ip, self.port), dialog)
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