from pubnub.pnconfiguration import PNConfiguration
from pubnub.pubnub import PubNub
from config import Config
from pubnub.callbacks import SubscribeCallback


pnconfig = PNConfiguration()
pnconfig.subscribe_key  = Config.PUBNUB_SUBSCRIBE_KEY # type: ignore
pnconfig.publish_key = Config.PUBNUB_PUBLISH_KEY # type: ignore
pnconfig.secret_key = Config.PUBNUB_SECRET_KEY # type: ignore
pnconfig.uuid = "even-bus-service"

pubnub = PubNub(pnconfig)

def publish_message(channel: str, message: dict):
    """Publica mensagem em um canal específico"""
    envelope = pubnub.publish().channel(channel).message(message).sync()
    return envelope.result