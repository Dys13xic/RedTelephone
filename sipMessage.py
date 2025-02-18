# Standard Library
from enum import Enum
import re

SIP_VERSION = 'SIP/2.0'
TRANSPORT_PROTOCOL = 'UDP'

class MessageType(Enum):
    REQUEST = "Request"
    RESPONSE = "Response"

# class SipMessageFactory():

#     @staticmethod
#     def createFromStr(message):
#         if SipMessage.isRequest(message):
#             return SipRequest.fromStr(message)
#         elif SipMessage.isResponse(message):
#             return SipResponse.fromStr(message)
#         else:
#             raise Exception('Invalid message received')

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

    def __init__(self, method, statusCode, viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders={}):
        if not bool(method) ^ bool(statusCode):
            raise Exception('Message must include either a response statusCode or request method.')
        
        self.method = method
        self.statusCode = statusCode
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

        method, statusCode = None, None
        if SipMessage.strIsRequest(startLine):
            method, _ = startLine.split(' ', 1)
        elif SipMessage.strIsResponse(startLine):
            _, statusCode, _ = message.split(' ', 2)
            statusCode = int(statusCode)
        else:
            raise Exception('Message is neither a valid request nor response.')
        
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

        return cls(method, statusCode, viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders)

    def getType(self):
        if self.method:
            return MessageType.REQUEST
        elif self.statusCode:
            return MessageType.RESPONSE
        else:
            return None

    @staticmethod
    def _extractParameters(header, label):
        _, *parameters = header.split(';')
        for param in parameters:
            key, value = param.split('=')
            if label == key:
                return value
        return None
    
    @staticmethod
    def strIsRequest(message):
        return bool(re.match('^(INVITE|ACK|BYE|CANCEL|REGISTER|OPTIONS)\\s+sip:[^\\s]+?\\s+SIP/2\\.0', message))
    
    @staticmethod
    def strIsResponse(message):
        return bool(re.match('^SIP/2\\.0\\s+\\d{3}\\s+.*', message))

# class SipRequest(SipMessage):
#     method: str
#     maxForwards: int

#     # def __init__(self, method, body, branch, fromTag, toTag, callID, seqNum, seqMethod, localAddr, remoteAddr, maxForwards=70):
#     def __init__(self, viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders, method, maxForwards=70):
#         super().__init__(viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders)
#         self.method = method
#         self.maxForwards = maxForwards

#     @classmethod
#     def fromStr(cls, message):
#         request = super().fromStr(message)
#         request.method, _ = message.split(' ', 1)
#         request.maxForwards = request.additionalHeaders.get('Max-Forwards', default=70)
#         return request

# class SipResponse(SipMessage):
#     statusCode: int

#     # def __init__(self, statusCode, body, branch, fromTag, toTag, callID, seqNum, seqMethod, localAddr, remoteAddr, maxForwards=70):
#     def __init__(self, viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders, statusCode):
#         super().__init__(viaAddress, branch, fromTag, toTag, callID, seqNum, seqMethod, body, additionalHeaders)
#         self.statusCode = statusCode

#     @classmethod
#     def fromStr(cls, message):
#         response = super().fromStr(message)
#         _, statusCode, _ = message.split(' ', 2)
#         response.statusCode = int(statusCode)