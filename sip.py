import socket
import threading
import time
import random
import hashlib
import queue

# TODO implement whitelist
PORT = 5060
READ_SIZE = 2048
SOCKET_TIMEOUT = 1

def _getHeader(headers, targetLabel):
    for header in headers:
        if header.startswith(targetLabel + ": "):
            content = header.split(" ", 1)[1].strip()
            if(content.isdigit()):
                content = int(content)
            
            return content
        
    return None

# TODO Remove UDP Handler class and instead port methods to be part of the SIP class?
# The sender and listener methods are sort of both catered specifically to SIP traffic...
class UDPHandler:

    def __init__(self, port, sendQueue, recvQueue, halt):
        self.localPort = port
        self.localIP = None
        self.sendQueue = sendQueue
        self.recvQueue = recvQueue
        self.halt = halt

    def listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.bind(("", self.localPort))

        try:
            sock.connect(("8.8.8.8", 80))
            self.localIP = sock.getsockname()[0]
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

    def sender(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while(self.halt.is_set() == False):
            try:
                (targetAddress, targetPort, data) = self.sendQueue.get(timeout=1)
                bytesSent = sock.sendto(data, (targetAddress, targetPort))
                # TODO confirm that bytes sent matches data size (is this necessary? UDP packets are atomic, I suppose we should still check that data has gone out and log otherwise)
            except queue.Empty:
                continue

    def getLocalAddress(self):
        return (self.localIP, self.localPort)


class Dialog():
    def __init__(self, state, callID, localTag, remoteTag, localSeq, remoteSeq, localURI, remoteURI, remoteTarget, secure=False, routeSet=[]):
        self.state = state
        self.callID = callID
        self.localTag = localTag
        self.remoteTag = remoteTag
        self.dialogID = "{};localTag={};remoteTag={}".format(self.callID, self.localTag, self.remoteTag)
        self.localSeq = localSeq
        self.remoteSeq = remoteSeq
        self.localURI = localURI
        self.remoteURI = remoteURI
        self.remoteTarget = remoteTarget
        self.secure = secure
        self.routeSet = routeSet

class Transaction:

    def __init__(self, localAddress, remoteAddres, state, sequence, dialog=None):
        self.localIP, self.localPort = localAddress
        self.remoteIP, self.remotePort = remoteAddres
        self.state = state
        self.dialog = dialog

    # def buildRequest(method)

    # def buildResponse(status)


class ClientTransaction(Transaction):
    def __init__(self, localAddress, remoteAddress, state, sequence=1, callID=None):
        Transaction.__init__(localAddress, remoteAddress, state, sequence)
        
        if(not callID):
            callID = hex(time.time_ns())[2:] + hex(int(random.getrandbits(32)))[2:]

        self.callID = callID
        self.sequence = sequence

    def invite():
        # Send Invite
        request = ClientTransaction.buildRequest("INVITE")

        # Initate timers

        # Await 1xx response

        # Await 200 OK

        # Create a seperate Transaction for Acking


    def nonInvite(method):

class ServerTransaction(Transaction):
    def __init__(self, localAddress, remoteAddress, state, sequence=1, callID)


    

class Sip:

    BRANCH_MAGIC_COOKIE = "z9hG4bK"

    def __init__(self, port=5060):
        self.port = port
        self.transactions = []
        self.dialogs = []

        self.sendQueue = queue.Queue()
        self.recvQueue = queue.Queue()
        self.halt = threading.Event()
        self.UDPHandler = UDPHandler(self.port, self.sendQueue, self.recvQueue, self.halt)

        self.UDPListenerThread = threading.Thread(target=self.UDPHandler.listener)
        self.UDPSenderThread = threading.Thread(target=self.UDPHandler.sender)
        self.SIPHandlerThread = threading.Thread(target=self.handler)

    @staticmethod
    def _buildMessage(type, localAddress, remoteAddress, branch=None, fromTag="", toTag="", callID=None, sequence=None, sequenceRequestType ="", messageBody=""):

        # TODO
        #  When the server transport receives a request over any transport, it
        #    MUST examine the value of the "sent-by" parameter in the top Via
        #    header field value.  If the host portion of the "sent-by" parameter
        #    contains a domain name, or if it contains an IP address that differs
        #    from the packet source address, the server MUST add a "received"

        (localIP, localPort) = localAddress
        (remoteIP, remotePort) = remoteAddress

        # TODO may need to handle ;received
        if(not callID and type == "INVITE"):
            callID = hex(time.time_ns())[2:] + hex(int(random.getrandbits(32)))[2:]
        else:
            print("Failed to include Call-ID")
            exit()            
            
        headers = {}
        headers["Call-ID"] = callID

        if(type in ["INVITE", "ACK", "CANCLE", "BYE"]):            
            startLine = "{} SIP:{}:{} SIP/2.0\r\n".format(type, remoteIP, remotePort)

            sequenceRequestType = type
            if(not sequence):
                sequence = "1"

            headers["Via"] = "SIP/2.0/UDP {}:{}".format(localIP, localPort)
            headers["From"] = "<sip:IPCall@{}:{}>".format(localIP, localPort, fromTag)
            headers["To"] = "<sip:{}:{}>".format(remoteIP, remotePort, toTag)
            headers["Max-Forwards"] = "70"


        elif(type in ["100 Trying", "180 Ringing", "200 OK", "400 Bad Request", "408 Request Timeout", "486 Busy Here", "487 Request Terminated"]):
            startLine = "SIP/2.0 {}\r\n".format(type)

            if (not sequence or not sequenceRequestType):
                print("Failed to include CSeq")
                exit()
            
            headers["Via"] = "SIP/2.0/UDP {}:{}".format(remoteIP, remotePort)
            headers["From"] = "<sip:IPCall@{}:{}>".format(remoteIP, remotePort, fromTag),
            headers["To"] = "<sip:{}:{}>".format(localIP, localPort, toTag)

        else:
            print("{} Not implemented".format(type))
            exit()

        if(not branch):
            branch = Sip.BRANCH_MAGIC_COOKIE + hashlib.md5((toTag + fromTag + headers["Call-ID"] + headers["Via"] + str(sequence)).encode()).hexdigest()
        
        headers["Via"] += ";branch=" + branch
        headers["CSeq"] = "{} {}".format(sequence, sequenceRequestType)
        headers["Content-Length"] = str(len(messageBody.encode("utf-8")))

        message = startLine
        for key in headers.keys():
            message += key + ": " + headers[key] + "\r\n"

        message += "\r\n{}".format(messageBody)

        return message.encode("utf-8")


    def start(self):
        self.SIPHandlerThread.start()
        self.UDPListenerThread.start()
        self.UDPSenderThread.start()
        print("SIP service started on port: {}\n".format(self.port))

    def stop(self):
        self.halt.set()
        self.SIPHandlerThread.join()
        self.UDPListenerThread.join()
        self.UDPSenderThread.join()
        print("SIP service terminated")

    def invite(self, address, port):
        print("Attempting to intitate a call with {}:{}".format(address, port))
        # TODO send invite request to handler
        inviteRequest = SIPService._buildMessage("INVITE", ("10.13.0.23", 5060), (address, port))
        self.sendQueue.put((address, port, inviteRequest))

    def cancel(self, address, port):
        print("Call cancelled")
        # TODO send cancel request to handler

    def bye(self, address, port):
        print("Call ended")
        # TODO send bye request to handler

    def handler(self):
        while(self.halt.is_set() == False):
            try:
                (targetAddress, targetPort, data) = self.recvQueue.get(timeout=1)

                # TODO deconstruct data



                # TODO pass data to matching transaction, or create a new transaction thread if one doesn't exist (or ignore if orphaned response)
            except queue.Empty:
                continue
        
SIPService = Sip()
SIPService.start()
# SIPService.invite("10.13.0.6", 5060)

command = input()
while(command != "EXIT"):
    if(command == "INVITE"):
        SIPService.invite("Remotehost", 5060)
    elif(command == "CANCEL"):
        SIPService.cancel("Remotehost", 5060)
    elif(command == "BYE"):
        SIPService.bye("Remotehost", 5060)
    command = input()

SIPService.stop()