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

def _parseParameters(parameters):
    parameterDict = {}
    for parameter in parameters:
        parameterList = parameter.split("=", 1)
        label = parameterList[0]
        content = parameterList[1] if len(parameterList) == 2 else ""
        parameterDict[label] = content

    return parameterDict

def _parseHeader(label, headerDict):
    content = headerDict[label]

    if label == "CSeq":
        sequence, method = content.strip().split(" ")
        subHeadingDict = {"sequence": int(sequence), "method": method}

    elif label in ["From", "To"]:
        temp = content.strip().split(";")
        contact = temp[0]
        parameters = temp[1:] if len(temp) >= 2 else []
        subHeadingDict = _parseParameters(parameters)
        subHeadingDict["URI"] = contact

    elif label == "Via":
        protocol, temp = content.strip().split(" ", 1)
        tempList = temp.split(";")
        address = tempList[0]
        parameters = tempList[1:]
        subHeadingDict = _parseParameters(parameters)
        subHeadingDict["protocol"] = protocol
        subHeadingDict["IP"], subHeadingDict['port'] = address.split(':', 1)
        subHeadingDict['port'] = int(subHeadingDict['port'])
    
    else:
        print("Unsupported header")
        exit()

    headerDict[label] = subHeadingDict

def _parseMessage(data, deepHeaderParse=False):
    startLineEncoded = data.split(b"\r\n", 1)[0]
    headersEncoded, messageBodyEncoded = data.split(b"\r\n\r\n")
    
    startLine = startLineEncoded.decode("utf-8")
    messageBody = messageBodyEncoded.decode("utf-8")
    headers = headersEncoded.decode("utf-8").split("\r\n")[1:]

    headerDict = {}
    for header in headers:
        label, content = header.split(": ", 1)
        if content.strip().isdigit():
            content = int(content.strip())
        headerDict[label] = content

    if deepHeaderParse:
        for label in ["Via", "From", "To", "CSeq"]:
            _parseHeader(label, headerDict)

    if(startLine.startswith("SIP/2.0")):
        version, code, label = startLine.split(" ", 2)
        messageDict = {"messageType": "Response", "statusCode": int(code), "statusLabel": label, "headers": headerDict, "messageBody": messageBody, "messageBodyLength": len(messageBodyEncoded)}


    elif(startLine.endswith("SIP/2.0")):
        method, requestURI, version = startLine.split(" ", 2)
        messageDict = {"messageType": "Request", "method": method, "requestURI": requestURI}

    else:
        print("Malformed message")
        exit()

    messageDict["headers"] = headerDict
    messageDict["messageBody"] = messageBody
    messageDict["messageBodyLength"] = len(messageBodyEncoded)
    
    return messageDict


class Dialog():
    UAS = 1
    UAC = 2

    EARLY = 1
    CONFIRMED = 2

    def __init__(self, transactionUser, state, role, callID, localTag, localURI, localSeq, remoteTag, remoteURI, remoteTarget, remoteSeq=None, rtpPort = RTP_PORT, rtcpPort = RTP_PORT + 1):
        self.transactionUser = transactionUser
        self.state = state
        self.role = role
        self.callID = callID
        self.localTag = localTag
        self.remoteTag = remoteTag
        self.dialogID = "{};localTag={};remoteTag={}".format(self.callID, self.localTag, self.remoteTag)
        self.localSeq = localSeq
        self.remoteSeq = remoteSeq
        self.localURI = localURI
        self.remoteURI = remoteURI
        self.remoteTarget = remoteTarget
        #self.secure = secure
        #self.routeSet = routeSet
        self.rtpPort = rtpPort
        self.rtcpPort = rtcpPort

        self.transactionUser.addDialog(self)

    def getLocalTag(self):
        return self.localTag

    def getRemoteTag(self):
        return self.remoteTag
    
    def getRemoteURI(self):
        return self.remoteURI
    
    def getCallID(self):
        return self.callID

    def getLocalSeq(self):
        return self.localSeq
    
    def getID(self):
        return self.dialogID

    # TODO Clean up the way this method operates
    def getRemoteIP(self):
        _, remoteIP, _ = self.remoteURI.split(':', 2)
        return remoteIP
    
    def getRtpPorts(self):
        return self.rtpPort, self.rtcpPort
    
    def setState(self, state):
        self.state = state
    
    def setRtpPorts(self, rtpPort, rtcpPort):
        self.rtpPort = rtpPort
        self.rtcpPort = rtcpPort
    
    def cleanup(self):
        self.transactionUser.removeDialog(self)
        # TODO is this going to mess up transactions that belong to this dialog and are still running?


