# 1st Party
from .gateway_connection import GatewayConnection, GatewayMessage
from .gateway import Gateway
from events import EventHandler
from rtp import RtpEndpoint

# 3rd Party
import websockets

# Standard Library
import asyncio
from os import urandom
from enum import Enum

DISCORD_RTP_PORT = 5003
SOURCE_IP = '64.231.153.189'
SOURCE_PORT = 5003


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

class VoiceGateway(GatewayConnection):
    gateway: Gateway
    serverID: str
    channelID: str
    eventDispatcher: EventHandler.dispatch
    token: str
    endpoint: str
    ssrc: int
    RTPEndpoint: RtpEndpoint

    def __init__(self, gateway, serverID, channelID, eventDispatcher):
        self.gateway = gateway
        self.serverID = serverID
        self.channelID = channelID
        self.eventDispatcher = eventDispatcher
        self.token = None
        self.endpoint = None
        self.ssrc = None
        self.RTPEndpoint = None
        super().__init__(self.token, self.endpoint)

    def getRTPEndpoint(self):
        return self.RTPEndpoint

    async def connect(self):
        await self._start()

    async def disconnect(self):
        self._stop()
        self.RTPEndpoint.stop()
        self.RTPEndpoint = None
        await self.gateway.signalVoiceChannelJoin(self.serverID, None)

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
                data = {'server_id': self.serverID, 'user_id': self.gateway.getUserID(), 'session_id': self.gateway.getSessionID(), 'token': self.token}
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
                self.RTPEndpoint = endpoint
            
                # TODO Establish UDP socket for RTP and peform IP discovery
                # IOT replace local address info
                data = {'protocol': 'udp', 'data': {'address': SOURCE_IP, 'port': SOURCE_PORT, 'mode': 'aead_xchacha20_poly1305_rtpsize'}}
                selectMsg = GatewayMessage(OpCodes.SELECT_PROTOCOL.value, data)
                await self.send(selectMsg)

            case OpCodes.SESSION_DESCRIPTION.value:
                self.RTPEndpoint.setSecretKey(msgObj.d['secret_key'])

                data = {'speaking': 5, 'delay': 0, 'ssrc': self.ssrc}
                speakingMsg = GatewayMessage(OpCodes.SPEAKING.value, data)
                await self.send(speakingMsg)

            case OpCodes.SPEAKING.value:
                pass

            case OpCodes.HEARTBEAT_ACK.value:
                pass

            case OpCodes.RESUMED.value:
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

    @staticmethod
    def genNonce():
        return int.from_bytes(urandom(8))