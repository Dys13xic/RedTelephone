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

class SpeakingModes:
    MICROPHONE = 1
    SOUNDSHARE = 2
    MICROPHONE_PRIORITY = 5
    SOUNDSHARE_PRIORITY = 6

class OpCodes(Enum):
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

class CloseCodes():
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

    @staticmethod
    def reconnectable(closeCode):
        if closeCode  in [CloseCodes.DISCONNECTED]:
            return False
        
        return True
        
class VoiceGateway(GatewayConnection):
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
        while True:
            try:
                await self._start()
            except websockets.exceptions.ConnectionClosedOK:
                self.disconnect()
                break
            except websockets.exceptions.ConnectionClosedError as e:                   
                if CloseCodes.reconnectable(e.code):
                    if self.attempts < 2:
                        self._stop(clean=False)
                    else:
                        self._stop(clean=True)
                        self.gateway.updateVoiceChannel(self.serverID, self.channelID)
                        break
                else:
                    self._stop(clean=True)
                    break

    async def disconnect(self):
        await super().disconnect()
        await self.gateway.updateVoiceChannel(self.serverID, None)

    def _stop(self, clean=True):
        if self.rtpEndpoint:
            self.rtpEndpoint.stop()

        super()._stop(clean)

    def _clean(self):
        super()._clean()
        self.endpoint = None
        self.ssrc = None
        self.rtpEndpoint = None

    async def processMsg(self, msgObj):
        # Update sequence number
        if(msgObj.s):
            self.lastSequence = msgObj.s

        eventName = OpCodes(msgObj.op).name
        args = []

        match msgObj.op:
            case OpCodes.HELLO.value:
                # Update heartbeat interval
                if("heartbeat_interval" in msgObj.d):
                    self.setHeartbeatInterval(msgObj.d["heartbeat_interval"])
                    
                # Identify to API
                data = {'server_id': self.serverID, 'user_id': self.gateway.userID, 'session_id': self.gateway.sessionID, 'token': self.token}
                identifyMsg = GatewayMessage(OpCodes.IDENTIFY.value, data)
                await self.send(identifyMsg)

            case OpCodes.READY.value:
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

            case OpCodes.SESSION_DESCRIPTION.value:
                self.rtpEndpoint.setSecretKey(msgObj.d['secret_key'])

            case OpCodes.SPEAKING.value:
                pass

            case OpCodes.HEARTBEAT_ACK.value:
                pass

            case OpCodes.RESUMED.value:
                self.attempts = 0
                pass

            case OpCodes.CLIENTS_CONNECT.value:
                pass

            case OpCodes.CLIENTS_DISCONNECT.value:
                pass

            case OpCodes.DAVE_PREPARE_TRANSITION.value:
                pass

            case OpCodes.DAVE_EXECUTE_TRANSITION.value:
                pass

            case OpCodes.DAVE_PREPARE_EPOCH.value:
                pass

            case OpCodes.DAVE_MLS_EXTERNAL_SENDER.value:
                pass

            case OpCodes.DAVE_MLS_PROPOSALS.value:
                pass

            case OpCodes.DAVE_MLS_ANNOUNCE_COMMIT_TRANSACTION.value:
                pass

            case OpCodes.DAVE_MLS_WELCOME.value:
                pass

            case _:
                raise ValueError("Unsupported OP code in voice_gateway msg {}".format(msgObj.op))

        # Pass to relevant event handler
        await self.eventDispatcher(eventName.lower(), *args)

    def genHeartBeat(self):
        data = {'t': VoiceGateway.genNonce(), 'seq_ack': self.lastSequence}
        return GatewayMessage(OpCodes.HEARTBEAT.value, data)
    
    async def updateSpeaking(self, speaking=SpeakingModes.MICROPHONE_PRIORITY):
        data = {'speaking': speaking, 'delay': VOICEGATEWAY_DELAY, 'ssrc': self.ssrc}
        speakingMsg = GatewayMessage(OpCodes.SPEAKING.value, data)
        await self.send(speakingMsg)

    @staticmethod
    def genNonce():
        return int.from_bytes(urandom(8))