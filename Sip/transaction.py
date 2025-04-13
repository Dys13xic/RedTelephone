# 1st Party
from .dialog import Dialog

# Standard Library
import asyncio
import random
from collections.abc import Callable
from enum import Enum

class States(Enum):
    """Enum class of Transaction states."""
    TRYING = 0,
    CALLING = 1,
    PROCEEDING = 2,
    COMPLETED = 3,
    CONFIRMED = 4,
    TERMINATED = 5

class Transaction:
    '''Manage the state of a SIP request and corresponding response across many independent messages.'''
    # Type Hints
    notifyTU: Callable
    sendToTransport: Callable
    requestMethod: str
    localIP: str
    localPort: int
    remoteIP: str
    remotePort: int
    dialog: Dialog
    recvQueue: asyncio.Queue
    id: str
    state: States
    fromTag: str
    toTag: str
    callID: str
    branch: str
    sequence: int

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
        """Terminate the current session and remove from _transactions."""
        self.state = States.TERMINATED
        del self._transactions[self.id]

    def _genTag(self):
        """Generates and returns a suitable SIP from/to tag."""
        return hex(int(random.getrandbits(32)))[2:]

    @staticmethod
    def getTransaction(id):
        """Returns a transaction with matching ID from _transactions or None if one does not exist."""
        return Transaction._transactions.get(id, None)