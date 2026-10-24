import argparse
import logging
import signal
import threading

from config import Config
from pubnub_client import PubNubPublisher, PublishUnavailable
from services.event_service import EventError, producer_policy, validate_event
from services.outbox_client import OutboxClient, OutboxConflict, OutboxUnavailable


class PublishWorker:
    def __init__(self, config, outbox=None, publisher=None):
        self.config = config
        self.outbox = outbox or OutboxClient(config)
        self.publisher = publisher or PubNubPublisher(config)

    def process_one(self):
        record = self.outbox.claim()
        if record is None:
            return 'idle'
        event_id, lease = record['event_id'], record['lease_token']
        saved = record['event']
        try:
            # Recheck current channel/type permissions before every publish/retry.
            policies = producer_policy(self.config)
            message = saved['message']
            subject = message['producer']
            if subject not in policies or message['event_id'] != event_id:
                raise EventError('policy_rejected', 403)
            raw = {key: message[key] for key in ('event_id', 'event_type', 'reference_id', 'occurred_at')}
            channel, event = validate_event({'channel': saved['channel'], 'message': raw}, subject, policies[subject])
            if event != message:
                raise EventError('policy_rejected', 403)
        except EventError as error:
            if error.status == 503:
                # Bad global config is an operator outage, not a poison message.
                self.outbox.complete(event_id, lease, 'retry')
                return 'retry'
            self.outbox.complete(event_id, lease, 'dead_letter')
            return 'dead_letter'
        except (KeyError, TypeError, ValueError):
            self.outbox.complete(event_id, lease, 'dead_letter')
            return 'dead_letter'
        try:
            timetoken = self.publisher.publish(channel, event)
        except PublishUnavailable:
            self.outbox.complete(event_id, lease, 'retry')
            return 'retry'
        # If this ACK fails, the lease expires and the SAME event_id is republished.
        self.outbox.complete(event_id, lease, 'published', timetoken)
        logging.info('event_publish_acknowledged event_id=%s', event_id)
        return 'published'


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    config = {name: getattr(Config, name) for name in dir(Config) if name.isupper()}
    worker = PublishWorker(config)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        try:
            result = worker.process_one()
        except (OutboxUnavailable, OutboxConflict):
            logging.warning('outbox_temporarily_unavailable_or_lease_lost')
            result = 'idle'
        if args.once:
            return
        if result == 'idle':
            stop.wait(2)


if __name__ == '__main__':
    main()
