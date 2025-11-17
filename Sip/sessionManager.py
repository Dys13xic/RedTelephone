# 1st Party
from .dialog import Dialog
from .transaction import Transaction

# Standard Library
import asyncio

class SessionManager():
    def __init__(self):
        self.activeInvite: Transaction = None
        self.activeDialog: Dialog = None
        self.isActiveDialog: asyncio.Event = asyncio.Event()
        self.answerCall: asyncio.Event = asyncio.Event()
        self.sessionStart: asyncio.Event = asyncio.Event()


    def setActiveDialog(self, dialog):
        self.activeDialog = dialog

        if dialog:
            self.isActiveDialog.set()
        else:
            self.isActiveDialog.clear()

    def getActiveDialog(self):
        pass
        

    def busy(self):
        return bool(self.activeInvite or self.activeDialog)
    
    def answerIncomingCall(self):
        self.answerCall.set()
        self.answerCall.clear()

    async def waitForAnswer(self):
        await self.answerCall.wait()

    async def waitForSession(self):
        await self.sessionStart.wait()

    def cleanup(self):
        self.activeInvite = None
        self.activeDialog = None
        self.answerCall.clear()
        self.sessionStart.clear()