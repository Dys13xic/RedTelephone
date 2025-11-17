# Standard Library
from enum import Enum
from dataclasses import dataclass
import re
from datetime import datetime

SIP_DEFAULT_PORT = 5060
SIP_VERSION = 'SIP/2.0'
TRANSPORT_PROTOCOL = 'UDP'

class StatusCodes(Enum):
    """Enum class of Sip response status codes."""
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
        """Return whether the status code is provisional."""
        return 100 <= self.code <= 199

    def isSuccessful(self):
        """Return whether the status code is successful."""
        return 200 <= self.code <= 299
    
    def isUnsuccessful(self):
        """Return whether the status code is unsuccessful."""
        return 300 <= self.code <= 699
        
    def isFinal(self):
        """Return whether the status code is final."""
        return 200 <= self.code <= 699

class SipMessageFactory():
    """Factory class that creates an object of the Sip Message subclass."""
    @staticmethod
    def fromStr(message):
        """Creates a Sip request or response based on the input message."""
        if SipMessage.strIsRequest(message):
            return SipRequest.fromStr(message)
        elif SipMessage.strIsResponse(message):
            return SipResponse.fromStr(message)
        else:
            raise Exception('Invalid message received')

@dataclass
class SipMessage():
    """Dataclass representation of a Sip message."""
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

    @classmethod
    def fromStr(cls, message):
        """Creates a new Sip message from the specified string. Holds shared parsing logic for child classes."""
        head, body = message.split("\r\n\r\n")
        startLine, *headers = head.split('\r\n')
        additionalHeaders = {}

        # Parse mandatory header URIs and parameters, maintain dict of non-mandatory headers
        for header in headers:
            label, content = header.split(": ", 1)
            match label:
                case 'Via':
                    # TODO add support for multiple Via headers
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
                        # If To parameters exist
                        toURI, paramStr = content.split(';', 1)
                        toParams = SipMessage._extractParameters(paramStr)
                    except ValueError:
                        toURI = content
                        toParams = {}
                case 'CSeq':
                    seqNum, method = content.split(' ')
                    seqNum = int(seqNum)
                case 'Call-ID':
                    callID = content
                case _:
                    additionalHeaders[label] = content

        # Construct and return a Sip message
        return cls(method, viaAddress, viaParams, fromURI, fromParams, toURI, toParams, callID, seqNum, body, additionalHeaders)
    
    def __str__(self):
        """Returns string representation of a Sip message. Holds shared logic for child classes."""
        headers = {}
        msg = ''
        viaIP, viaPort = self.viaAddress
        # Construct mandatory header contents from URIs and parameters
        headers['Via'] = f'{SIP_VERSION}/{TRANSPORT_PROTOCOL} {viaIP}:{viaPort}' + ''.join(f';{k}={v}' for k, v in self.viaParams.items())
        headers['From'] = self.fromURI + ''.join(f';{k}={v}' for k, v in self.fromParams.items())
        headers['To'] = self.toURI + ''.join(f';{k}={v}' for k, v in self.toParams.items())
        headers['Call-ID'] = self.callID
        headers['CSeq'] = f'{self.seqNum} {self.method}'

        # Include any non-mandatory headers
        for k, v in self.additionalHeaders.items():
            headers[k] = v
        headers["Content-Length"] = len(self.body.encode("utf-8"))

        # Combine header label and content
        for k, v in headers.items():
            msg += f'{k}: {v}\r\n'

        # Include message body
        msg += f'\r\n{self.body}'
        return msg
    
    @staticmethod
    def _extractParameters(header):
        """Helper method to retrieve key=value parameters from header URIs."""
        hashMap = {}
        parameters = header.split(';')
        for param in parameters:
            # TODO add support for parameters without a key=value format
            try:
                key, value = param.split('=')
                hashMap[key] = value
            except ValueError:
                continue

        return hashMap

    def getTransactionID(self):
        """Calculate the Sip messages' transaction ID. To be implemented by child class."""
        raise NotImplementedError
    
    def getDialogID(self):
        """Calculate the Sip messages' dialog ID. To be implemented by child class."""

    def parseSDP(self):
        """Retrieve RTP and RTCP ports from Session Description Protocol if they exist."""
        rtpPort, rtcpPort = None, None
        # Regex search for matching media description
        match = re.match('^m=audio (?P<port>[0-9]+)', self.body)
        if match and 'port' in match.groupdict():
            rtpPort = int(match.group('port'))
        # Regex search for matching media attribute
        match = re.match('^a=rtcp:(?P<port>[0-9]+)', self.body)
        if match and 'port' in match.groupdict():
            rtcpPort = int(match.group('port'))

        return rtpPort, rtcpPort
    
    @staticmethod
    def _buildSDP(localAddress, port):
        """Generates and returns a suitable SDP body."""
        # RFC 4566 recommends timestamps for session ID and version (Section 5.2)
        sessionID = datetime.now().timestamp()
        sessionVersion = sessionID
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
    
    @staticmethod
    def strIsRequest(message):
        """Returns whether the specified message is a request."""
        return bool(re.match('^(INVITE|ACK|BYE|CANCEL|REGISTER|OPTIONS)\\s+sip:[^\\s]+?\\s+SIP/2\\.0', message))
    
    @staticmethod
    def strIsResponse(message):
        """Returns whether the specified message is a response."""
        return bool(re.match('^SIP/2\\.0\\s+\\d{3}\\s+.*', message))

