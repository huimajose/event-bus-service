from services.event_service import EventError, producer_policy, validate_event
from services.outbox_client import OutboxClient


class NotificationInboxConsumer:
    """Persists matching notification receipts; never executes clinical actions.

    The live subscriber/replay cursor is deliberately not enabled by this adapter.
    A caller must retry failed persistence before advancing its durable cursor.
    """
    def __init__(self, config, outbox=None):
        self.config = config
        self.outbox = outbox or OutboxClient(config)

    def consume(self, channel, message, publisher_id):
        if not isinstance(publisher_id, str) or not publisher_id or publisher_id != self.config.get('PUBNUB_USER_ID'):
            raise EventError('notification_publisher_not_authorized', 403)
        if not isinstance(message, dict):
            raise EventError('invalid_event', 400)
        if type(message.get('schema_version')) is not int or message['schema_version'] != 1:
            raise EventError('invalid_event', 400)
        policies = producer_policy(self.config)
        subject = message.get('producer')
        if not isinstance(subject, str) or subject not in policies:
            raise EventError('notification_producer_not_authorized', 403)
        try:
            raw = {key: message[key] for key in ('event_id', 'event_type', 'reference_id', 'occurred_at')}
        except KeyError:
            raise EventError('invalid_event', 400) from None
        verified_channel, expected = validate_event({'channel': channel, 'message': raw}, subject, policies[subject])
        if expected != message:
            raise EventError('invalid_event', 400)
        # DBM independently compares the entire envelope with its admitted outbox.
        # SDK publisher metadata alone is not treated as cryptographic proof.
        return self.outbox.receive_notification(verified_channel, expected)
