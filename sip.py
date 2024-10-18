import socket
import threading
import time
import random
import hashlib
import queue
import json

# TODO implement whitelist
PORT = 5060
READ_SIZE = 2048
SOCKET_TIMEOUT = 1
T1 = 0.5 # Estimate of RTT (default 500 milliseconds)

def _getHeader(headers, targetLabel):
    for header in headers:
        if header.startswith(targetLabel + ": "):
            content = header.split(" ", 1)[1].strip()
            if(content.isdigit()):
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
        subHeadingDict["contact"] = contact

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

    messageType = "Request"
    if(startLine.startswith("SIP/2.0")):
        messageType = "Response"

    headerDict = {}
    for header in headers:
        label, content = header.split(": ", 1)
        if(content.strip().isdigit()):
            content = int(content.strip())
        headerDict[label] = content

    if(deepHeaderParse):
        for label in ["Via", "From", "To", "CSeq"]:
            _parseHeader(label, headerDict)

    return {"messageType": messageType, "startLine": startLine, "headers": headerDict, "messageBody": messageBody, "messageBodyLength": len(messageBody)}

# TODO Remove UDP Handler class and instead port methods to be part of the SIP class?
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


# class Dialog():
#     UAS = 1
#     UAC = 2

#     def __init__(self, state, role, localSeq, remoteSeq, localURI, remoteURI, remoteTarget, callID=None, localTag=None, remoteTag=None):
#         self.state = state
#         self.role = role
#         self.callID = #callID
#         self.localTag = #localTag
#         self.remoteTag = #remoteTag
#         self.dialogID = "{};localTag={};remoteTag={}".format(self.callID, self.localTag, self.remoteTag)
#         self.localSeq = localSeq
#         self.remoteSeq = remoteSeq
#         self.localURI = localURI
#         self.remoteURI = remoteURI
#         self.remoteTarget = remoteTarget
#         #self.secure = secure
#         #self.routeSet = routeSet

class Transaction:
    def __init__(self, transactionUser, localAddress, remoteAddress, state, dialog):
        self.transactionUser = transactionUser
        self.localIP, self.localPort = localAddress
        self.remoteIP, self.remotePort = remoteAddress
        self.state = state
        self.dialog = dialog

        self.fromTag = None
        self.toTag = None
        self.branch = None
        self.sequence = None

        self.recvQueue = queue.Queue()

    def getRecvQueue(self):
        return self.recvQueue
    
    def getBranch(self):
        return self.branch

class ClientTransaction(Transaction):
    def __init__(self, transactionUser, localAddress, remoteAddress, state, dialog=None):
        super().__init__(transactionUser, localAddress, remoteAddress, state, dialog)
        #Transaction().__init__(transactionUser, localAddress, remoteAddress, state, dialog)
        
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
        return Sip._buildMessage("INVITE", (self.localIP, self.localPort), (self.remoteIP, self.remotePort), self.branch, self.callID, self.sequence, method, self.fromTag)

        # elif(method=="CANCEL"):

        # elif(method=="BYE"):
            
        # elif(method=="ACK"):

        # else:
        #     #TODO better error handling here
        #     print("Unsupported Request Method")
        #     exit()

    # def transmit(self, attempts=1):




    def invite(self, remoteAddress):
        # Send Invite
        request = self.buildRequest("INVITE")
        self.transactionUser.getUDPHandler().sender(remoteAddress, request)

        # Initate timers
        # timeoutTimer = threading.Timer(64 * T1) # If still in calling state when timeoutTimer triggers, inform TU of timeout
        
        # self.transactionUser.getUDPHandler()
        # while self.state == "Calling" and timeoutTimer.is_alive():
        #         retransmitTimer = threading.Timer(pow(2, attempt) * T1) # If fires, client transaction must retransmit request and reset timer
        #         attempt += 1







        # Await 1xx response

        # Await 200 OK

        # Create a seperate Transaction for Acking


    # def nonInvite(method):

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
        self.clientTransactions[transaction.getBranch()] = transaction

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

        # TODO may need to handle ;received            
        headers = {"Call-ID": callID}

        if(type in ["INVITE", "ACK", "CANCLE", "BYE"]):            
            startLine = "{} SIP:{}:{} SIP/2.0\r\n".format(type, remoteIP, remotePort)
            headers["Via"] = "SIP/2.0/UDP {}:{}".format(localIP, localPort)
            headers["From"] = "<sip:IPCall@{}:{}>".format(localIP, localPort, fromTag)
            headers["To"] = "<sip:{}:{}>".format(remoteIP, remotePort, toTag)
            headers["Max-Forwards"] = "70"
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
        transaction = ClientTransaction(self, self.UDPHandler.getLocalAddress(), (address, port), "Calling")
        transaction.invite((address, port))
        print("Attempting to intitate a call with {}:{}".format(address, port))

        # # TODO send invite request to handler
        # inviteRequest = SIPService._buildMessage("INVITE", ("10.13.0.23", 5060), (address, port))
        # self.UDPHandler.sender(inviteRequest, (address, port))

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
            print(json.dumps(message, indent=4))

            # Pass to matching transaction
            if(message["messageType"] == "Response"):
                print(message["headers"]["Via"])
                key = message["headers"]["Via"]["branch"] + message["headers"]["CSeq"]["method"]
                if(key in self.clientTransactions):
                    self.clientTransactions[key].getRecvQueue().put(message)
                
                # Ignore orphansed response
                else:
                    continue
            
            # TODO Create new transaction thread if one doesn't exist
            #elif(message["messageType"] == "Request"):

            else:
                print("Unsupported message type")
                exit()



SIPService = Sip()
SIPService.start()
SIPService.invite("10.13.0.6", 5060)

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