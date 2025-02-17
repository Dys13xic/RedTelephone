# Standard Library
from abc import ABC
import re

SIP_VERSION = 'SIP/2.0'
TRANSPORT_PROTOCOL = 'UDP'

class SipMessageFactory():
    def createSipMessageFromStr(message):
        if SipMessage.isRequest(message):
            return SipRequest.fromStr(message)
        elif SipMessage.isResponse(message):
            return SipResponse.fromStr(message)
        else:
            raise Exception('Invalid message received')

class SipMessage(ABC):
    startLine: str
    viaAddress: bool
    branch: str
    fromTag: str
    toTag: str
    callID: str
    seqNum: int
    seqMethod: str
    body: str
    additionalHeaders: dict

    def __init__(self, startLine, viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders={}):
        self.startLine = startLine
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
        startLine, *headers = head
        
        additionalHeaders = {}
        for header in headers:
            label, content = header.split(": ", 1)
            match label:
                case 'Via':
                    content.removeprefix('{}/{} '.format(SIP_VERSION, TRANSPORT_PROTOCOL))
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

        return cls(startLine, viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders)

    @staticmethod
    def _extractParameters(header, label):
        _, *parameters = header.split(';')
        for param in parameters:
            key, value = param.split('=')
            if label == key:
                return value
        return None
    
    @staticmethod
    def isRequest(message):
        return bool(re.match('^(INVITE|ACK|BYE|CANCEL|REGISTER|OPTIONS)\s+sip:[^\s]+?\s+SIP/2\.0$', message))
    
    @staticmethod
    def isResponse(message):
        return bool(re.match('^SIP/2\.0\s+\d{3}\s+.*$', message))

class SipRequest(SipMessage):
    method: str
    maxForwards: int

    def __init__(self, method, body, branch, fromTag, toTag, callID, seqNum, seqMethod, localAddr, remoteAddr, maxForwards=70):
        super().__init__(body, branch, fromTag, toTag, callID, seqNum, seqMethod, localAddr, remoteAddr)
        self.method = method
        self.maxForwards = maxForwards

    @classmethod
    def fromStr(cls, message):
        request = super().toStr(message)
        request.method = request.startLine.split(' ', 1)
        request.maxForwards = request.additionalHeaders.get('Max-Forwards', default=70)
        return request

class SipResponse(SipMessage):
    statusCode: int

    def __init__(self, statusCode, body, branch, fromTag, toTag, callID, seqNum, seqMethod, localAddr, remoteAddr, maxForwards=70):
        super().__init__(body, branch, fromTag, toTag, callID, seqNum, seqMethod, localAddr, remoteAddr)
        self.statusCode = statusCode

    @classmethod
    def fromStr(cls, message):
        response = super().toStr(message)
        _, statusCode, _ = response.startLine.split(' ', 2)
        response.statusCode = int(statusCode)