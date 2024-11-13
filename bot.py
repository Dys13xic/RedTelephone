import discord
from discord.ext import voice_recv
import sys

EXIT_SUCCESS = 0
EXIT_FAILURE = 1

# Retrieve the discord bot token
try:
    tokenFile = open("token.txt", 'r')
    token = tokenFile.readline()

except:
    print("ERROR: Unable to open/read token.txt")
    sys.exit(EXIT_FAILURE)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print("{} has connected to Discord".format(client.user))

    guilds = client.user.mutual_guilds
    print(guilds)
    if len(guilds) != 1:
        exit(EXIT_FAILURE)

    homeGuild = guilds[0]

    for channel in homeGuild.voice_channels:
        print(channel)
        if channel.name == "General":
            global homeChannel
            homeChannel = channel
            break

@client.event
async def on_message(message):
    if client.user.mentioned_in(message) and message.channel.type == discord.ChannelType.text:
        # Call phone
        print("Attempting to call phone")
        
        # Put message in general that phone is ringing

        await joinVoice(homeChannel)

async def recvCall():
    # Maybe @ everyone?
    await joinVoice(homeChannel)



async def joinVoice(channel):
    if channel.type != discord.ChannelType.voice:
        exit(EXIT_FAILURE)

    print("Joining voice channel")
    voiceClient = await channel.connect()


client.run(token)