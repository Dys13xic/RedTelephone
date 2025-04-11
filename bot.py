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
    # Load config.ini settings
    config = Config()
    await config.load()

    # Initialize main services
    client = Client(token=config.discordBotToken)
    voip = Voip(config.publicIP, allowList=[config.voipAddress] + config.voipAllowList)

    # Initialize utilities
    currentTimeZone = timezone(config.utcOffsetFactor * timedelta(hours=config.utcOffset))
    doNotDisturb = DoNotDisturb(config.doNotDisturbTimes, tz=currentTimeZone)
    callLog = CallLog(config.hourlyCallLimit, tz=currentTimeZone)
    
    # Event listeners
    @client.event
    async def on_guild_join(msgData):
        """Posts a welcome message in a text channel when a new guild is joined."""
        pass

    @client.event
    async def on_bot_mention(msgData):
        """When the bot is mentioned in a text channel, join the message author's current voice channel and call the VoIP handset."""
        voiceServerID, voiceChannelID = await client.fetchVoiceState(msgData['author']['id'], msgData['guild_id'])
        _, botVoiceChannelID = await client.fetchVoiceState(client.gateway.userID)

        if voiceServerID and voiceChannelID:
            if doNotDisturb.violated():
                client.createMessage('`The line is not monitored at this hour.`', msgData['channel_id'])

            elif callLog.callLimitExceeded():
                client.createMessage(f'`The hourly call limit was exceeded, you may try again at: {callLog.nextAllowedTime()}`', msgData['channel_id'])

            elif botVoiceChannelID:
                client.createMessage('`The line is already in use.`', msgData['channel_id'])

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
    async def on_voice_connection_finalized():
        """Once voice communication to Discord is finalized, answer if the call is incoming and  """
        # TODO improve the appearance of this code and only run when needed (incoming calls)
        voip.answerCall.set()

        # Wait for an active VoIP session before proxying traffic
        await voip.sessionStarted.wait()
        # Notify voice gateway that audio packets are starting to be sent
        await client.voiceGateway.updateSpeaking()
        RtpEndpoint.proxy(client.voiceGateway.rtpEndpoint, voip.rtpEndpoint, yCtrl=voip.rtcpEndpoint)

    @voip.event
    async def on_inbound_call():
        """On an incoming call, join the configured discord voice channel and notify guild members with a message."""
        await client.joinVoice(config.discordGuildID, config.discordVoiceChannelID)
        client.createMessage(config.incomingCallMessage, config.discordTextChannelID)

    @voip.event
    async def on_inbound_call_ended():
        """When a call is remotely terminated, leave the discord voice channel."""
        await client.leaveVoice()

    # Configure logging
    if LOGGING:
        logging.basicConfig(format='%(message)s', level=logging.DEBUG)
        os.environ['WEBSOCKETS_MAX_LOG_SIZE'] = '1000'

    # Run main co-routines
    await asyncio.gather(client.run(), voip.run())

# Entry point
if __name__ == "__main__":
    try:
        asyncio.run(main(), debug=LOGGING)
    except KeyboardInterrupt:
        print('Process interrupted')
    finally:
        print('Bot successfully shutdown')