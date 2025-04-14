class Dialog():
    """Maintains the state of a SIP dialog across multiple transactions."""
    _dialogs: dict = {}

    def __init__(self, callID, localTag, localURI, localSeq, remoteTag, remoteURI, remoteTarget, remoteSeq=None):
        self.callID: str = callID
        self.localTag: str = localTag
        self.remoteTag: str= remoteTag
        self.id: str = self.callID + self.localTag + self.remoteTag
        self.localSeq: int = localSeq
        self.remoteSeq: int  = remoteSeq
        self.localURI: str = localURI
        self.remoteURI: str = remoteURI
        self.remoteTarget: str = remoteTarget
        self.secure: bool = False
        #self.routeSet = routeSet

        # Register new Dialog
        Dialog._dialogs[self.id] = self

    def getRemoteIP(self):
        """Returns the dialog's remote IP."""
        _, remoteIP, _ = self.remoteURI.split(':', 2)
        return remoteIP
    
    def terminate(self):
        """Terminate the current dialog and remove from dialogs list."""
        del self._dialogs[self.id]

    @staticmethod
    def getDialog(id):
        """Returns a dialog with matching ID from dialogs list or None if one does not exist."""
        return Dialog._dialogs.get(id, None)