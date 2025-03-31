# Standard Library
from enum import Enum
import re

SIP_DEFAULT_PORT = 5060
SIP_VERSION = 'SIP/2.0'
TRANSPORT_PROTOCOL = 'UDP'

class StatusCodes(Enum):
    TRYING = (100, 'Trying')
    RINGING = (180, 'Ringing')
    OK = (200, 'OK')
    MULTIPLE_CHOICES = (300, 'Multiple Choices')
    MOVED_PERMANENTLY = (301, 'Moved Permanently')
    MOVED_TEMPORARILY = (302, 'Moved Temporarily')
    USE_PROXY = (305, 'Use Proxy')
    BAD_REQUEST = (400, 'Bad Request')
    FORBIDDEN = (403, 'Forbidden')
    REQUEST_TIMEOUT = (408, 'Request Timeout')
    BUSY_HERE = (486, 'Busy Here')
    REQUEST_TERMINATED = (487, 'Request Terminated')
    SERVER_TIMEOUT = (504, 'Server Time-out')

    def __init__(self, code, reasonPhrase):
        self.code = code
        self.reasonPhrase = reasonPhrase

    def isProvisional(self):
        return 100 <= self.code <= 199

    def isSuccessful(self):
        return 200 <= self.code <= 299
    
    def isUnsuccessful(self):
        return 300 <= self.code <= 699
        
    def isFinal(self):
        return 200 <= self.code <= 699


class SipMessageFactory():
    @staticmethod
    def createFromStr(message):
        if SipMessage.strIsRequest(message):
            return SipRequest.fromStr(message)
        elif SipMessage.strIsResponse(message):
            return SipResponse.fromStr(message)
        else:
            raise Exception('Invalid message received')


class SipMessage():
    method: str
    viaAddress: tuple
    viaParams: dict
    fromURI: str
    fromParams: dict
    toURI: str
    toParams: dict
    callID: str
    seqNum: int
    body: str
    additionalHeaders: dict

    def __init__(self, method, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, callID, seqNum, body, additionalHeaders):
        self.method = method
        self.viaAddress = viaAddress
        self.viaParams = viaParams
        self.fromURI = fromURI
        self.fromParams = fromParams
        self.toURI = toURI
        self.toParams = toParams
        self.callID = callID
        self.seqNum = seqNum
        self.body = body
        self.additionalHeaders = additionalHeaders

    @classmethod
    def fromStr(cls, message):
        head, body = message.split("\r\n\r\n")
        startLine, *headers = head.split('\r\n')
        
        additionalHeaders = {}
        for header in headers:
            label, content = header.split(": ", 1)
            match label:
                # TODO add support for multiple Via headers
                case 'Via':
                    content = content.removeprefix(f'{SIP_VERSION}/{TRANSPORT_PROTOCOL} ')
                    address, paramStr = content.split(';', 1)
                    ip, port = address.split(':')
                    viaAddress = (ip, int(port))
                    viaParams = SipMessage._extractParameters(paramStr)
                case 'From':
                    fromURI, paramStr = content.split(';', 1)
                    fromParams = SipMessage._extractParameters(paramStr)
                case 'To':
                    try:
                        toURI, paramStr = content.split(';', 1)
                        toParams = SipMessage._extractParameters(paramStr)
                    except Exception:
                        toURI = content
                        toParams = {}
                case 'CSeq':
                    seqNum, method = content.split(' ')
                    seqNum = int(seqNum)
                case 'Call-ID':
                    callID = content
                case _:
                    additionalHeaders[label] = content

        return cls(method, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, callID, seqNum, body, additionalHeaders)
    
    def __str__(self):
        headers = {}
        msg = ''
        
        viaIP, viaPort = self.viaAddress
        headers['Via'] = f'{SIP_VERSION}/{TRANSPORT_PROTOCOL} {viaIP}:{viaPort}' + ''.join(f';{k}={v}' for k, v in self.viaParams.items())
        headers['From'] = self.fromURI + ''.join(f';{k}={v}' for k, v in self.fromParams.items())
        headers['To'] = self.toURI + ''.join(f';{k}={v}' for k, v in self.toParams.items())
        headers['Call-ID'] = self.callID
        headers['CSeq'] = f'{self.seqNum} {self.method}'
        for k, v in self.additionalHeaders.items():
            headers[k] = v
        headers["Content-Length"] = len(self.body.encode("utf-8"))

        for k, v in headers.items():
            msg += f'{k}: {v}\r\n'
        
        msg += f'\r\n{self.body}'
        return msg
    
    def getTransactionID(self):
        raise NotImplementedError

    @staticmethod
    def _extractParameters(header):
        hashMap = {}
        parameters = header.split(';')
        for param in parameters:
            # TODO add support for params without a key=value relationship
            try:
                key, value = param.split('=')
                hashMap[key] = value
            except:
                continue

        return hashMap
    
    # TODO Add comments to regex using re.VERBOSE
    @staticmethod
    def strIsRequest(message):
        return bool(re.match('^(INVITE|ACK|BYE|CANCEL|REGISTER|OPTIONS)\\s+sip:[^\\s]+?\\s+SIP/2\\.0', message))
    
    @staticmethod
    def strIsResponse(message):
        return bool(re.match('^SIP/2\\.0\\s+\\d{3}\\s+.*', message))

    # TODO fix this up and incorporate into class properly
    @staticmethod
    def _parseSDP(messageBody):
        rtpPort, rtcpPort = None, None
        fields = messageBody.split('\r\n')

        # TODO clean up this brutal parsing code
        for f in fields:
            if f.startswith('m=audio'):
                args = f.split(' ')
                rtpPort = int(args[1])

            elif f.startswith('a=rtcp:'):
                firstArg, _ = f.split(' ', 1)
                rtcpPort = int(firstArg[len('a=rtcp:'):])

        return rtpPort, rtcpPort
    
    # TODO fix this up and incorporate into class properly
    @staticmethod
    def _buildSDP(localAddress, port):
        #TODO make session id and version unique
        sessionID = 8000
        sessionVersion = 8000

        sdp = f"""v=0
o=Hotline {sessionID} {sessionVersion} IN IP4 {localAddress}\r
s=SIP Call\r
c=IN IP4 {localAddress}\r
t=0 0\r
m=audio {port} RTP/AVP 120\r
a=sendrecv\r
a=rtpmap:120 opus/48000/2\r
a=ptime:20\r\n"""

        return sdp


