from gateway import Gateway, GatewayMessage

class GatewaySession(Gateway):
    def __init__(self, token):
        super().__init__(token)

    async def processMsg(self, msgObj):
        match msgObj.op:
            # Event Dispatched
            case 0:
                pass

            # Heartbeat Request
            case 1:
                pass

            # Reconnect
            case 7:
                pass

            # Invalid session
            case 9:
                pass

            # Hello
            case 10:
                data = {"token": self.token, "properties": {"os": "Linux", "browser": "redTelephone", "device": "redTelephone"}, "intents": 1 << 9}
                identifyMsg = GatewayMessage(2, data)
                pass

            # Heartbeat Ack
            case 11:
                pass

            case _:
                raise ValueError("Unsupported OP code in response {}".format(msgObj.op))
