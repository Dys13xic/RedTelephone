import socket
import threading
import time
import random
import hashlib
import queue
import json

# TODO implement whitelist
SIP_PORT = 5060
RTP_PORT = 5004
READ_SIZE = 2048
SOCKET_TIMEOUT = 1
NANOSECONDS_IN_MILISECONDS = 1000000
T1 = 500 * NANOSECONDS_IN_MILISECONDS # Estimate of RTT (default 500 milliseconds or in this case 500,000,000 nanoseconds)
T2 = 4000 * NANOSECONDS_IN_MILISECONDS # Estimate of time a non-INVITE server transaction takes to respond to a request
T4 = 5000 * NANOSECONDS_IN_MILISECONDS # Estimate of time for the network to clear messages between network and server client

def _getHeader(headers, targetLabel):
    for header in headers:
        if header.startswith(targetLabel + ": "):
            content = header.split(" ", 1)[1].strip()
            if content.isdigit():
                content = int(content)

            return content

    return None

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
        subHeadingDict["address"] = address
    
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

# The sender and listener methods are sort of both catered specifically to SIP traffic...
class UDPHandler:

    def __init__(self, port, recvQueue, halt):
        self.localPort = port
        self.localIP = None
        self.recvQueue = recvQueue
        self.halt = halt
        self.sendSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.bind(("", self.localPort))

        # Retrieve local IP
        try:
            tempSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            tempSock.connect(("8.8.8.8", 80))
            self.localIP = tempSock.getsockname()[0]
            tempSock.close()
        except:
            "Failed to determine local IP address"
            exit()

        while(self.halt.is_set() == False):
            try:
                data, (srcAddress, srcPort) = sock.recvfrom(READ_SIZE)
            except socket.timeout:
                continue

            # TODO should I add more validation of UDP message format?

            startLineEncoded = data.split(b"\r\n", 1)[0]
            headersEncoded, messageBodyEncoded = data.split(b"\r\n\r\n")

            startLine = startLineEncoded.decode("utf-8")
            headers = headersEncoded.decode("utf-8").split("\r\n")[1:]
            contentLength = _getHeader(headers, "Content-Length")

            messageType = "Request"
            if(startLine.startswith("SIP/2.0")):
                messageType = "Response"



            if(contentLength):
                # Long messages truncated to contentLength
                if(len(messageBodyEncoded) > contentLength):
                    messageBodyEncoded = messageBodyEncoded[:contentLength]
                    print("Message truncated")

                # Short messages discarded
                elif(len(messageBodyEncoded) < contentLength):
                    # 400 Bad Request response generated
                    if(messageType == "Request"):
                        # TODO Generate a 400 (Bad Request) response
                        print("Bad Request")

                    print("Message discarded")
                    continue

            self.recvQueue.put((srcAddress, srcPort, data))

        sock.close()

    def sender(self, target, message):
        bytesSent = self.sendSock.sendto(message, target)
        # TODO confirm that bytes sent matches data size (is this necessary? UDP packets are atomic, I suppose we should still check that data has gone out and log otherwise)

    def getLocalAddress(self):
        return (self.localIP, self.localPort)


