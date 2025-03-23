# 1st Party
from Discord.client import Client
from rtp import RtpEndpoint
from voip import Voip
from doNotDisturb import DoNotDisturb, Weekdays
from callLog import CallLog

# Standard Library
import sys
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

LOGGING = True

VOIP_HANDSET_ADDRESS = '10.13.0.6'
RTP_PORT = 5004
RTCP_PORT = 5005
SIP_PORT = 5060

HOME_GUILD_ID = '729825988443111424'
HOME_VOICE_CHANNEL_ID = '729825988443111428'
HOME_TEXT_CHANNEL_ID = '733403603867271179'

HOURLY_CALL_LIMIT = 5

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
    doNotDisturb = DoNotDisturb(timeFrames=[(0, 9), (23, 24)], tz=currentTimeZone)
    callLog = CallLog(HOURLY_CALL_LIMIT, tz=currentTimeZone)

    client = Client(token)
    voip = Voip(SIP_PORT, RTP_PORT, RTCP_PORT)


    @client.event
    async def on_user_mention(msgData):
        authorID = msgData['author']['id']
        # TODO is it more appropriate to keep the stuff users would see to client?
        voiceServerID, voiceChannelID = client.gateway.getVoiceState(authorID)
        _, botVoiceChannelID = client.gateway.getVoiceState(client.gateway.userID)
        if msgData['guild_id'] == voiceServerID and voiceChannelID:

            if doNotDisturb.violated():
                client.createMessage('`The line is not monitored at this hour.`', msgData['channel_id'])
                
            elif callLog.callLimitExceeded():
                client.createMessage(f'`The hourly call limit was exceeded, you may try again at: {callLog.nextAllowedTime()}`', msgData['channel_id'])

            elif botVoiceChannelID:
                client.createMessage('`The line is already in use.`', msgData['channel_id'])
                pass
            else:
                await asyncio.gather(client.joinVoice(voiceServerID, voiceChannelID), voip.call(VOIP_HANDSET_ADDRESS))
                callLog.record()
        else:
            client.createMessage('`User must be in a voice channel to initiate a call.`', msgData['channel_id'])

    @client.event
    async def on_voice_secret_received():
        # TODO improve the appearance of this code and only run when needed (incoming calls)
        voip.answerCall.set()

        # Need an active VOIP session before proxying traffic
        await voip.sessionStarted.wait()
        RtpEndpoint.proxy(client.voiceGateway.rtpEndpoint, voip.rtpEndpoint, yCtrl=voip.rtcpEndpoint)

    @voip.event
    async def on_inbound_call():
        await client.joinVoice(HOME_GUILD_ID, HOME_VOICE_CHANNEL_ID)
        client.createMessage('@everyone', HOME_TEXT_CHANNEL_ID)

    @voip.event
    async def on_inbound_call_ended():
        await client.leaveVoice()
        # TODO cleanup the RTP assets?

    @voip.event
    async def on_inbound_call_cancelled():
        await client.leaveVoice()

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
    