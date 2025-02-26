# TODO this constant is defined in sip.py (shouldn't need to be in both places)
RTP_PORT = 5004

class Dialog():
    _dialogs: dict = {}

    def __init__(self, callID, localTag, localURI, localSeq, remoteTag, remoteURI, remoteTarget, remoteSeq=None, rtpPort = RTP_PORT, rtcpPort = RTP_PORT + 1):
        # self.state = state
        # self.role = role
        self.callID = callID
        self.localTag = localTag
        self.remoteTag = remoteTag
        self.id = self.callID + self.localTag + self.remoteTag
        self.localSeq = localSeq
        self.remoteSeq = remoteSeq
        self.localURI = localURI
        self.remoteURI = remoteURI
        self.remoteTarget = remoteTarget
        #self.secure = secure
        #self.routeSet = routeSet
        # TODO should rtpPort and rtcpPort be moved to a different session obj?
        self.rtpPort = rtpPort
        self.rtcpPort = rtcpPort

        Dialog._dialogs[self.id] = self

    # TODO Clean up the way this method operates
    def getRemoteIP(self):
        _, remoteIP, _ = self.remoteURI.split(':', 2)
        return remoteIP
    
    def getRtpPorts(self):
        return self.rtpPort, self.rtcpPort
    
    def terminate(self):
        del self._dialogs[self.id]

    @staticmethod
    def getDialog(id):
        if id in Dialog._dialogs:
            return Dialog._dialogs[id]
        else:
            return None