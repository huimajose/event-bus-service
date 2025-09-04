from pubnub_client import pubnub

def publish_event(channel: str, message: dict):
    """
    Publica um evento em canal do PubNub
    """

    envelope = pubnub.publish().channel(channel).message(message).sync()
    return {
        "status": "sucess" if not envelope.status.is_error() else "error",
        "timetoken": envelope.result.timetoken if envelope.result else None
    }