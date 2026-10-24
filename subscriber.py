"""Legacy unauthenticated, payload-printing subscriber has been retired.

Production consumers require scoped PubNub access and a persistent inbox.
They will be implemented with the hospital integration, not this publisher gate.
"""
if __name__ == '__main__':
    raise SystemExit('Subscriber not configured: authenticated consumers and inbox pending.')
