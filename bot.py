# 1st Party
from Discord.client import Client
from rtp import RtpEndpoint
from voip import Voip
from doNotDisturb import DoNotDisturb, Weekdays

# Standard Library
import sys
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

LOGGING = True

RTP_PORT = 5004
RTCP_PORT = 5005
SIP_PORT = 5060

HOME_GUILD_ID = '729825988443111424'
HOME_VOICE_CHANNEL_ID = '729825988443111428'
HOME_TEXT_CHANNEL_ID = '733403603867271179'

UTC_OFFSET_HOURS = 5
UTC_OFFSET_FACTOR = -1

if __name__ == "__main__":
    # Retrieve the discord bot token
    try:
        with open('token.txt', 'r', encoding='utf-8') as f:
            token = f.readline()
    except Exception:
        sys.exit()

    # TODO load configuration settings
    currentTimeZone = timezone(UTC_OFFSET_FACTOR * timedelta(hours=UTC_OFFSET_HOURS))
    doNotDisturb = DoNotDisturb(timeFrames=[(0, 9), (23, 24)])

    client = Client(token)
    voip = Voip(SIP_PORT, RTP_PORT, RTCP_PORT)


    @client.event
    async def on_user_mention(msgData):
        authorID = msgData['author']['id']
        # TODO is it more appropriate to keep the stuff users would see to client?
        voiceServerID, voiceChannelID = client.gateway.getVoiceState(authorID)
        if msgData['guild_id'] == voiceServerID and voiceChannelID:
            
            currentDateTime = datetime.now(tz=currentTimeZone)
            if doNotDisturb.violated(currentDateTime):
                client.createMessage('`Line is not monitored at this hour.`', msgData['channel_id'])
                
            # elif callLimitExceeded(currentDateTime):
            #     client.createMessage('`You have surpassed the hourly call limit. You may try again at: `', msgData['channel_id'])
            else:
                await asyncio.gather(client.joinVoice(voiceServerID, voiceChannelID), voip.call('10.13.0.6'))                
        else:
            client.createMessage('`User must be in a voice channel to initiate a call.`', msgData['channel_id'])

    @client.event
    async def on_voice_secret_received():
        # Wait for active VOIP session before proxying traffic
        await voip.getSessionStarted().wait()
        RtpEndpoint.proxy(client.voiceGateway.getRTPEndpoint(), voip.getRTPEndpoint(), yCtrl=voip.getRTCPEndpoint())


    @voip.event
    async def on_inbound_call_accepted():
        await client.joinVoice(HOME_GUILD_ID, HOME_VOICE_CHANNEL_ID)
        # TODO uncomment after testing finished
        # client.createMessage('@everyone', HOME_TEXT_CHANNEL_ID)

    @voip.event
    async def on_inbound_call_ended():
        await client.leaveVoice()
        # TODO cleanup the RTP assets?

    async def main():
        if LOGGING:
            logging.basicConfig(format='%(message)s', level=logging.DEBUG)
            os.environ['WEBSOCKETS_MAX_LOG_SIZE'] = '1000'
        await asyncio.gather(client.run(), voip.run())

    try:
        asyncio.run(main(), debug=LOGGING)
    except KeyboardInterrupt:
        print('Process interrupted')
    finally:
        print('Bot successfully shutdown')
    