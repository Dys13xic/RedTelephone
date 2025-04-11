# Standard Library
from configparser import ConfigParser
from aiohttp import ClientSession
import json

DEFAULT_CONFIG_FILE = 'config.ini'
REQUIRED_FIELDS = {
    'Server': ['PublicIP'],
    'VoIP': ['Address'],
    'Discord': ['BotToken', 'HomeGuildID', 'HomeVoiceChannelID', 'HomeTextChannelID'],
    'Messages': ['Welcome', 'IncomingCall'],
    'Timezone': ['UtcOffset']
}
IP_DISCOVERY_ENDPOINT = 'https://checkip.amazonaws.com/'

class Config():
    """Manage user configurable settings."""
    def __init__(self):
        self.publicIP = None
        self.voipAddress = None
        self.voipAllowList = []
        self.discordBotToken = None
        self.discordGuildID = None
        self.discordVoiceChannelID = None
        self.discordTextChannelID = None
        self.welcomeMessage = None
        self.incomingCallMessage = None
        self.utcOffset = None
        self.utcOffsetFactor = None
        self.hourlyCallLimit = None
        self.doNotDisturbTimes = []

    async def load(self, filename=DEFAULT_CONFIG_FILE):
        """Load configuration file values into object properties."""
        config = ConfigParser()
        config.read(filename)

        # Ensure mandatory parameters have been included.
        for section, options in REQUIRED_FIELDS.items():
            for o in options:
                if not config.has_option(section, o) or config.get(section, o) == '':
                    raise Exception(f'Mandatory parameter "{o}" missing from [{section}] section in config.ini')

        self.publicIP = config.get('Server', 'PublicIP')
        # Retrieve public ip if field set to "auto"
        if self.publicIP == 'auto':
            self.publicIP = await self._getPublicIP()

        self.voipAddress = config.get('VoIP', 'Address')
        
        temp = config.get('VoIP', 'AllowList', fallback='')
        if temp:
            self.voipAllowList = temp.split(',')
        else:
            self.voipAllowList = []

        self.discordBotToken = config.get('Discord', 'BotToken')
        self.discordGuildID = config.get('Discord', 'HomeGuildID')
        self.discordVoiceChannelID = config.get('Discord', 'HomeVoiceChannelID')
        self.discordTextChannelID = config.get('Discord', 'HomeTextChannelID')
        self.welcomeMessage = config.get('Messages', 'Welcome')
        self.incomingCallMessage = config.get('Messages', 'IncomingCall')

        temp = config.getint('Timezone', 'UtcOffset')
        self.utcOffsetFactor = 1 if temp >= 0 else -1
        self.utcOffset = abs(temp)

        self.hourlyCallLimit = config.getint('Call Preferences', 'HourlyCallLimit', fallback=0)
        # Convert falsey int of 0 to None
        if not self.hourlyCallLimit:
            self.hourlyCallLimit = None

        self.doNotDisturbTimes = json.loads(config.get('Call Preferences', 'DoNotDisturb', fallback='[]'))

    async def _getPublicIP(self):
        """Make a web request to retrieve your public IP."""
        async with ClientSession() as session:
            async with session.get(IP_DISCOVERY_ENDPOINT) as resp:
                ip = await resp.text()
                return ip.strip()
