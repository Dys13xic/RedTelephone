# **Red Telephone**

Red Telephone serves as an update to the classic Cold War film cliche of an emergency hotline, connecting Discord server and VOIP handset for urgent correspondence. When the Discord bot is @'d the connected VOIP phone will ring, picking up the phone will result in instant voice communciation.

> [!CAUTION]
> Currently all SIP and RTP traffic between the bot and VoIP handset is transported unencrypted and is vulnerable to interception.

## Requirements

* Unix based operating system
* Analog rotary phone
* Grandstream HT801 ATA

## Installation:

1. [Install Python.](https://www.python.org/downloads/)
```console
~$ sudo apt install python3
```
2. Clone the project repository to your machine and open it.
```console
~$ git clone https://github.com/Dys13xic/RedTelephone
~$ cd RedTelephone
```
3. Create and activate a virtual environment.
```console
~/RedTelephone$ python -m venv .venv
~/RedTelephone$ source .venv/bin/activate
```

4. Install project dependencies.
```console
~/RedTelephone$ pip install -r requirements.txt
```
5. [Create a Discord bot](https://discordpy.readthedocs.io/en/latest/discord.html)

5. Configure the following manadatory settings in config.ini
```ini
[VoIP]
# VoIP handset IP
Address=xxxxxxxxxx

[Discord]
BotToken=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
#These IDs can easily be found by enabling "Developer Mode" under "Advanced" settings in Discord. Then simply right click on your Guild, Voice Channel, or Text Channel and select Copy ID from the drop-down menu.
HomeGuildID=xxxxxxxxxx
HomeVoiceChannelID=xxxxxxxxxx
HomeTextChannelID=xxxxxxxxxx
```

6. Run the bot
```console
~/RedTelephone$ python bot.py
```

## Grandstream Configuration
1. Enable Pulse Dialing if using a rotary phone.

2. Configure Offhook-Auto-Dial
```
*47xxx*xxx*xxx*xxx*5060
```
Enter the bot's IP address and SIP port number (default ```5060```), replacing all dots ```.``` with an asterisks ```*```
> [!NOTE]
> To make direct IP calls you must include the prefix ```*47```. 

3. Enable STUN

Set NAT Traversal to ```STUN``` and input your preferred STUN server. I am currently utilizing:  ```stun.cloudflare.com:3478```

## Usage Information:

To dial the hotline join a voice channel and @ the bot in any text channel.

```
@TheHotline
```

## // TODO

