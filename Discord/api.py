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
        self.session = None

    # TODO add error handling
    async def simple_message_create(self, text, channelID):
        if not self.session:
            self.session = ClientSession(base_url = self.endpoint, headers=self.headers)

        resp = await self.session.post(f'channels/{channelID}/messages', data={'content': text})

    # TODO add cleanup method to close session