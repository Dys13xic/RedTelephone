# 1st Party
from gateway_connection import GatewayConnection, GatewayMessage
from events import EventHandler

# 3rd Party
import websockets

# Standard Library
import asyncio

DEFAULT_ENDPOINT = "wss://gateway.discord.gg/"


class OpCodes:
    EVENT_DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE_UPDATE = 3
    VOICE_STATE_UPDATE = 4
    RESUME = 6
    RECONNECT = 7
    REQUEST_GUILD_MEMBERS = 8
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11
    REQUEST_SOUNDBOURD_SOUNDS = 31

class CloseCodes():
    UNKNOWN_ERROR = 4000
    UNKNOWN_OPCODE = 4001
    DECODE_ERROR = 4002
    NOT_AUTHENTICATED = 4003
    AUTHENTICATION_FAILED = 4004
    ALREADY_AUTHENTICATED = 4005
    INVALID_SEQ = 4007
    RATE_LIMITED = 4008
    SESSION_TIMED_OUT = 4009
    INVALID_SHARD = 4010
    SHARDING_REQUIRED = 4011
    INVALID_API_VERSION = 4012
    INVALID_INTENT = 4013
    DISALLOWED_INTENT = 4014


class Gateway(GatewayConnection):
    _userID: int
    _sessionID: int
    _eventDispatcher: EventHandler.dispatch
    _voiceState: dict

    def __init__(self, token, eventDispatcher):
        super().__init__(token, DEFAULT_ENDPOINT, '&encoding=json')
        self._userID = None
        self._sessionID = None
        self._eventDispatcher = eventDispatcher
        self._voiceState = {}

    def getUserID(self):
        return self._userID
    
    def getSessionID(self):
        return self._sessionID

    def setSessionID(self, sessionID):
        self._sessionID = sessionID

    def getVoiceState(self, userID):
        return self._voiceState.get(userID, [None, None])

    async def connect(self):
        # TODO add exponential backoff?
        await self._start()
        # while True:
        #     try:
        #         await self._start()
        #     # TODO add error logging?
        #     except websockets.exceptions.ConnectionClosedOK:
        #         self._stop(clean=True)
        #     except websockets.exceptions.ConnectionClosedError as e:
        #         clean = not self.isResumable(e.code)
        #         self._stop(clean)
        #     except asyncio.exceptions.CancelledError as e:
        #         print('Task cancelled')
        #     except Exception as e:
        #         print(e)

    def _clean(self):
        super()._clean()
        self._sessionID = None
        self.setEndpoint(DEFAULT_ENDPOINT)
        self.setParams('&encoding=json')

    async def processMsg(self, msgObj):
        match msgObj.op:
            case OpCodes.HELLO:
                # Update heartbeat interval
                if("heartbeat_interval" in msgObj.d):
                    self.setHeartbeatInterval(msgObj.d["heartbeat_interval"])

                if self._sessionID:
                    # Resume connection
                    data = {'token': self.token, 'session_id': self._sessionID, 'seq': self.lastSequence}
                    opcode = OpCodes.RESUME
                else:
                    # Identify to API
                    data = {"token": self.token, "properties": {"os": "Linux", "browser": "redTelephone", "device": "redTelephone"}, "intents": (1 << 7) + (1 << 9)}
                    opcode = OpCodes.IDENTIFY
                    
                await self.send(GatewayMessage(opcode, data))

            case OpCodes.EVENT_DISPATCH:
                # Update sequence number
                if(msgObj.s):
                    self.lastSequence = msgObj.s

                eventType = msgObj.t
                args = []

                if eventType == "READY":
                    self._userID = msgObj.d['user']['id']
                    self.setEndpoint = msgObj.d['resume_gateway_url']
                    self._sessionID = msgObj.d['session_id']

                if eventType == 'MESSAGE_CREATE':
                    args = [msgObj.d]

                if eventType == 'VOICE_STATE_UPDATE':
                    # Track user's current voice channel
                    self._voiceState[msgObj.d['user_id']] = [msgObj.d['guild_id'], msgObj.d['channel_id']]
                    # Keep bot session ID up-to-date
                    if msgObj.d['user_id'] == self.getUserID():
                        self._sessionID = msgObj.d['session_id']


                if eventType == "VOICE_SERVER_UPDATE":
                    args = [msgObj.d['token'],
                             'wss://' + msgObj.d['endpoint']]

                # Pass to relevant event handler
                await self._eventDispatcher(msgObj.t.lower(), *args)

            case OpCodes.HEARTBEAT:
                msgObj = self.genHeartBeat()
                await self.send(msgObj)

            case OpCodes.RECONNECT:
                self._stop(clean=False)

            case OpCodes.INVALID_SESSION:
                clean = not msgObj.d
                self._stop(clean)

            # TODO is timer needed to verify heartbeat ack and connection still open?
            case OpCodes.HEARTBEAT_ACK:
                pass

            case _:
                raise ValueError("Unsupported OP code in gateway msg {}".format(msgObj.op))
    
    def genHeartBeat(self):
        return GatewayMessage(OpCodes.HEARTBEAT, self.lastSequence)
    
    def isResumable(self, closeCode):
        if closeCode in [CloseCodes.UNKNOWN_ERROR, CloseCodes.DECODE_ERROR, CloseCodes.NOT_AUTHENTICATED, CloseCodes.ALREADY_AUTHENTICATED, 
                         CloseCodes.INVALID_SEQ, CloseCodes.RATE_LIMITED, CloseCodes.SESSION_TIMED_OUT]:
            return True
        else:
            return False
    
    async def signalVoiceChannelJoin(self, guildID, channelID, selfMute=False, selfDeaf=False):
        # if not self._handshakeComplete:
        #     raise Exception('Gateway handshake not complete.')

        data = {'guild_id': guildID, 'channel_id': channelID, 'self_mute': selfMute, 'self_deaf': selfDeaf}
        # try:
        await self.send(GatewayMessage(OpCodes.VOICE_STATE_UPDATE, data))
        # except Exception as e:
        #     print(e)


if __name__ == "__main__":
    # Retrieve the discord bot token
    try:
        tokenFile = open("token.txt", 'r')
        token = tokenFile.readline()
    except:
        print("ERROR: Unable to open/read token.txt")
        
    gw = Gateway(token)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(gw.connect())
    loop.close()