@dataclass
class SipRequest(SipMessage):
    """Dataclass representation of a Sip request."""
    targetAddress: tuple

    @classmethod
    def fromStr(cls, message):
        """Constructs a request object from the specified message."""
        baseMsg = SipMessage.fromStr(message)
        method, requestURI, version = message.split(' ', 2)

        # Determine if the port is included in request URI
        match = re.match('sips?:(?P<user>.*@)?(?P<ip>[^@: ]+)(:?)(?P<port>[0-9]+)?', requestURI)
        if match and 'ip' in match.groupdict():
            targetIP = match.group('ip')
            targetPort = int(match.group('port')) if 'port' in match.groupdict() else SIP_DEFAULT_PORT
        else:
            raise ValueError('Invalid Request URI.')

        targetAddress = (targetIP, targetPort)
        # Construct and return a request obj
        return cls(method, baseMsg.viaAddress, baseMsg.viaParams, baseMsg.fromURI, baseMsg.fromParams, baseMsg.toURI, baseMsg.toParams, 
                   baseMsg.callID, baseMsg.seqNum, baseMsg.body, baseMsg.additionalHeaders, targetAddress)

    @classmethod
    def ackFromResponse(cls, response):
        """Constructs an ack request object from an existing response object."""
        if 'Contact' not in response.additionalHeaders:
            raise ValueError('Response missing Contact header.')

        match = re.match('<sips?:(?P<user>.*@)?(?P<ip>[^@:]+):(?P<port>[0-9]+)?>', response.additionalHeaders['Contact'])
        if match and 'ip' in match.groupdict():
            targetIP = match.group('ip')
            targetPort = int(match.group('port')) if 'port' in match.groupdict() else SIP_DEFAULT_PORT 
            targetAddress = (targetIP, targetPort)
        else:
            raise ValueError('Invalid Contact URI')

        return cls('ACK', response.viaAddress, response.viaParams, response.fromURI, response.fromParams, response.toURI, response.toParams,
                   response.callID, response.seqNum, "", response.additionalHeaders, targetAddress)
    
    def __str__(self):
        """Returns string representation of a Sip request."""
        targetIP, targetPort = self.targetAddress
        requestLine = f'{self.method} sip:{targetIP}:{targetPort} {SIP_VERSION}\r\n'
        # Add request line to base message string
        return requestLine + super().__str__()
    
    def getTransactionID(self):
        """Calculate the Sip requests' corresponding transaction ID."""
        viaIP, viaPort = self.viaAddress

        # Matches ACKs to corresponding INVITE request
        if self.method == 'ACK':
            matchMethod = 'INVITE'
        else:
            matchMethod = self.method

        return self.viaParams['branch'] + viaIP + str(viaPort) + matchMethod
    
    def getDialogID(self):
        """Calculate the Sip request's dialog ID."""
        if 'tag' in self.toParams:
            return self.callID + self.toParams['tag'] + self.fromParams['tag']
        
        return None
    
@dataclass
class SipResponse(SipMessage):
    """Dataclass representation of a Sip response."""
    statusCode: StatusCodes

    @classmethod
    def fromStr(cls, message):
        """Constructs a response object from the specified message."""
        baseMsg = SipMessage.fromStr(message)

        # Construct a matching StatusCode enum
        statusLine, _ = message.split('\r\n', 1)
        version, code, reasonPhrase = statusLine.split(' ', 2)
        statusCode = StatusCodes(int(code), reasonPhrase)

        # Construct and return a response obj
        return cls(baseMsg.method, baseMsg.viaAddress, baseMsg.viaParams, baseMsg.fromURI, baseMsg.fromParams, baseMsg.toURI, baseMsg.toParams, 
                   baseMsg.callID, baseMsg.seqNum, baseMsg.body, baseMsg.additionalHeaders, statusCode)
        
    @classmethod
    def fromRequest(cls, request, statusCode):
        """Constructs a response object from an existing request object."""
        return cls(request.method, request.viaAddress, request.viaParams, request.fromURI, request.fromParams, request.toURI, request.toParams,
                   request.callID, request.seqNum, request.body, request.additionalHeaders, statusCode)

    def __str__(self):
        """Returns string representation of a Sip response."""
        statusLine = f'{SIP_VERSION} {self.statusCode.code} {self.statusCode.reasonPhrase}\r\n'
        # Add status line to base message string
        return statusLine + super().__str__()
    
    def getTransactionID(self):
        """Calculate the Sip response's corresponding transaction ID."""
        return self.viaParams['branch'] + self.method
    
    def getDialogID(self):
        """Calculate the Sip response's dialog ID."""
        if 'tag' in self.toParams:
            return self.callID + self.fromParams['tag'] + self.toParams['tag']
        
        return None