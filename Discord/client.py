# 1st Party
from Utils.events import EventHandler
from .gateway import Gateway
from .voice_gateway import VoiceGateway
from .api import Api

# Standard Library
import asyncio

class Client:
    """Manage user facing interaction with Discord's Gateway, VoiceGateway, and REST API"""
    _token: str
    gatewayEventHandler: EventHandler
    voiceEventHandler: EventHandler
    clientEventHandler: EventHandler
    gateway: Gateway
    voiceGateway: VoiceGateway
    api: Api

    def __init__(self, token):
        self._token = token
        self.eventHandler = EventHandler()
        self.gatewayEventHandler = EventHandler()
        self.voiceEventHandler = EventHandler()
        self.gateway = Gateway(self._token, self.gatewayEventHandler.dispatch)
        self.voiceGateway = None
        self.api = Api(token)
        
        # Register listeners
        self.gatewayEventHandler.on('message_create', self.on_message_create)
        self.gatewayEventHandler.on('voice_server_update', self.on_voice_server_update)
        self.gatewayEventHandler.on('guild_create', self.on_guild_create)
        self.voiceEventHandler.on('session_description', self.on_session_description)

    async def run(self):
        """Start the bot and connect to Discord."""
        try:
            await self.gateway.connect()
        except asyncio.CancelledError:
            print('Gateway cancelled.')
        finally:
            await self.cleanup()

    def event(self, func):
        """Register client events through function decorator."""
        async def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result
        
        self.eventHandler.on(func.__name__.removeprefix('on_'), wrapper)
        return wrapper
    
    async def cleanup(self):
        """Cleanup client connections."""
        if self.voiceGateway:
            await self.voiceGateway.disconnect()

        await self.gateway.disconnect()
        await self.api.close()

    # Gateway Events
    # ---------------
    async def on_guild_create(self, data):
        """When a bot connects/reconnects to a guild, determine if the guild is new (if so dispatch an event)."""
        # TODO implement logic for determining if the guild is new
        await self.eventHandler.dispatch('guild_join', data)

    async def on_message_create(self, data):
        """When a message is received, check if the bot was mentioned (if so dispatch an event)."""
        userID = self.gateway.userID
        for user in data['mentions']:
            if user['id'] == userID:
                await self.eventHandler.dispatch('bot_mention', data)
                break

    async def on_voice_server_update(self, token, endpoint):
        """When a VOICE_SERVER_UPDATE is received, configure and connect the voice gateway."""
        if endpoint:
            self.voiceGateway.token = token
            self.voiceGateway.endpoint = endpoint
            asyncio.create_task(self.voiceGateway.connect())
        else:
            await self.gateway.updateVoiceChannel(channelID=None)

    # Voice Gateway Events
    # ---------------------
    async def on_session_description(self):
        """When a SESSION_DESCRIPTION is received, dispatch an event indicating voice connection is complete."""
        await self.eventHandler.dispatch('voice_connection_finalized')

    # Gateway API Methods
    # --------------------
    async def joinVoice(self, guildID, channelID):
        """Join a new voice channel."""
        await self.gateway.updateVoiceChannel(guildID, channelID)
        self.voiceGateway = VoiceGateway(self.gateway, guildID, channelID, self.voiceEventHandler.dispatch)

    async def leaveVoice(self):
        """Leave the current voice channel."""
        await self.gateway.updateVoiceChannel(channelID=None)
        if self.voiceGateway:
            await self.voiceGateway.disconnect()
            self.voiceGateway = None

    # REST API Wrapper Methods
    # -----------------
    def createMessage(self, text, channelID):
        """Send a message to the specified text channel."""
        asyncio.create_task(self.api.simple_message_create(text, channelID))

    # Fetch Methods
    # -----------------
    async def fetchVoiceState(self, userID, guildID=None):
        """Return the current voice state of a user using cached values if they exist or a REST API call."""
        cachedGuildID, cachedVoiceID = self.gateway.getVoiceState(userID)
        if cachedGuildID and cachedVoiceID:
            guildID, voiceID = cachedGuildID, cachedVoiceID
        elif guildID:
            guildID, voiceID = await self.api.get_user_voice_state(userID, guildID)
            self.gateway.setVoiceState(userID, (guildID, voiceID))
        else:
            guildID, voiceID = None, None
                
        return guildID, voiceID