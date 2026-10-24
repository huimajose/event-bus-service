import threading


class PublishUnavailable(Exception):
    pass


class PubNubPublisher:
    def __init__(self, config):
        self.config = config
        self._client = None
        self._lock = threading.Lock()

    def _get_client(self):
        with self._lock:
            if self._client is None:
                if not self.config.get('PUBNUB_PUBLISH_KEY') or not self.config.get('PUBNUB_SUBSCRIBE_KEY'):
                    raise PublishUnavailable()
                from pubnub.pnconfiguration import PNConfiguration
                from pubnub.pubnub import PubNub

                settings = PNConfiguration()
                settings.publish_key = self.config['PUBNUB_PUBLISH_KEY']
                settings.subscribe_key = self.config['PUBNUB_SUBSCRIBE_KEY']
                settings.auth_key = self.config.get('PUBNUB_AUTH_KEY')
                settings.user_id = self.config['PUBNUB_USER_ID']
                settings.ssl = True
                settings.connect_timeout = 3
                settings.non_subscribe_request_timeout = 5
                self._client = PubNub(settings)
            return self._client

    def publish(self, channel, message):
        try:
            envelope = self._get_client().publish().channel(channel).message(message).sync()
            if envelope.status.is_error() or not envelope.result or not envelope.result.timetoken:
                raise PublishUnavailable()
            return str(envelope.result.timetoken)
        except Exception:
            # SDK exceptions can contain URLs and credentials; never return or log them.
            raise PublishUnavailable() from None
