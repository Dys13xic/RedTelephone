# 1st Party
from gateway_connection import GatewayMessage
from gateway import Gateway
from voice_gateway import VoiceGateway
from rtp import RtpEndpoint
from voip import Voip 

# Standard Library
import sys
import asyncio

DISCORD_RTP_PORT = 5003
RTP_PORT = 5004
RTCP_PORT = 5005
SIP_PORT = 5060


class Bot:
    gateway: Gateway
    voiceGateway: VoiceGateway
    initialVoiceServerUpdate: asyncio.Event
    voip = Voip
    discordEndpoint = RtpEndpoint
    phoneEndpoint = RtpEndpoint
    voiceState = {}

    def __init__(self, token):
        self.gateway = Gateway(token)
        self.voiceGateway = VoiceGateway()
        self.initialVoiceServerUpdate = asyncio.Event()
        self.voip = Voip(SIP_PORT, RTP_PORT, RTCP_PORT)
        self.discordEndpoint = None
        self.phoneEndpoint = None
        self.voiceState = {}


if __name__ == "__main__":
    # Retrieve the discord bot token
    try:
        tokenFile = open("token.txt", 'r')
        token = tokenFile.readline()
    except:
        print("ERROR: Unable to open/read token.txt")
        sys.exit(1)

    bot = Bot(token)

    # Track the voice state of all users and update bot session ID
    @bot.gateway.eventHandler
    async def voice_state_update(msgObj):
        if msgObj.d['user_id'] == bot.gateway.getUserID():
            bot.gateway.setSessionID(msgObj.d['session_id'])
        bot.voiceState[msgObj.d['user_id']] = [msgObj.d['guild_id'], msgObj.d['channel_id']]


    # Initiate VOIP call on bot mention
    @bot.gateway.eventHandler
    async def message_create(msgObj):
        botID = bot.gateway.getUserID()
        authorID = msgObj.d['author']['id']
        voiceGuildID, voiceChannelID = bot.voiceState.get(authorID, [None, None])

        for user in msgObj.d['mentions']:
            if user['id'] == botID:
                if msgObj.d['guild_id'] == voiceGuildID:
                    await bot.gateway.joinVoiceChannel(voiceGuildID, voiceChannelID)
                    await bot.voip.call('10.13.0.6')
                else:
                    # TODO send message to text channel stating user isn't in a voice channel within that guild.
                    pass

                break


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
        ssrc = msgObj.d['ssrc']

        loop = asyncio.get_event_loop()
        _, endpoint = await loop.create_datagram_endpoint(
            lambda: RtpEndpoint(ssrc=ssrc, encrypted=True),
            local_addr=("0.0.0.0", DISCORD_RTP_PORT),
            remote_addr=(remoteIP, remotePort)
        )
        bot.discordEndpoint = endpoint


    @bot.voiceGateway.eventHandler
    async def session_description(msgObj):
        bot.discordEndpoint.setSecretKey(msgObj.d['secret_key'])
        # TODO verify phonecall has been picked up and RTP endpoint exists before proxying
        # Alternatively, create the RTP endpoint on INVITE sent and don't specify the remote address/port, could include a class var to store it...
        RtpEndpoint.proxy(bot.discordEndpoint, bot.voip.getRTPEndpoint(), yCtrl=bot.voip.getRTCPEndpoint())
        

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(asyncio.gather(bot.voip.run(), bot.gateway.run(), bot.voiceGateway.runAfter(bot.initialVoiceServerUpdate)))
    finally:
        loop.close()    