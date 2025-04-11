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
        # Define custom configparser converters
        customConverters = {
            'csv': lambda x: x.split(',') if x else [],
            'list': lambda x: json.loads(x) if x else []
        }
        # Initialize config parser and load DEFAULT_CONFIG_FILE
        config = ConfigParser(converters=customConverters)
        config.read(filename)

        # Ensure mandatory parameters have been included
        for section, options in REQUIRED_FIELDS.items():
            for o in options:
                if not config.has_option(section, o) or config.get(section, o) == '':
                    raise Exception(f'Mandatory parameter "{o}" missing from [{section}] section in config.ini')

        # Load config properties
        self.publicIP = config.get('Server', 'PublicIP')
        self.voipAddress = config.get('VoIP', 'Address')
        self.voipAllowList = config.getcsv('VoIP', 'AllowList')
        self.discordBotToken = config.get('Discord', 'BotToken')
        self.discordGuildID = config.get('Discord', 'HomeGuildID')
        self.discordVoiceChannelID = config.get('Discord', 'HomeVoiceChannelID')
        self.discordTextChannelID = config.get('Discord', 'HomeTextChannelID')
        self.welcomeMessage = config.get('Messages', 'Welcome')
        self.incomingCallMessage = config.get('Messages', 'IncomingCall')
        self.utcOffset = config.getint('Timezone', 'UtcOffset')
        self.hourlyCallLimit = config.getint('Call Preferences', 'HourlyCallLimit', fallback=0)
        self.doNotDisturbTimes = config.getlist('Call Preferences', 'DoNotDisturb')

        # Retrieve public IP if field set to "auto"
        if self.publicIP == 'auto':
            self.publicIP = await self._getPublicIP()

        # Convert falsey int of 0 to None
        if not self.hourlyCallLimit:
            self.hourlyCallLimit = None

    async def _getPublicIP(self):
        """Make a web request to retrieve your public IP."""
        async with ClientSession() as session:
            async with session.get(IP_DISCOVERY_ENDPOINT) as resp:
                ip = await resp.text()
                return ip.strip()