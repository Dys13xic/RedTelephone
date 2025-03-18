import asyncio
import random

class Transaction:
    # Constants
    BRANCH_MAGIC_COOKIE = "z9hG4bK"
    T1 = 0.5
    T2 = 4
    T4 = 5
    ANSWER_DUPLICATES_DURATION = 32

    # Static Vars
    _transactions: dict = {}

    def __init__(self, notifyTU, sendToTransport, requestMethod, localAddress, remoteAddress, dialog):
        self.notifyTU = notifyTU
        self.sendToTransport = sendToTransport
        self.requestMethod = requestMethod
        self.localIP, self.localPort = localAddress
        self.remoteIP, self.remotePort = remoteAddress
        self.dialog = dialog
        self.recvQueue = asyncio.Queue()
        self.id = None
        self.state = None

        self.fromTag = None
        self.toTag = None
        self.callID = None
        self.branch = None
        self.sequence = None
            
    def terminate(self):
        self.state = "Terminated"
        del self._transactions[self.id]

    def _genTag(self):
        return hex(int(random.getrandbits(32)))[2:]

    @staticmethod
    def getTransaction(id):
        if id in Transaction._transactions:
            return Transaction._transactions[id]
        else:
            return None