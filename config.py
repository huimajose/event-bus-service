import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    PUBNUB_PUBLISH_KEY = os.getenv("PUBNUB_PUBLISH_KEY")
    PUBNUB_SUBSCRIBE_KEY = os.getenv("PUBNUB_SUBSCRIBE_KEY")
    PUBNUB_SECRET_KEY = os.getenv("PUBNUB_SECRET_KEY")
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "True") == "True"
