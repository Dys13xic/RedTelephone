# 1st Party
from gateway_connection import GatewayConnection, GatewayMessage

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


class Gateway(GatewayConnection):
    _eventListeners: dict
    _userID: int
    _sessionID: int
    _voiceToken: str
    _voiceEndpoint: str
    _serverID: str
    _handshakeComplete: bool

    def __init__(self, token):
        super().__init__(token, DEFAULT_ENDPOINT, '&encoding=json')

        self._eventListeners = {}
        self._userID = None
        self._sessionID = None
        self._handshakeComplete = False

    def eventHandler(self, func):
        def wrapper(instanceSelf, *args, **kwargs):
            return func(instanceSelf, *args, **kwargs)
        
        self._eventListeners[func.__name__] = wrapper
        return wrapper

    async def processMsg(self, msgObj):
        match msgObj.op:
            case OpCodes.EVENT_DISPATCH:
                # Update sequence number
                if(msgObj.s):
                    self.setLastSequence(msgObj.s)

                if(msgObj.t == "READY"):
                    self._handshakeComplete = True
                    self._userID = msgObj.d['user']['id']

                if(msgObj.t == "VOICE_SERVER_UPDATE"):
                    self._voiceToken = msgObj.d['token']
                    self._voiceEndpoint = 'wss://' + msgObj.d['endpoint']
                    self._serverID = msgObj.d['guild_id']

                    # TODO grab info for resuming session

                # Pass to relevant event handler
                if(msgObj.t.lower() in self._eventListeners.keys()):
                    await self._eventListeners[msgObj.t.lower()](msgObj)

            # TODO, see if you can reset sleep timer on HeartBeat request (as this function will run immediately, resulting in an early follow-up heartbeat)
            case OpCodes.HEARTBEAT:
                msgObj = self.genHeartBeat()
                await self.send(msgObj)

            case OpCodes.RECONNECT:
                pass

            case OpCodes.INVALID_SESSION:
                pass

            case OpCodes.HELLO:
                # Update heartbeat interval
                if("heartbeat_interval" in msgObj.d):
                    self.setHeartbeatInterval(msgObj.d["heartbeat_interval"])
                # Identify to API

                data = {"token": self.token, "properties": {"os": "Linux", "browser": "redTelephone", "device": "redTelephone"}, "intents": (1 << 7) + (1 << 9)}
                identifyMsg = GatewayMessage(OpCodes.IDENTIFY, data)
                await self.send(identifyMsg)

            # TODO is timer needed to verify heartbeat ack and connection still open?
            case OpCodes.HEARTBEAT_ACK:
                pass

            case _:
                raise ValueError("Unsupported OP code in gateway msg {}".format(msgObj.op))
            
    def genHeartBeat(self):
        return GatewayMessage(OpCodes.HEARTBEAT, self._lastSequence)
    
    # TODO is this method needed?
    async def joinVoiceChannel(self, guildID, channelID, selfMute=False, selfDeaf=False):
        if not self._handshakeComplete:
            raise Exception('Gateway handshake not complete.')

        data = {'guild_id': guildID, 'channel_id': channelID, 'self_mute': selfMute, 'self_deaf': selfDeaf}
        try:
            await self.send(GatewayMessage(OpCodes.VOICE_STATE_UPDATE, data))
        except Exception as e:
            print(e)
    
    def getUserID(self):
        return self._userID
    
    def getSessionID(self):
        return self._sessionID

    def setSessionID(self, sessionID):
        self._sessionID = sessionID

    def getVoiceToken(self):
        return self._voiceToken
    
    def getVoiceEndpoint(self):
        return self._voiceEndpoint

    def getServerID(self):
        return self._serverID

if __name__ == "__main__":
    token = "foo"
    gw = Gateway(token)

    @gw.eventHandler
    def ready(msgObj):
        print("xxxxxxxxxxxxxxxx")
        print(msgObj)
        print("XXXXXXXXXXXXXXXXX")

    # asyncio.run(gw._run())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(gw.run())
    finally:
        loop.close()