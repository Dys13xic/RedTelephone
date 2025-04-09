import asyncio
from aiohttp import ClientSession

API_URL = 'https://discord.com/api'
API_VERSION = 10

class Api():
    _token: str
    endpoint: str
    headers: dict
    session: ClientSession

    def __init__(self, token):
        self._token = token
        self.endpoint = f'{API_URL}/v{str(API_VERSION)}/'
        # TODO establish proper versioning constants
        self.headers = {'User-Agent': 'DiscordBot (RedTelephone, 1.0)', 'Authorization': f'Bot {self._token}'}
        self.session = ClientSession(base_url = self.endpoint, headers=self.headers)

    # TODO add error handling
    async def simple_message_create(self, text, channelID):
        resp = await self.session.post(f'channels/{channelID}/messages', data={'content': text})

    async def get_user_voice_state(self, userID, guildID):
        async with self.session.get(f'guilds/{guildID}/voice-states/{userID}') as resp:
            result = await resp.json()
            guildID = result.get('guild_id', None)
            channelID = result.get('channel_id', None)

        return guildID, channelID

    # TODO add cleanup method to close session