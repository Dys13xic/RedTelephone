# 1st Party
from Discord.client import Client
from rtp import RtpEndpoint
from voip import Voip 

# Standard Library
import sys
import asyncio

RTP_PORT = 5004
RTCP_PORT = 5005
SIP_PORT = 5060

HOME_GUILD_ID = '729825988443111424'
HOME_VOICE_CHANNEL_ID = '729825988443111428'
HOME_TEXT_CHANNEL_ID = '733403603867271179'

if __name__ == "__main__":
    # Retrieve the discord bot token
    try:
        tokenFile = open("token.txt", 'r')
        token = tokenFile.readline()
    except:
        print("ERROR: Unable to open/read token.txt")
        sys.exit(1)

    client = Client(token)
    voip = Voip(SIP_PORT, RTP_PORT, RTCP_PORT)

    @client.event
    async def on_user_mention(msgData):
        authorID = msgData['author']['id']
        # TODO is it more appropriate to keep the stuff users would see to client?
        voiceServerID, voiceChannelID = client.gateway.getVoiceState(authorID)
        if msgData['guild_id'] == voiceServerID and voiceChannelID:
            await client.joinVoiceChannel(voiceServerID, voiceChannelID)
            await voip.call('10.13.0.6')
        else:
            client.createMessage('`User must be in a voice channel to initiate a call.`', msgData['channel_id'])

    @client.event
    async def on_voice_secret_received():
        # Wait for active VOIP session before proxying traffic
        await voip.getSessionStarted().wait()
        RtpEndpoint.proxy(client.voiceGateway.getRTPEndpoint(), voip.getRTPEndpoint(), yCtrl=voip.getRTCPEndpoint())


    @voip.event
    async def on_inbound_call_accepted():
        await client.joinVoiceChannel(HOME_GUILD_ID, HOME_VOICE_CHANNEL_ID)
        client.createMessage('@everyone', HOME_TEXT_CHANNEL_ID)

    @voip.event
    async def on_inbound_call_ended():
        pass
        # TODO disconnect from voice
        # await bot.gateway.joinVoiceChannel(None, None)

    async def main():
        await asyncio.gather(client.run(), voip.run())

    asyncio.run(main())