class Transaction:
    def __init__(self, transactionUser, requestMethod, localAddress, remoteAddress, state, dialog):
        self.transactionUser = transactionUser
        self.localIP, self.localPort = localAddress
        self.remoteIP, self.remotePort = remoteAddress
        self.state = state
        self.dialog = dialog

        self.fromTag = None
        self.toTag = None
        self.branch = None
        self.sequence = None
        self.requestMethod = requestMethod

        self.recvQueue = asyncio.Queue()
    
    def getRecvQueue(self):
        return self.recvQueue
    
    def getRequestMethod(self):
        return self.requestMethod
    
    def cleanup(self):
        self.transactionUser.removeTransaction(self)


class ClientTransaction(Transaction):
    def __init__(self, transactionUser, requestMethod, localAddress, remoteAddress, state, dialog=None):
        super().__init__(transactionUser, requestMethod, localAddress, remoteAddress, state, dialog)
        
        if(self.dialog):
            self.fromTag = dialog.getLocalTag()
            self.toTag = dialog.getRemoteTag()
            self.callID = dialog.getCallID()

            # TODO update dialog settings after request sent
            if self.requestMethod == "ACK":
                self.sequence = dialog.getLocalSeq()
            else:
                self.sequence = dialog.getLocalSeq() + 1
        
        else:
            self.fromTag = hex(int(random.getrandbits(32)))[2:]
            self.toTag = ""
            self.callID = hex(time.time_ns())[2:] + hex(int(random.getrandbits(32)))[2:]
            self.sequence = 1

        self.branch = Sip.BRANCH_MAGIC_COOKIE + hashlib.md5((self.toTag + self.fromTag + self.callID + "SIP/2.0/UDP {}:{};".format(self.localIP, self.localPort) + str(self.sequence)).encode()).hexdigest()
        self.transactionUser.addTransaction(self)

    def buildRequest(self, method):
        messageBody = ""

        if method == "INVITE":
            messageBody = Sip._buildSDP(self.localIP, RTP_PORT)

        return Sip._buildMessage(method, (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.branch, self.callID, self.sequence, method, self.fromTag, self.toTag, messageBody)

    async def invite(self):
        request = self.buildRequest("INVITE")

        transactionTimeout = 64 * T1
        response = None

        async with asyncio.timeout(transactionTimeout):
            attempts = 0
            while(not response):
                self.transactionUser.send(request, (self.remoteIP, self.remotePort))
                retransmitInterval = (pow(2, attempts) * T1)

                try:
                    async with asyncio.timeout(retransmitInterval):
                        response = await self.recvQueue.get()
                except TimeoutError:
                    attempts += 1

        # TODO handle possible transport error during request

        if response:
            # Await response suitable for dialog creation
            while 'tag' not in response['headers']['To']:
                response = await self.recvQueue.get()
            self.toTag = response['headers']['To']['tag']

            # Await non-Provisional response
            while 100 <= response['statusCode'] <= 199:
                if not self.dialog:
                    self.dialog = Dialog(self.transactionUser, Dialog.EARLY, Dialog.UAC, self.callID, self.fromTag, "sip:IPCall@{}:{}".format(self.localIP, self.localPort), self.sequence, response['headers']['To']['tag'], "sip:{}:{}".format(self.remoteIP, self.remotePort), response['headers']['Contact'].strip('<>'))
                response = await self.recvQueue.get()

            # Successfully opened dialog
            if 200 <= response["statusCode"] <= 299:
                rtpPort, rtcpPort = _parseSDP(response['messageBody'])
                if self.dialog:
                    self.dialog.setState(Dialog.CONFIRMED)
                    self.dialog.setRtpPorts(rtpPort, rtcpPort)
                else:
                    self.dialog = Dialog(self.transactionUser, Dialog.CONFIRMED, Dialog.UAC, self.callID, self.fromTag, "sip:IPCall@{}:{}".format(self.localIP, self.localPort), self.sequence, response['headers']['To']['tag'], "sip:{}:{}".format(self.remoteIP, self.remotePort), response['headers']['Contact'].strip('<>'), rtpPort=rtpPort, rtcpPort=rtcpPort)

                # Ack in seperate transaction
                newTransaction = ClientTransaction(self.transactionUser, "ACK", (self.localIP, self.localPort), (self.remoteIP, self.remotePort), None, self.dialog)
                newTransaction.ack(autoClean=True)

            # Failed to open dialog
            elif 300 <= response['statusCode'] <= 699:

                if self.dialog:
                    self.dialog.cleanup()
                    self.dialog = None

                self.state = "Completed"
                self.ack()

                # Answer duplicate final responses for 32 seconds before terminating transaction
                try:
                    async with asyncio.timeout(ANSWER_DUPLICATES_DURATION):
                        while(True):
                            response = await self.recvQueue.get()
                            if 300 <= response['statusCode'] <= 699:
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
        return self.dialog

    async def nonInvite(self, method):
        # TODO Ensure dialog established
        # if not self.dialog:
        #     print("No dialog")
        #     exit()

        request = self.buildRequest(method)

        transactionTimeout = 64 * T1
        response = None

        async with asyncio.timeout(transactionTimeout):
            attempts = 0
            while(not response or 100 <= response['statusCode'] <= 199):
                self.transactionUser.send(request, (self.remoteIP, self.remotePort))

                retransmitInterval = (pow(2, attempts) * T1)
                retransmitInterval = min(T2, retransmitInterval)

                try:
                    async with asyncio.timeout(retransmitInterval):
                        response = await self.recvQueue.get()
                        # TODO does this state update provide any value?
                        if 100 <= response['statusCode'] <= 199:
                            self.state = 'Proceeding'
                except TimeoutError:
                    attempts += 1

        # TODO handle possible transport error during request

        if response:
            if 300 <= response['statusCode'] <= 699:
                self.state = 'Completed'
                # Buffer response retransmissions
                try:
                    async with asyncio.timeout(T4):
                        while(True):
                            response = await self.recvQueue.get()
                except TimeoutError:
                    pass
        
        self.cleanup()

    def ack(self, autoClean=False):
        outgoingMsg = self.buildRequest("ACK")
        self.transactionUser.send(outgoingMsg, (self.remoteIP, self.remotePort))

        if autoClean:
            self.cleanup()

    def getID(self):
        return self.branch + self.requestMethod


class ServerTransaction(Transaction):
    def __init__(self, transactionUser, requestMethod, localAddress, remoteAddress, callID, branch, fromTag, sequence, state, dialog=None):
        super().__init__(transactionUser, requestMethod, localAddress, remoteAddress, state, dialog)

        if(self.dialog):
            self.toTag = dialog.getRemoteTag()    
        else:
            self.toTag = hex(int(random.getrandbits(32)))[2:]
        
        self.callID = callID
        self.branch = branch
        self.fromTag = fromTag
        self.sequence = sequence

        self.transactionUser.addTransaction(self)

    def buildResponse(self, status):
        messageBody = ""

        if status == "200 OK":
            messageBody = Sip._buildSDP(self.localIP, RTP_PORT)

        return Sip._buildMessage(status, (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.branch, self.callID, self.sequence, self.requestMethod, self.fromTag, self.toTag, messageBody)

    async def invite(self):
        self.state = 'Proceeding'
        response = self.buildResponse('100 Trying')
        self.transactionUser.send(response, (self.remoteIP, self.remotePort))

        response = self.buildResponse('180 Ringing')
        self.transactionUser.send(response, (self.remoteIP, self.remotePort))

        # TODO replace condition to implement behaviour for not accepting every call, i.e. 300 - 699 responses
        if True:
            # TODO, keep phone ringing until secret received?
            response = self.buildResponse('200 OK')
            self.transactionUser.send(response, (self.remoteIP, self.remotePort))
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
                while(not request or request['method'] != 'ACK'):
                    self.transactionUser.send(response, (self.remoteIP, self.remotePort))

                    retransmitInterval = (pow(2, attempts) * T1)
                    retransmitInterval = min(T2, retransmitInterval)

                    try:
                        async with asyncio.timeout(retransmitInterval):
                            request = await self.recvQueue.get()
                            # TODO does this state update provide any value?
                            if request['method'] == 'ACK':
                                self.state = 'Confirmed'
                    except TimeoutError:
                        attempts += 1

            # TODO handle possible transport error during request

            if request:
                if 300 <= response['statusCode'] <= 699:
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

        self.dialog = Dialog(self.transactionUser, Dialog.CONFIRMED, Dialog.UAS, self.callID, self.toTag, "sip:IPCall@{}:{}".format(self.localIP, self.localPort), 0, self.fromTag, "sip:{}:{}".format(self.remoteIP, self.remotePort), remoteTarget, self.sequence)
        self.cleanup()

        return self.dialog
        
    async def nonInvite(self, method):
        self.state = 'Proceeding'

        if method == 'BYE':
            response = self.buildResponse('200 OK')
        else:
            # TODO implement additional requests
            print('Unsupported Request')

        
    async def ack(self):
        pass

    def getID(self):
        return self.branch + self.remoteIP + str(self.remotePort)


class SipEndpointProtocol:
    def __init__(self):
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport

    def send(self, data, addr):
        try:
            print(data)
            self._transport.sendto(data, addr)
        except Exception as e:
            print("Failed to Send: ", e)
            exit(1)

    def datagram_received(self, data, addr):
        raise NotImplementedError

    def error_received(e):
        print("Error Received: ", e)
        exit(1)

    def connection_lost(e):
        print("Connection Lost: ", e)
        exit(1)

    def stop(self):
        self._transport.close()


class Sip(SipEndpointProtocol):
    BRANCH_MAGIC_COOKIE = "z9hG4bK"

    def __init__(self, port=SIP_PORT, inviteReceivedCallback=None, byeReceivedCallback=None):
        self.port = port
        self.inviteReceivedCallback = inviteReceivedCallback
        self.byeReceivedCallback = byeReceivedCallback
        self.transactions = {}
        self.dialogs = {}

        # Retrieve local IP
        try:
            tempSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            tempSock.connect(("8.8.8.8", 80))
            self.ip = tempSock.getsockname()[0]
            tempSock.close()
        except:
            "Failed to determine local IP address"
            exit()

    def datagram_received(self, data, addr):
        loop = asyncio.get_event_loop()
        loop.create_task(self.datagram_received_async(data, addr))

    async def datagram_received_async(self, data, addr):
        # TODO check message length against contentLength
        # Truncating long messages and discarding (with a 400 error) short messages
        await self.handleMsg(data, addr)

    def addTransaction(self, transaction):
        self.transactions[transaction.getID()] = transaction

    def removeTransaction(self, transaction):
        del self.transactions[transaction.getID()]

    def addDialog(self, dialog):
        self.dialogs[dialog.getID()] = dialog
    
    def removeDialog(self, dialog):
        del self.dialogs[dialog.getID()]

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

        # TODO
        #  When the server transport receives a request over any transport, it
        #    MUST examine the value of the "sent-by" parameter in the top Via
        #    header field value.  If the host portion of the "sent-by" parameter
        #    contains a domain name, or if it contains an IP address that differs
        #    from the packet source address, the server MUST add a "received"

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
        transaction = ClientTransaction(self, "INVITE", (self.ip, self.port), (address, port), "Calling")
        dialog = await transaction.invite()
        return dialog

    # TODO implement
    # def cancel(self, address, port):
    #     print("Call cancelled")

    async def bye(self, dialog):
        print("Ending call")
        _, remoteIP, remotePort = dialog.remoteTarget.split(':', 2)
        remotePort = int(remotePort)

        transaction = ClientTransaction(self, "BYE", (self.ip, self.port), (remoteIP, remotePort), "Trying", dialog)
        byeTask = asyncio.create_task(transaction.nonInvite('BYE'))
        await byeTask

    async def handleMsg(self, data, addr):
        message = _parseMessage(data, True)
        print(json.dumps(message, indent=4))

        # Pass response to matching transaction if one exists
        if(message["messageType"] == "Response"):
            key = message["headers"]["Via"]["branch"] + message["headers"]["CSeq"]["method"]
            if(key in self.transactions):
                await self.transactions[key].getRecvQueue().put(message)

        # TODO ensure request received is not a duplicate
        elif(message["messageType"] == "Request"):

            # Determine if SIP message belongs to existing dialog
            dialog = None
            if 'tag' in message['headers']['From'] and 'tag' in message['headers']['To']:
                key = message['headers']['Call-ID'] + message['headers']['To']['tag'] + message['headers']['From']['tag']
                if key in self.dialogs:
                    dialog = self.dialogs[key]

            # Determine if SIP message belongs to existing transaction
            key = message['headers']['Via']['branch'] + message['headers']['Via']['IP'] + str(message['headers']['Via']['port'])
            if (key in self.transactions and(message['method'] == self.transactions[key].getRequestMethod() or
                                                    (message['method'] == 'ACK' and self.transactions[key].getRequestMethod == "INVITE"))):
                await self.transactions[key].getRecvQueue().put(message)
            elif message['method'] == 'ACK':
                # Do not process orphaned ACK
                pass
            else:
                remoteIP = message['headers']['Via']['IP']
                remotePort = message['headers']['Via']['port']
                callID = message['headers']['Call-ID']
                branch = message['headers']['Via']['branch']
                fromTag = message['headers']['From']['tag']
                sequence = message['headers']['CSeq']['sequence']
                transaction = ServerTransaction(self, message['method'], (self.ip, self.port), (remoteIP, remotePort), callID, branch, fromTag, sequence, None, dialog)
                
                if message['method'] == 'INVITE':
                    dialog = await transaction.invite()
                    await self.inviteReceivedCallback(dialog)
                else:
                    await transaction.nonInvite(message['method'])
                    if message['method'] == 'BYE':
                        await self.byeReceivedCallback()

        else:
            print("Unsupported message type")
            exit()

    @staticmethod
    async def run():
        loop = asyncio.get_event_loop()
        _, endpoint = await loop.create_datagram_endpoint(
        lambda: Sip(SIP_PORT),
        local_addr=("0.0.0.0", SIP_PORT),
        )
        return endpoint

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