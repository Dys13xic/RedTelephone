# Standard Library
from enum import Enum
import re

SIP_DEFAULT_PORT = 5060
SIP_VERSION = 'SIP/2.0'
TRANSPORT_PROTOCOL = 'UDP'

class StatusCodes(Enum):
    TRYING = 100
    RINGING = 180
    OK = 200
    MULTIPLE_CHOICES = 300
    MOVED_PERMANENTLY = 301
    MOVED_TEMPORARILY = 302
    USE_PROXY = 305
    BAD_REQUEST = 400
    REQUEST_TIMEOUT = 408
    BUSY_HERE = 486
    REQUEST_TERMINATED = 487

    @staticmethod
    def isProvisional(code):
        return 100 <= code <= 199

    @staticmethod
    def isSuccessful(code):
        return 200 <= code <= 299
    
    @staticmethod
    def isFinal(code):
        return 200 <= code <= 699

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
    viaAddress: bool
    branch: str
    fromTag: str
    toTag: str
    callID: str
    seqNum: int
    seqMethod: str
    body: str
    additionalHeaders: dict

    def __init__(self, viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders={}):
        self.viaAddress = viaAddress
        self.branch = branch
        self.fromTag = fromTag
        self.toTag = toTag
        self.callID = callID
        self.seqNum = seqNum
        self.seqMethod = seqMethod
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
                case 'Via':
                    content = content.removeprefix('{}/{} '.format(SIP_VERSION, TRANSPORT_PROTOCOL))
                    address, _ = content.split(';', 1)
                    ip, port = address.split(':')
                    port = int(port)
                    viaAddress = (ip, port)
                    branch = SipMessage._extractParameters(content, label='branch')
                case 'From':
                    fromTag = SipMessage._extractParameters(content, label='tag')
                case 'To':
                    toTag = SipMessage._extractParameters(content, label='tag')
                case 'CSeq':
                    seqNum, seqMethod = content.split(' ')
                    seqNum = int(seqNum)
                case 'Call-ID':
                    callID = content
                case _:
                    additionalHeaders[label] = content

        return cls(viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders)

    @staticmethod
    def _extractParameters(header, label):
        _, *parameters = header.split(';')
        for param in parameters:
            key, value = param.split('=')
            if label == key:
                return value
        return None
    
    # TODO Add comments to regex using re.VERBOSE
    @staticmethod
    def strIsRequest(message):
        return bool(re.match('^(INVITE|ACK|BYE|CANCEL|REGISTER|OPTIONS)\\s+sip:[^\\s]+?\\s+SIP/2\\.0', message))
    
    @staticmethod
    def strIsResponse(message):
        return bool(re.match('^SIP/2\\.0\\s+\\d{3}\\s+.*', message))

class SipRequest(SipMessage):
    method: str
    maxForwards: int

    def __init__(self, method, targetAddress, viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders, maxForwards=70):
        super().__init__(viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders)
        self.method = method
        self.targetAddress = targetAddress
        self.maxForwards = maxForwards

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
        maxForwards = temp.additionalHeaders.get('Max-Forwards', 70)

        return cls(method, targetAddress, temp.viaAddress, temp.branch, temp.fromTag, temp.toTag, temp.callID, temp.seqNum, temp.seqMethod, 
                   temp.body, temp.additionalHeaders, maxForwards)

class SipResponse(SipMessage):
    statusCode: int

    def __init__(self, statusCode, viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders):
        super().__init__(viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders)
        self.statusCode = statusCode

    @classmethod
    def fromStr(cls, message):
        temp = SipMessage.fromStr(message)
        _, statusCode, _ = message.split(' ', 2)
        statusCode = int(statusCode)
        # TODO replace with enum
        # statusCode = StatusCodes(statusCode)
        
        return cls(statusCode, temp.viaAddress, temp.branch, temp.fromTag, temp.toTag, temp.callID, temp.seqNum, temp.seqMethod, 
                   temp.body, temp.additionalHeaders)