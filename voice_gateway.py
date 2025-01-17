# 1st Party
from gateway_connection import GatewayConnection, GatewayMessage

# Standard Library
import asyncio
from os import urandom
from enum import Enum

SOURCE_IP = '69.156.219.180'
SOURCE_PORT = 5004


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

class VoiceGateway(GatewayConnection):
    _eventListeners: dict = {}
    ssrc: int = None

    def __init__(self, userID=None, serverID=None, token=None, endpoint=None, sessionID=None):
        super().__init__(token, endpoint)
        self._userID = userID
        self._serverID = serverID
        self._sessionID = sessionID

    def lateInit(self, userID, serverID, token, endpoint, sessionID):
        self.setToken(token)
        self.setEndpoint(endpoint)
        self._userID = userID
        self._serverID = serverID
        self._sessionID = sessionID

    def eventHandler(self, func):
        def wrapper(instanceSelf, *args, **kwargs):
            return func(instanceSelf, *args, **kwargs)
        
        self._eventListeners[func.__name__] = wrapper
        return wrapper

    async def processMsg(self, msgObj):
        # Update sequence number
        # Note: unlike the standard gateway, there isn't just one OpCode that contains sequence numbers
        if(msgObj.s):
            self.setLastSequence(msgObj.s)

        match msgObj.op:

            case OpCodes.READY.value:
                try:
                    # TODO add check for modes containing: aead_xchacha20_poly1305_rtpsize
                    self.ssrc = msgObj.d['ssrc']
                    ip = msgObj.d['ip']
                    port = msgObj.d['port']
                    modes = msgObj.d['modes']
                except Exception as e:
                    print(e)
                    await self._stop()

                # TODO Establish UDP socket for RTP and peform IP discovery
                # TODO replace local address info
                data = {'protocol': 'udp', 'data': {'address': SOURCE_IP, 'port': SOURCE_PORT, 'mode': 'aead_xchacha20_poly1305_rtpsize'}}
                selectMsg = GatewayMessage(OpCodes.SELECT_PROTOCOL.value, data)
                try:
                    await self.send(selectMsg)
                except Exception as e:
                    print(e)
            
            case OpCodes.SESSION_DESCRIPTION.value:
                data = {'speaking': 1, 'delay': 0, 'ssrc': self.ssrc}
                speakingMsg = GatewayMessage(OpCodes.SPEAKING.value, data)
                try:
                    await self.send(speakingMsg)
                except Exception as e:
                    print(e)

            case OpCodes.SPEAKING.value:
                pass

            case OpCodes.HEARTBEAT_ACK.value:
                pass

            case OpCodes.HELLO.value:
                # Update heartbeat interval
                if("heartbeat_interval" in msgObj.d):
                    self.setHeartbeatInterval(msgObj.d["heartbeat_interval"])
                    
                # Identify to API
                data = {'server_id': self._serverID, 'user_id': self._userID, 'session_id': self._sessionID, 'token': self.token}
                identifyMsg = GatewayMessage(OpCodes.IDENTIFY.value, data)
                await self.send(identifyMsg)

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
        listenerName = OpCodes(msgObj.op).name.lower()
        if listenerName in self._eventListeners.keys():
            await self._eventListeners[listenerName](msgObj)

    def genHeartBeat(self):
        data = {'t': VoiceGateway.genNonce(), 'seq_ack': self._lastSequence}
        return GatewayMessage(OpCodes.HEARTBEAT.value, data)

    @staticmethod
    def genNonce():
        return int.from_bytes(urandom(8))