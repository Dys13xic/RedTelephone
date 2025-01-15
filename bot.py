from gateway_connection import GatewayMessage
from gateway import Gateway
from voice_gateway import VoiceGateway
from rtp import RtpEndpoint

import sys
import asyncio

GUILD_ID = 729825988443111424
CHANNEL_ID = 729825988443111428
RTP_PORT = 5004

class Bot:
    gateway: Gateway
    voiceGateway: VoiceGateway
    initialVoiceServerUpdate: asyncio.Event
    discordEndpoint = RtpEndpoint
    phoneEndpoint = RtpEndpoint

    def __init__(self, token):
        self.gateway = Gateway(token)
        self.voiceGateway = VoiceGateway()
        self.initialVoiceServerUpdate = asyncio.Event()
        self.discordEndpoint = None
        self.phoneEndpoint = None

if __name__ == "__main__":
    # Retrieve the discord bot token
    try:
        tokenFile = open("token.txt", 'r')
        token = tokenFile.readline()
    except:
        print("ERROR: Unable to open/read token.txt")
        sys.exit(1)

    bot = Bot(token)

    @bot.gateway.eventHandler
    async def voice_server_update(msgObj):
        try:
            voiceToken = msgObj.d['token']
            voiceEndpoint = 'wss://' + msgObj.d['endpoint']
            serverID = msgObj.d['guild_id']
        except KeyError as e:
            print(e)
            await bot.gateway._stop()

        userID = bot.gateway.getUserID()
        sessionID = bot.gateway.getSessionID()

        # TODO should the Bot class hold the UserID, ServerID, and sessionID? Note: they are shared by both gateways
        bot.voiceGateway.lateInit(userID, serverID, voiceToken, voiceEndpoint, sessionID)
        bot.initialVoiceServerUpdate.set()

    @bot.voiceGateway.eventHandler
    async def ready(msgObj):
        remoteIP, remotePort = msgObj.d['ip'], msgObj.d['port']

        loop = asyncio.get_event_loop()
        _, endpoint = await loop.create_datagram_endpoint(
            lambda: RtpEndpoint(encrypted=False),
            local_addr=("0.0.0.0", RTP_PORT),
            remote_addr=(remoteIP, remotePort)
        )
        bot.discordEndpoint = endpoint

    @bot.voiceGateway.eventHandler
    async def session_description(msgObj):
        bot.discordEndpoint.setSecretKey(msgObj.d['secret_key'])

    # asyncio.run(gw._run())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(asyncio.gather(bot.gateway._run(), bot.voiceGateway._runAfter(bot.initialVoiceServerUpdate)))
    finally:
        loop.close()    