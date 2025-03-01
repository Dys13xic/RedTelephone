# 1st Party
from events import EventHandler
from .gateway import Gateway
from .voice_gateway import VoiceGateway
from .api import Api

# Standard Library
import asyncio

class Client:
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
        self.voiceEventHandler.on('session_description', self.on_session_description)

    async def run(self):
        await self.start()

    async def start(self):
        await self.gateway.connect()

    # Register client events through function decorator
    def event(self, func):
        async def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result
        
        self.eventHandler.on(func.__name__.removeprefix('on_'), wrapper)
        return wrapper

    # Gateway Events
    # ---------------
    async def on_message_create(self, data):
        userID = self.gateway.getUserID()
        for user in data['mentions']:
            if user['id'] == userID:
                await self.eventHandler.dispatch('user_mention', data)
                break

    async def on_voice_server_update(self, token, endpoint):
        # TODO handle when endpoint == NULL
        self.voiceGateway.token = token
        self.voiceGateway.endpoint = endpoint
        try:
            await self.voiceGateway.connect()
        except asyncio.CancelledError:
            print('Voice gateway cancelled.')

    # Voice Gateway Events
    # ---------------------
    async def on_session_description(self):
        await self.eventHandler.dispatch('voice_secret_received')


    # Gateway API Methods
    # --------------------
    async def joinVoice(self, guildID, channelID):
        await self.gateway.updateVoiceChannel(guildID, channelID)
        self.voiceGateway = VoiceGateway(self.gateway, guildID, channelID, self.voiceEventHandler.dispatch)

    async def leaveVoice(self):
        if self.voiceGateway:
            await self.voiceGateway.disconnect()
            self.voiceGateway = None

    # REST API Wrapper Methods
    # -----------------
    def createMessage(self, text, channelID):
        self.api.simple_message_create(text, channelID)