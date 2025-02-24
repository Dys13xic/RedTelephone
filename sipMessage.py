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

        sdp = """v=0
o=Hotline {} {} IN IP4 {}\r
s=SIP Call\r
c=IN IP4 {}\r
t=0 0\r
m=audio {} RTP/AVP 120\r
a=sendrecv\r
a=rtpmap:120 opus/48000/2\r
a=ptime:20\r\n""".format(sessionID, sessionVersion, localAddress, localAddress, port)
        #a=fmtp:120\r

        return sdp

    # TODO fix this up and incorporate into class properly
    @staticmethod
    def _buildMessage(type, localAddress, remoteAddress, branch, callID, sequence, sequenceRequestType, fromTag, toTag="", messageBody=""):

        (localIP, localPort) = localAddress
        (remoteIP, remotePort) = remoteAddress

        if(fromTag):
            fromTag = ';tag=' + fromTag

        if(toTag):
            if type == '100 Trying':
                toTag = ''
            else:
                toTag = ";tag=" + toTag

        # TODO may need to handle ;received            
        headers = {"Call-ID": callID}

        if(type in ["INVITE", "ACK", "CANCLE", "BYE"]):            
            startLine = "{} SIP:{}:{} SIP/2.0\r\n".format(type, remoteIP, remotePort)
            headers["Via"] = "SIP/2.0/UDP {}:{}".format(localIP, localPort)
            headers["From"] = "<sip:IPCall@{}:{}>{}".format(localIP, localPort, fromTag)
            headers["To"] = "<sip:{}:{}>{}".format(remoteIP, remotePort, toTag)
            headers["Max-Forwards"] = "70"
            if type == "INVITE":
                headers['Contact'] = '<sip:IPCall@{}>'.format(localIP)   # TODO I think we'd need the public ip for a request outside of LAN
            # elif type == "ACK":
            #     sequenceRequestType = "INVITE"
            else:
                sequenceRequestType = type

        elif(type in ["100 Trying", "180 Ringing", "200 OK", "400 Bad Request", "408 Request Timeout", "486 Busy Here", "487 Request Terminated"]):
            startLine = "SIP/2.0 {}\r\n".format(type)
            headers["Via"] = "SIP/2.0/UDP {}:{}".format(remoteIP, remotePort)
            headers["From"] = "<sip:IPCall@{}:{}>{}".format(remoteIP, remotePort, fromTag)
            headers["To"] = "<sip:{}:{}>{}".format(localIP, localPort, toTag)

            if type != '100 Trying':
                headers['Contact'] = '<sip:{}:{}>'.format(localIP, localPort)

        else:
            print("{} Not implemented".format(type))
            exit()
        
        headers["Via"] += ";branch=" + branch
        headers["CSeq"] = "{} {}".format(sequence, sequenceRequestType)

        if(messageBody):
            headers['Content-Type'] = "application/sdp"

        headers["Content-Length"] = str(len(messageBody.encode("utf-8")))

        # Build message
        message = startLine
        for key in headers.keys():
            message += key + ": " + headers[key] + "\r\n"

        message += "\r\n{}".format(messageBody)
        return message.encode("utf-8")


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