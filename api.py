import requests

API_URL = 'https://discord.com/api'
API_VERSION = 10

# TODO replace with self-written async class
class Api():
    _token: str

    def __init__(self, token):
        self._token = token
        self.endpoint = '{}/v{}'.format(API_URL, str(API_VERSION))
        self.session = requests.Session()
        self.session.headers = {'Authorization': 'Bot {}'.format(self._token)}

    def simple_message_create(self, text, channelID):
        data = {'content': text}
        r = self.session.post(self.endpoint + '/channels/{}/messages'.format(channelID), data)