class Dialog():
    UAS = 1
    UAC = 2

    EARLY = 1
    CONFIRMED = 2
    TERMINATED = 3

    def __init__(self, transactionUser, state, role, callID, localTag, localURI, localSeq, remoteTag, remoteURI, remoteTarget, remoteSeq=None):
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

        self.transactionUser.addDialog(self)

    def getLocalTag(self):
        return self.localTag

    def getRemoteTag(self):
        return self.remoteTag
    
    def getCallID(self):
        return self.callID

    def getLocalSeq(self):
        return self.localSeq
    
    def setState(self, state):
        self.state = state

    def getDialogID(self):
        return self.dialogID
    
    def terminate(self):
        self.state = Dialog.TERMINATED
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

        self.recvQueue = queue.Queue()
        self.thread = threading.Thread(target=self.handler)

    def getRecvQueue(self):
        return self.recvQueue
    
    def getBranch(self):
        return self.branch
    
    def getRequestMethod(self):
        return self.requestMethod

    def getThread(self):
        return self.thread

    def handler(self):
        if(self.requestMethod == "INVITE"):
            self.invite()

        elif(self.requestMethod == "ACK"):
            self.ack()

        #elif(self.requestMethod == "")

    def passToTransport(self, outgoingMsg, limitRetransmitInterval=False):
        currentTime = time.time_ns()
        transactionTimeout = currentTime + (64 * T1)
        attempts = 0

        while(currentTime < transactionTimeout and self.getRecvQueue().empty()):
            self.transactionUser.getUDPHandler().sender((self.remoteIP, self.remotePort), outgoingMsg)

            retransmitInterval = (pow(2, attempts) * T1)
            if(limitRetransmitInterval):
                retransmitInterval = min((retransmitInterval, T2))

            retransmitTimeout = currentTime + retransmitInterval
            while(currentTime < retransmitTimeout and currentTime < transactionTimeout and self.getRecvQueue().empty()):
                    currentTime = time.time_ns()

            attempts += 1

        if self.getRecvQueue().empty():
            respone = None
        else:
            response = self.getRecvQueue().get()

        self.state = "Proceeding"
        return response, retransmitTimeout, transactionTimeout

    def terminate(self):
        self.state = "Terminated"
        self.transactionUser.removeClientTransaction(self)

