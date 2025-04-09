# 1st Party
from Discord.client import Client
from rtp import RtpEndpoint
from voip import Voip
from Utils.doNotDisturb import DoNotDisturb
from Utils.callLog import CallLog
from Utils.config import Config
from Sip.exceptions import InviteError

# Standard Library
import sys
import asyncio
import logging
import os
from datetime import timedelta, timezone

LOGGING = True

async def main():
    # Load configuration settings
    config = Config()
    await config.load()

    currentTimeZone = timezone(config.utcOffsetFactor * timedelta(hours=config.utcOffset))
    doNotDisturb = DoNotDisturb(config.doNotDisturbTimes, tz=currentTimeZone)
    callLog = CallLog(config.hourlyCallLimit, tz=currentTimeZone)

    client = Client(token=config.discordBotToken)
    voip = Voip(config.publicIP, allowList=[config.voipAddress] + config.voipAllowList)

    @client.event
    async def on_guild_join(msgData):
        pass

    @client.event
    async def on_user_mention(msgData):
        voiceServerID, voiceChannelID = await client.fetchVoiceState(msgData['author']['id'], msgData['guild_id'])
        # TODO replace use of getVoiceState somehow
        _, botVoiceChannelID = client.gateway.getVoiceState(client.gateway.userID)

        if voiceServerID and voiceChannelID:
            if doNotDisturb.violated():
                client.createMessage('`The line is not monitored at this hour.`', msgData['channel_id'])

            elif callLog.callLimitExceeded():
                client.createMessage(f'`The hourly call limit was exceeded, you may try again at: {callLog.nextAllowedTime()}`', msgData['channel_id'])

            elif botVoiceChannelID:
                client.createMessage('`The line is already in use.`', msgData['channel_id'])
                pass
            else:
                try:
                    result = await asyncio.gather(client.joinVoice(voiceServerID, voiceChannelID), voip.call(config.voipAddress))
                    callLog.record()
                except InviteError as e:
                    client.createMessage('`Failed to initiate a call.`', msgData['channel_id'])
                    await client.leaveVoice()
        else:
            client.createMessage('`User must be in a voice channel to initiate a call.`', msgData['channel_id'])

    @client.event
    async def on_voice_secret_received():
        # TODO improve the appearance of this code and only run when needed (incoming calls)
        voip.answerCall.set()

        # Need an active VOIP session before proxying traffic
        await voip.sessionStarted.wait()
        await client.voiceGateway.updateSpeaking()
        RtpEndpoint.proxy(client.voiceGateway.rtpEndpoint, voip.rtpEndpoint, yCtrl=voip.rtcpEndpoint)

    @voip.event
    async def on_inbound_call():
        await client.joinVoice(config.discordGuildID, config.discordVoiceChannelID)
        client.createMessage(config.incomingCallMessage, config.discordTextChannelID)

    @voip.event
    async def on_inbound_call_ended():
        await client.leaveVoice()
        # TODO cleanup the RTP assets?

    @voip.event
    async def on_inbound_call_cancelled():
        await client.leaveVoice()

    if LOGGING:
        logging.basicConfig(format='%(message)s', level=logging.DEBUG)
        os.environ['WEBSOCKETS_MAX_LOG_SIZE'] = '1000'
    await asyncio.gather(client.run(), voip.run())


if __name__ == "__main__":
    try:
        asyncio.run(main(), debug=LOGGING)
    except KeyboardInterrupt:
        print('Process interrupted')
    finally:
        print('Bot successfully shutdown')