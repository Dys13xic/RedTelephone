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
    """Manage the state of a SIP request and corresponding response across many independent messages."""
    # Constants
    BRANCH_MAGIC_COOKIE = "z9hG4bK"
    T1 = 0.5
    T2 = 4
    T4 = 5
    ANSWER_DUPLICATES_DURATION = 32

    # Static Vars
    _transactions: dict = {}

    def __init__(self, notifyTU, sendToTransport, requestMethod, localAddress, remoteAddress, dialog):
        self.notifyTU: Callable = notifyTU
        self.sendToTransport: Callable = sendToTransport
        self.requestMethod: str = requestMethod
        self.localIP, self.localPort = localAddress
        self.remoteIP, self.remotePort = remoteAddress
        self.dialog: Dialog = dialog
        self.recvQueue: asyncio.Queue = asyncio.Queue()
        self.id: str = None
        self.state: States = None
        self.fromTag: str = None
        self.toTag: str = None
        self.callID: str = None
        self.branch: str = None
        self.sequence: int = None
            
    def terminate(self):
        """Terminate the current session and remove from transactions list."""
        self.state = States.TERMINATED
        del self._transactions[self.id]

    def _genTag(self):
        """Generates and returns a suitable SIP from/to tag."""
        return hex(int(random.getrandbits(32)))[2:]

    @staticmethod
    def getTransaction(id):
        """Returns a transaction with matching ID from transactions list or None if one does not exist."""
        return Transaction._transactions.get(id, None)