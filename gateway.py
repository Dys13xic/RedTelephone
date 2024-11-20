import asyncio
import sys

from gateway_connection import GatewayConnection, GatewayMessage

class Gateway(GatewayConnection):
    _eventListeners: dict = {}

    def __init__(self, token):
        super().__init__(token)

    def eventHandler(self, func):
        self._eventListeners[func.__name__] = func
        return func

    async def processMsg(self, msgObj):
        match msgObj.op:
            # Event Dispatched
            case 0:
                # Update sequence number
                if(msgObj.s):
                    self.setLastSequence(msgObj.s)

                if(msgObj.t == "READY"):
                    # TODO grab info for resuming session
                    pass
                # Pass to relevant event handler
                elif(msgObj.t.lower() in self._eventListeners.keys()):
                    self._eventListeners[msgObj.t.lower()](msgObj)

            # Heartbeat Request
            # TODO, see if you can reset sleep timer on HeartBeat request (as this function will run immediately, resulting in an early follow-up heartbeat)
            case 1:
                msgObj = GatewayMessage(1, self._lastSequence)
                await self.send(msgObj)

            # Reconnect
            case 7:
                pass

            # Invalid session
            case 9:
                pass

            # Hello
            case 10:
                # Update heartbeat interval
                if("heartbeat_interval" in msgObj.d):
                    self.setHeartbeatInterval(msgObj.d["heartbeat_interval"])
                # Identify to API
                data = {"token": self.token, "properties": {"os": "Linux", "browser": "redTelephone", "device": "redTelephone"}, "intents": 1 << 9}
                identifyMsg = GatewayMessage(2, data)
                await self.send(identifyMsg)

            # Heartbeat Ack
            case 11:
                pass

            case _:
                raise ValueError("Unsupported OP code in msg {}".format(msgObj.op))

if __name__ == "__main__":

    # Retrieve the discord bot token
    try:
        tokenFile = open("token.txt", 'r')
        token = tokenFile.readline()
    except:
        print("ERROR: Unable to open/read token.txt")
        sys.exit(1)

    gw = Gateway(token)

    @gw.eventHandler
    def ready(msgObj):
        print("xxxxxxxxxxxxxxxx")
        print(msgObj)
        print("XXXXXXXXXXXXXXXXX")

    # asyncio.run(gw._run())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(gw._run())
    finally:
        loop.close()