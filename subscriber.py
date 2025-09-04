from pubnub.pubnub import PubNub
from pubnub.pnconfiguration import PNConfiguration
from pubnub.callbacks import SubscribeCallback
from config import Config

pnconfig = PNConfiguration()
pnconfig.publish_key = Config.PUBNUB_PUBLISH_KEY # type: ignore
pnconfig.subscribe_key = Config.PUBNUB_SUBSCRIBE_KEY # type: ignore
pnconfig.uuid = "subscriber-service"

pubnub = PubNub(pnconfig)

class Listener(SubscribeCallback):
    def message(self, pubnub, message):
        print(f"[{message.channel}] {message.message}")

pubnub.add_listener(Listener())

# Escuta múltiplos canais
pubnub.subscribe().channels(["hospital", "patient", "alerts"]).execute()
