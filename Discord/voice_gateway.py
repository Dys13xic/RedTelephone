# 1st Party
from .gateway_connection import GatewayConnection, GatewayMessage
from .gateway import Gateway
from Utils.events import EventHandler
from rtp import RtpEndpoint

# 3rd Party
import websockets

# Standard Library
import asyncio
from os import urandom
from enum import Enum

DISCORD_RTP_PORT = 5003
VOICEGATEWAY_DELAY = 0
RECONNECT_ATTEMPTS = 2

class SpeakingModes(Enum):
    """Enum class of speaking modes for SPEAKING voice gateway messages."""
    MICROPHONE = 1
    SOUNDSHARE = 2
    MICROPHONE_PRIORITY = 5
    SOUNDSHARE_PRIORITY = 6

class OpCodes(Enum):
    """Enum class of sent/received voice gateway message OpCodes."""
    IDENTIFY = 0
    SELECT_PROTOCOL = 1
    READY = 2
    HEARTBEAT = 3
    SESSION_DESCRIPTION = 4
    SPEAKING = 5
    HEARTBEAT_ACK = 6
    RESUME = 7
    HELLO = 8
    RESUMED = 9
    CLIENTS_CONNECT = 11
    CLIENTS_DISCONNECT = 13
    DAVE_PREPARE_TRANSITION = 21
    DAVE_EXECUTE_TRANSITION = 22
    DAVE_TRANSITION_READY = 23
    DAVE_PREPARE_EPOCH = 24
    DAVE_MLS_EXTERNAL_SENDER = 25
    DAVE_MLS_KEY_PACKAGE = 26
    DAVE_MLS_PROPOSALS = 27
    DAVE_MLS_COMMIT_WELCOME = 28
    DAVE_MLS_ANNOUNCE_COMMIT_TRANSACTION = 29
    DAVE_MLS_WELCOME = 30
    DAVE_MLS_INVALID_COMMIT_WELCOME = 31

class CloseCodes(Enum):
    """Enum class of voice gateway close codes."""
    UNKNOWN_OPCODE = 4001
    FAILED_TO_DECODE_PAYLOAD = 4002
    NOT_AUTHENTICATED = 4003
    AUTHENTICATION_FAILED = 4004
    ALREADY_AUTHENTICATED = 4005
    SESSION_NO_LONGER_VALID = 4006
    SESSION_TIMEOUT = 4009
    SERVER_NOT_FOUND = 4011
    UNKNOWN_PROTOCOL = 4012
    DISCONNECTED = 4014
    VOICE_SERVER_CRASHED = 4015
    UNKNOWN_ENCRYPTION_MODE = 4016
    BAD_REQUEST = 4020

    def reconnectable(self):
        """Returns whether the specified gateway close code allows reconnection."""
        if self in [CloseCodes.DISCONNECTED]:
            return False
        
        return True
        
class VoiceGateway(GatewayConnection):
    """Manage voice gateway state and handling of incoming/outgoing gateway messages."""
    gateway: Gateway
    serverID: str
    channelID: str
    eventDispatcher: EventHandler.dispatch
    token: str
    endpoint: str
    ssrc: int
    rtpEndpoint: RtpEndpoint

    def __init__(self, gateway, serverID, channelID, eventDispatcher):
        self.gateway = gateway
        self.serverID = serverID
        self.channelID = channelID
        self.eventDispatcher = eventDispatcher
        self.token = None
        self.endpoint = None
        self.ssrc = None
        self.rtpEndpoint = None
        super().__init__(self.token, self.endpoint)

    async def connect(self):
        """Establish a voice gateway connection and attempt to reconnect on unexpected websocket close."""
        while True:
            try:
                await self._start()
            except websockets.exceptions.ConnectionClosedOK:
                break
            except websockets.exceptions.ConnectionClosedError as e:                   
                if CloseCodes(e.code).reconnectable():
                    # Try to resume the existing voice session
                    if self.attempts < RECONNECT_ATTEMPTS:
                        self._stop(clean=False)
                    # Negotiate a new voice session
                    else:
                        self._stop(clean=True)
                        self.gateway.updateVoiceChannel(self.channelID, self.serverID)
                        break
                else:
                    self._stop(clean=True)
                    break

    def _stop(self, clean=True):
        """Sever the voice gateway connection and voice RTP endpoint."""
        if self.rtpEndpoint:
            self.rtpEndpoint.stop()
            self.rtpEndpoint = None

        super()._stop(clean)

    def _clean(self):
        """Revert session specific properties."""
        super()._clean()
        self.endpoint = None
        self.ssrc = None
        self.rtpEndpoint = None

    async def processMsg(self, msgObj):
        """Process incoming gateway messages."""
        # Update sequence number
        if(msgObj.s):
            self.lastSequence = msgObj.s

        eventName = OpCodes(msgObj.op).name
        args = []

        match OpCodes(msgObj.op):
            case OpCodes.HELLO:
                # Update heartbeat interval
                if("heartbeat_interval" in msgObj.d):
                    self.setHeartbeatInterval(msgObj.d["heartbeat_interval"])
                    
                # Identify to API
                data = {'server_id': self.serverID, 'user_id': self.gateway.userID, 'session_id': self.gateway.sessionID, 'token': self.token}
                identifyMsg = GatewayMessage(OpCodes.IDENTIFY.value, data)
                await self.send(identifyMsg)

            case OpCodes.READY:
                self.ssrc = msgObj.d['ssrc']
                remoteIP = msgObj.d['ip']
                remotePort = msgObj.d['port']

                # Establish an RTP endpoint for voice data
                loop = asyncio.get_event_loop()
                _, endpoint = await loop.create_datagram_endpoint(
                    lambda: RtpEndpoint(ssrc=self.ssrc, encrypted=True),
                    local_addr=("0.0.0.0", DISCORD_RTP_PORT),
                    remote_addr=(remoteIP, remotePort)
                )
                self.rtpEndpoint = endpoint
            
                await self.rtpEndpoint.recvPublicIP.wait()
                data = {'protocol': 'udp', 'data': {'address': self.rtpEndpoint.publicIP, 'port': DISCORD_RTP_PORT, 'mode': 'aead_xchacha20_poly1305_rtpsize'}}
                selectMsg = GatewayMessage(OpCodes.SELECT_PROTOCOL.value, data)
                await self.send(selectMsg)

            case OpCodes.SESSION_DESCRIPTION:
                self.rtpEndpoint.setSecretKey(msgObj.d['secret_key'])

            # TODO is timer needed to verify heartbeat ack and connection still open?
            case OpCodes.HEARTBEAT_ACK:
                pass

            case OpCodes.RESUMED:
                self.attempts = 0

            case _:
                pass

        # Pass to relevant event handler
        await self.eventDispatcher(eventName.lower(), *args)

    async def updateSpeaking(self, speaking=SpeakingModes.MICROPHONE_PRIORITY.value):
        """Update the bot's current speaking mode"""
        data = {'speaking': speaking, 'delay': VOICEGATEWAY_DELAY, 'ssrc': self.ssrc}
        speakingMsg = GatewayMessage(OpCodes.SPEAKING.value, data)
        await self.send(speakingMsg)

    def genHeartBeat(self):
        """Generate a heartbeat gateway message."""
        data = {'t': VoiceGateway._genNonce(), 'seq_ack': self.lastSequence}
        return GatewayMessage(OpCodes.HEARTBEAT.value, data)

    @staticmethod
    def _genNonce():
        """Generate a random nonce."""
        return int.from_bytes(urandom(8))