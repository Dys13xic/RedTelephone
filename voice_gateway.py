from gateway_connection import GatewayConnection, GatewayMessage
from os import urandom
import socket

SOURCE_IP = '69.156.219.180'
SOURCE_PORT = 5004

class OpCodes:
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

            case OpCodes.READY:
                try:
                    # TODO add check for modes containing: aead_xchacha20_poly1305_rtpsize
                    ssrc = msgObj.d['ssrc']
                    ip = msgObj.d['ip']
                    port = msgObj.d['port']
                    modes = msgObj.d['modes']
                except Exception as e:
                    print(e)
                    await self._stop()

                # Pass to relevant event handler
                if('ready' in self._eventListeners.keys()):
                    await self._eventListeners['ready'](msgObj)

                # TODO Establish UDP socket for RTP and peform IP discovery
                # TODO replace local address info
                data = {'protocol': 'udp', 'data': {'address': SOURCE_IP, 'port': SOURCE_PORT, 'mode': 'aead_xchacha20_poly1305_rtpsize'}}
                selectMsg = GatewayMessage(OpCodes.SELECT_PROTOCOL, data)
                await self.send(selectMsg)
            
            case OpCodes.SESSION_DESCRIPTION:
                pass

            case OpCodes.SPEAKING:
                pass

            case OpCodes.HEARTBEAT_ACK:
                pass

            case OpCodes.HELLO:
                # Update heartbeat interval
                if("heartbeat_interval" in msgObj.d):
                    self.setHeartbeatInterval(msgObj.d["heartbeat_interval"])
                    
                # Identify to API
                data = {'server_id': self._serverID, 'user_id': self._userID, 'session_id': self._sessionID, 'token': self.token}
                identifyMsg = GatewayMessage(OpCodes.IDENTIFY, data)
                await self.send(identifyMsg)

            case OpCodes.RESUMED:
                pass

            case OpCodes.CLIENTS_CONNECT:
                pass

            case OpCodes.CLIENTS_DISCONNECT:
                pass

            case OpCodes.DAVE_PREPARE_TRANSITION:
                pass

            case OpCodes.DAVE_EXECUTE_TRANSITION:
                pass

            case OpCodes.DAVE_PREPARE_EPOCH:
                pass

            case OpCodes.DAVE_MLS_EXTERNAL_SENDER:
                pass

            case OpCodes.DAVE_MLS_PROPOSALS:
                pass

            case OpCodes.DAVE_MLS_ANNOUNCE_COMMIT_TRANSACTION:
                pass

            case OpCodes.DAVE_MLS_WELCOME:
                pass

            case _:
                raise ValueError("Unsupported OP code in msg {}".format(msgObj.op))

    def genHeartBeat(self):
        data = {'t': VoiceGateway.genNonce(), 'seq_ack': self._lastSequence}
        return GatewayMessage(OpCodes.HEARTBEAT, data)
    
    @staticmethod
    def genNonce():
        return int.from_bytes(urandom(8))