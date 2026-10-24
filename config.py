import os


class Config:
    # No automatic .env loading: production receives credentials from its secret store.
    EVENT_BUS_PRODUCERS = os.getenv('EVENT_BUS_PRODUCERS', '{}')
    EVENT_BUS_ISSUER = os.getenv('EVENT_BUS_ISSUER', 'osie-services')
    EVENT_BUS_AUDIENCE = 'osie-event-bus'
    MAX_CONTENT_LENGTH = 8192
    PUBNUB_PUBLISH_KEY = os.getenv('PUBNUB_PUBLISH_KEY')
    PUBNUB_SUBSCRIBE_KEY = os.getenv('PUBNUB_SUBSCRIBE_KEY')
    PUBNUB_AUTH_KEY = os.getenv('PUBNUB_AUTH_KEY')
    PUBNUB_USER_ID = 'osie-event-bus-service'
    DATABASE_MANAGER_URL = os.getenv('DATABASE_MANAGER_URL')
    EVENT_BUS_OUTBOX_SECRET = os.getenv('EVENT_BUS_OUTBOX_SECRET')
