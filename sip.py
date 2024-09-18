import socket
import threading
import time
import random
import hashlib
import queue

PORT = 5060
READ_SIZE = 1024
SOCKET_TIMEOUT = 1

class UDP:

    def __init__(self, port, sendQueue, recvQueue, halt):
        self.port = port
        self.sendQueue = sendQueue
        self.recvQueue = recvQueue
        self.halt = halt

    def listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(SOCKET_TIMEOUT)
        sock.bind(("", self.port))

        while(self.halt.is_set() == False):
            try:
                data, (srcAddress, srcPort) = sock.recvfrom(READ_SIZE)
                # TODO implement functionality to ensure whole message content received.
                self.recvQueue.put((srcAddress, srcPort, data))
            except socket.timeout:
                continue

        sock.close()

    def sender(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while(self.halt.is_set() == False):
            try:
                (targetAddress, targetPort, data) = self.sendQueue.get(timeout=1)
                bytesSent = sock.sendto(data), (targetAddress, targetPort)
                # TODO confirm that bytes sent matches data size
            except queue.Empty:
                continue

class Transaction:

    def __init__(self, outgoingQueue, halt):
        self.incomingQueue = queue.Queue()
        self.outgoingQueue = outgoingQueue
        self.halt = halt
        #self.transactionThread = threading.Thread(target=self., args=(self.))
        # TODO continue implementing

#    def transport():
#
#    def 


class Sip:

    def __init__(self, port=5060):
        self.port = port

        self.sendQueue = queue.Queue()
        self.recvQueue = queue.Queue()
        self.halt = threading.Event()
        self.UDP = UDP(self.port, self.sendQueue, self.recvQueue, self.halt)

        self.UDPListenerThread = threading.Thread(target=self.UDP.listener)
        self.UDPSenderThread = threading.Thread(target=self.UDP.sender)
        self.SIPHandlerThread = threading.Thread(target=self.handler)

    def start(self):
        self.SIPHandlerThread.start()
        self.UDPListenerThread.start()
        self.UDPSenderThread.start()
        print("SIP service started on port: {}".format(self.port))

    def stop(self):
        self.halt.set()
        self.SIPHandlerThread.join()
        self.UDPListenerThread.join()
        self.UDPSenderThread.join()
        print("SIP service terminated")

    def invite(self, address, port):
        print("Attempting to intitate a call with {}:{}".format(address, port))
        # TODO send invite request to handler

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

                # TODO pass data to matching transaction, or create a new transaction thread if one doesn't exist (or ignore if orphaned response)
            except queue.Empty:
                continue
        
SIPService = Sip()
SIPService.start()
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

# LOCAL_IP, LOCAL_PORT = "192.168.2.12", 5060
# REMOTE_IP, REMOTE_PORT = "192.168.2.20", 5060

# method = "INVITE"
# requestLine = "{} sip:{}:{} SIP/2.0\r\n".format(method, REMOTE_IP, REMOTE_PORT)

# # TODO generate fromTag
# fromTag = hex(int(random.getrandbits(32)))[2:]

# # toTag generated by response
# toTag = ""

# callID = hex(time.time_ns())[2:] + hex(int(random.getrandbits(32)))[2:] + "@cleckie.com"

# sequence = 1

# headers = {
#     "Via": "SIP/2.0/UDP {}:{}".format(LOCAL_IP, LOCAL_PORT),
#     "From": "<sip:IPCall@{}:{}>".format(LOCAL_IP, LOCAL_PORT),
#     "To": "<sip:{}:{}>".format(REMOTE_IP, REMOTE_PORT),
#     "Call-ID": "{}".format(callID),
#     "CSeq": "{} {}".format(sequence, method),
#     "Max-Forwards": "70"
# }

# # TODO include Request-URI of the request received (before translation) in hash
# branch = "z9hG4bK" + hashlib.md5((toTag + fromTag + headers["Call-ID"] + headers["Via"] + str(sequence)).encode()).hexdigest()

# # Add branch and from tag
# headers["Via"] = headers["Via"] + ";branch=" + branch
# headers["From"] = headers["From"] + ";tag=" + fromTag


# request = requestLine

# for key in headers.keys():
#     request += key + ": " + headers[key] + "\r\n"

# print(request)

# clientSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# clientSock.bind(("", LOCAL_PORT))

# clientSock.sendto(bytes(request + "\n", "utf-8"), (REMOTE_IP, REMOTE_PORT))

# while True:
#     time.sleep(1) 
#     received, address = clientSock.recvfrom(4096)
#     print(received)