class ClientTransaction(Transaction):
    def __init__(self, transactionUser, requestMethod, localAddress, remoteAddress, state, dialog=None):
        super().__init__(transactionUser, requestMethod, localAddress, remoteAddress, state, dialog)
        
        if(self.dialog):
            self.fromTag = dialog.getLocalTag()
            self.toTag = dialog.getRemoteTag()
            self.callID = dialog.getCallID()
            self.sequence = dialog.getLocalSeq() + 1        # TODO update dialog settings after request sent
        
        else:
            self.fromTag = hex(int(random.getrandbits(32)))[2:]
            self.toTag = ""
            self.callID = hex(time.time_ns())[2:] + hex(int(random.getrandbits(32)))[2:]
            self.sequence = 1

        self.branch = Sip.BRANCH_MAGIC_COOKIE + hashlib.md5((self.toTag + self.fromTag + self.callID + "SIP/2.0/UDP {}:{};".format(self.localIP, self.localPort) + str(self.sequence)).encode()).hexdigest()
        self.transactionUser.addClientTransaction(self)

    def buildRequest(self, method):
        messageBody = ""

        if method == "INVITE":
            messageBody = Sip._buildSDP(self.localIP, RTP_PORT)

        return Sip._buildMessage(method, (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.branch, self.callID, self.sequence, method, self.fromTag, self.toTag, messageBody)

    def invite(self):
        request = self.buildRequest("INVITE")
        response, _, _ = self.passToTransport(request)

        # TODO handle possible transport error during request

        if response:
            # Await response suitable for dialog creation
            while 'tag' not in response['headers']['To']:
                response = self.getRecvQueue().get()
            self.toTag = response['headers']['To']['tag']

            # Await non-Provisional response
            while 100 <= response['statusCode'] <= 199:
                if not self.dialog:
                    self.dialog = Dialog(self.transactionUser, Dialog.EARLY, Dialog.UAC, self.callID, self.fromTag, "sip:IPCall@{}:{}".format(self.localIP, self.localPort), self.sequence, response['headers']['To']['tag'], "sip:{}:{}".format(self.remoteIP, self.remotePort), response['headers']['Contact'].strip('<>'))
                response = self.getRecvQueue().get()

            # Successfully opened dialog
            if 200 <= response["statusCode"] <= 299:
                if self.dialog:
                    self.dialog.setState(Dialog.CONFIRMED)
                else:
                    self.dialog = Dialog(self.transactionUser, Dialog.CONFIRMED, Dialog.UAC, self.callID, self.fromTag, "sip:IPCall@{}:{}".format(self.localIP, self.localPort), self.sequence, response['headers']['To']['tag'], "sip:{}:{}".format(self.remoteIP, self.remotePort), response['headers']['Contact'].strip('<>'))

                # Ack in seperate transaction
                ackTransaction = ClientTransaction(self.transactionUser, "ACK", (self.localIP, self.localPort), (self.remoteIP, self.remotePort), None, self.dialog)
                ackTransaction.getThread().start()
                self.terminate()

            # Failed to open dialog
            elif 300 <= response['statusCode'] <= 699:

                if self.dialog:
                    self.dialog.terminate()

                self.state = "Completed"
                self.ack()

                currentTime = time.time_ns()
                completedTimeout = currentTime + (32000 * NANOSECONDS_IN_MILISECONDS)

                # Answer duplicate final responses for 32 seconds before terminating transaction
                while(currentTime < completedTimeout):
                    if self.getRecvQueue().empty() == False:
                        response = self.getRecvQueue().get()
                        if 300 <= response['statusCode'] <= 699:
                            self.ack()
                        else:
                            # TODO Maybe return a malformed response? *at the very least shouldn't cause program exit
                            print("Invalid status code")
                            exit()
                    
                    currentTime = time.time_ns()

                self.terminate()

            else:
                # Invalid response code TODO generate a malformed request response? *Note: could also do this at a lower level.
                print("Invalid response code")
                exit()

        # Transaction timed out
        else:
            self.terminate

    def ack(self):
        outgoingMsg = self.buildRequest("ACK")
        self.transactionUser.getUDPHandler().sender((self.remoteIP, self.remotePort), outgoingMsg)
        self.terminate()

    def nonInvite(self, method):
        # Ensure dialog established
        if not self.dialog:
            print("No dialog")
            exit()

        request = self.buildRequest(method)
        response, retransmitTimeout, transactionTimeout = self.passToTransport(request, True)
        currentTime = time.time_ns()

        # TODO handle possible transport error during request

        if response:
            while(currentTime < transactionTimeout and 100 <= response['statusCode'] <= 199):
                while(currentTime < retransmitTimeout and currentTime < transactionTimeout and 100 <= response['statusCode' <= 199]):
                    if self.recvQueue.empty() == False:
                        response = self.recvQueue.get()
                    
                    currentTime = time.time_ns

                retransmitTimeout = currentTime + T2
                self.transactionUser.getUDPHandler().sender((self.remoteIP, self.remotePort), request)

            if 100 <= response['statusCode'] <= 199:
                # Transaction timed out
                self.terminate()

            elif 200 <= response['statusCode'] <= 699:
                # Buffer duplicate responses for 5 seconds before terminating transaction
                completedTimeout = currentTime + T4
                while(currentTime < completedTimeout):
                    if self.getRecvQueue().empty() == False:
                        response = self.getRecvQueue().get()

                    currentTime = time.time_ns()

                self.terminate()

            else:
                # Invalid response code TODO generate a malformed request response? *Note: could also do this at a lower level.
                print("Invalid response code")
                exit()

        # Transaction timed out
        else:
            self.terminate()

# class ServerTransaction(Transaction):
#     def __init__(self, localAddress, remoteAddress, state, sequence=1, callID)
        

#     def buildResponse(status):



    

class Sip:

    BRANCH_MAGIC_COOKIE = "z9hG4bK"

    def __init__(self, port=5060):
        self.port = port
        self.clientTransactions = {}
        self.dialogs = {}

        self.recvQueue = queue.Queue()
        self.halt = threading.Event()
        self.UDPHandler = UDPHandler(self.port, self.recvQueue, self.halt)

        self.UDPListenerThread = threading.Thread(target=self.UDPHandler.listener)
        self.SIPHandlerThread = threading.Thread(target=self.handler)

    def getUDPHandler(self):
        return self.UDPHandler

    def addClientTransaction(self, transaction):
        self.clientTransactions[transaction.getBranch() + transaction.getRequestMethod()] = transaction

    def removeClientTransaction(self, transaction):
        del self.clientTransactions[transaction.getBranch() + transaction.getRequestMethod()]

    def addDialog(self, dialog):
        self.dialogs[dialog.getDialogID()] = dialog
    
    def removeDialog(self, dialog):
        del self.dialogs[dialog.getDialogID()]

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
m=audio {} RTP/AVP 123\r
a=sendrecv\r
a=rtpmap:123 opus/48000/2\r
a=fmtp:123 maxplaybackrate=16000\r\n""".format(sessionID, sessionVersion, localAddress, localAddress, port)
        
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

        if(toTag):
            toTag = ";tag=" + toTag

        # TODO may need to handle ;received            
        headers = {"Call-ID": callID}

        if(type in ["INVITE", "ACK", "CANCLE", "BYE"]):            
            startLine = "{} SIP:{}:{} SIP/2.0\r\n".format(type, remoteIP, remotePort)
            headers["Via"] = "SIP/2.0/UDP {}:{}".format(localIP, localPort)
            headers["From"] = "<sip:IPCall@{}:{}>;tag={}".format(localIP, localPort, fromTag)
            headers["To"] = "<sip:{}:{}>{}".format(remoteIP, remotePort, toTag)
            headers["Max-Forwards"] = "70"
            if(type == "ACK"):
                sequenceRequestType = "INVITE"
            else:
                sequenceRequestType = type

        elif(type in ["100 Trying", "180 Ringing", "200 OK", "400 Bad Request", "408 Request Timeout", "486 Busy Here", "487 Request Terminated"]):
            startLine = "SIP/2.0 {}\r\n".format(type)
            headers["Via"] = "SIP/2.0/UDP {}:{}".format(remoteIP, remotePort)
            headers["From"] = "<sip:IPCall@{}:{}>".format(remoteIP, remotePort, fromTag),
            headers["To"] = "<sip:{}:{}>".format(localIP, localPort, toTag)

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


    def start(self):
        self.SIPHandlerThread.start()
        self.UDPListenerThread.start()
        print("SIP service started on port: {}\n".format(self.port))

    def stop(self):
        self.halt.set()
        self.SIPHandlerThread.join()
        self.UDPListenerThread.join()
        print("SIP service terminated")

    def invite(self, address, port):
        print("Attempting to intitate a call with {}:{}".format(address, port))
        transaction = ClientTransaction(self, "INVITE", self.UDPHandler.getLocalAddress(), (address, port), "Calling")
        transaction.getThread().start()

    # def cancel(self, address, port):
    #     print("Call cancelled")
    #     # TODO send cancel request to handler

    # def bye(self, address, port):
    #     print("Call ended")
    #     # TODO send bye request to handler

    def handler(self):
        while(self.halt.is_set() == False):
            try:
                (targetAddress, targetPort, data) = self.recvQueue.get(timeout=1)
            except queue.Empty:
                continue

            # Parse message
            message = _parseMessage(data, True)
            # print(json.dumps(message, indent=4))

            # Pass to matching transaction
            if(message["messageType"] == "Response"):
                #print(message["headers"]["Via"])
                key = message["headers"]["Via"]["branch"] + message["headers"]["CSeq"]["method"]
                if(key in self.clientTransactions):
                    self.clientTransactions[key].getRecvQueue().put(message)
                
                # Ignore orphaned response
                else:
                    continue
            
            # TODO Create new transaction thread if one doesn't exist
            #elif(message["messageType"] == "Request"):

            else:
                print("Unsupported message type")
                exit()



SIPService = Sip()
SIPService.start()
SIPService.invite("10.13.0.6", SIP_PORT)

# TODO, what if I passed a dialog object into the SIPService.invite() function IOT initialize it?
# I could then call Cancel or Bye on the dialog object itself
# Would make it easier to act on a dialog object as well



time.sleep(2)
SIPService.cancel()

# command = input()
# while(command != "EXIT"):
#     if(command == "INVITE"):
#         SIPService.invite("Remotehost", 5060)
#     elif(command == "CANCEL"):
#         SIPService.cancel("Remotehost", 5060)
#     elif(command == "BYE"):
#         SIPService.bye("Remotehost", 5060)
#     command = input()

# SIPService.stop()