class SipRequest(SipMessage):
    method: str
    targetAddress: tuple

    def __init__(self, method, targetAddress, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, callID, seqNum, body='', additionalHeaders={}):
        super().__init__(method, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, callID, seqNum, body, additionalHeaders)
        self.targetAddress = targetAddress

    @classmethod
    def fromStr(cls, message):
        temp = SipMessage.fromStr(message)
        method, requestURI, _ = message.split(' ', 2)
        # TODO find a better way to check if port is included (or explore adding comments to regex using re.VERBOSE)
        if re.match("^sip:(?:[a-zA-Z0-9_.!~*'()-]+)@(?:[a-zA-Z0-9.-]+):\\d", requestURI):
            _, targetIP, targetPort = requestURI.split(':')
        else:
            _, targetIP = requestURI.split(':', 1)
            targetPort = SIP_DEFAULT_PORT

        targetAddress = (targetIP, int(targetPort))
        return cls(method, targetAddress, temp.viaAddress, temp.viaParams, temp.fromURI, temp.fromParams, temp.toURI, temp.toParams, 
                   temp.callID, temp.seqNum, temp.body, temp.additionalHeaders)
    
    def __str__(self):
        # TODO what about in instances where the client doesn't supply the port (due to it matching SIP default)?
        targetIP, targetPort = self.targetAddress
        requestLine = f'{self.method} sip:{targetIP}:{targetPort} {SIP_VERSION}\r\n'
        return requestLine + super().__str__()
    
    def getTransactionID(self):
        viaIP, viaPort = self.viaAddress

        if self.method == 'ACK':
            matchMethod = 'INVITE'
        else:
            matchMethod = self.method

        return self.viaParams['branch'] + viaIP + str(viaPort) + matchMethod
    

class SipResponse(SipMessage):
    statusCode: StatusCodes

    def __init__(self, statusCode, method, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, callID, seqNum, body='', additionalHeaders={}):
        super().__init__(method, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, callID, seqNum, body, additionalHeaders)
        self.statusCode = statusCode

    @classmethod
    def fromStr(cls, message):
        temp = SipMessage.fromStr(message)
        statusLine, _ = message.split('\r\n', 1)
        version, code, reasonPhrase = statusLine.split(' ', 2)
        statusCode = StatusCodes(int(code), reasonPhrase)
        
        return cls(statusCode, temp.method, temp.viaAddress, temp.viaParams, temp.fromURI, temp.fromParams, temp.toURI, temp.toParams, temp.callID, temp.seqNum, temp.body, temp.additionalHeaders)
    
    # @classmethod
    # def fromRequest(cls, request, responseCode, toTag=None, body='', additionalHeaders={}):
    #     # TODO what about 200 OK response where a body is expected?
    #     toParamsCopy = request.fromParams.copy()
    #     if toTag:
    #         toParamsCopy['tag'] = toTag
    #     return cls(responseCode, request.method, request.viaAddress, request.viaParams, request.fromURI, request.fromParams, request.toURI, toParamsCopy, request.callID, request.seqNum, body, additionalHeaders)    
    
    def __str__(self):
        statusLine = f'{SIP_VERSION} {self.statusCode.code} {self.statusCode.reasonPhrase}\r\n'
        return statusLine + super().__str__()
    
    def getTransactionID(self):
        return self.viaParams['branch'] + self.method