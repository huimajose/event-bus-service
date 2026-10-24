import copy
import json
from unittest.mock import Mock

import pytest

from services.event_service import EventError
from services.inbox_consumer import NotificationInboxConsumer
from services.outbox_client import OutboxConflict, OutboxUnavailable


CHANNEL = 'osie.network.osie-demo.organization.hcl.events'
EVENT_ID = '04d633de-5de5-49bd-8cc1-b521f1edb0fa'


def setup():
    config = {'PUBNUB_USER_ID': 'osie-event-bus-service', 'EVENT_BUS_PRODUCERS': json.dumps({
        'hospital-hml': {'secret': 'synthetic-inbox-test-secret-at-least-32-bytes',
                         'organization_id': 'HML', 'channels': [CHANNEL],
                         'event_types': ['clinical.access.requested']}})}
    store = Mock()
    consumer = NotificationInboxConsumer(config, store)
    message = {'event_id': EVENT_ID, 'reference_id': 'be80e22e-0e98-4470-a4cf-8530a9a247ff',
               'event_type': 'clinical.access.requested', 'occurred_at': '2026-10-24T08:00:00+00:00',
               'schema_version': 1, 'producer': 'hospital-hml', 'source_organization_id': 'HML'}
    return consumer, store, message


def test_receipt_deduplication_is_owned_by_durable_dbm():
    consumer, store, message = setup()
    store.receive_notification.side_effect = [{'event_id': EVENT_ID, 'duplicate': False},
                                              {'event_id': EVENT_ID, 'duplicate': True}]
    assert consumer.consume(CHANNEL, message, 'osie-event-bus-service')['duplicate'] is False
    assert consumer.consume(CHANNEL, message, 'osie-event-bus-service')['duplicate'] is True
    assert store.receive_notification.call_count == 2
    assert store.receive_notification.call_args.args == (CHANNEL, message)


@pytest.mark.parametrize('publisher', [None, '', 'another-publisher'])
def test_unexpected_pubnub_publisher_is_rejected(publisher):
    consumer, store, message = setup()
    with pytest.raises(EventError):
        consumer.consume(CHANNEL, message, publisher)
    store.receive_notification.assert_not_called()


@pytest.mark.parametrize('change', [{'patient_id': 'blocked'}, {'source_organization_id': 'OTHER'},
                                    {'producer': 'unknown'}, {'schema_version': True}])
def test_payload_or_source_forgery_rejected(change):
    consumer, store, message = setup()
    message.update(change)
    with pytest.raises(EventError):
        consumer.consume(CHANNEL, message, 'osie-event-bus-service')
    store.receive_notification.assert_not_called()


def test_rejects_cross_channel():
    consumer, store, message = setup()
    with pytest.raises(EventError):
        consumer.consume('osie.network.osie-demo.organization.hml.events', message,
                         'osie-event-bus-service')
    store.receive_notification.assert_not_called()


@pytest.mark.parametrize('failure', [OutboxConflict, OutboxUnavailable])
def test_persistence_failures_propagate_before_any_cursor_advance(failure):
    consumer, store, message = setup()
    store.receive_notification.side_effect = failure()
    with pytest.raises(failure):
        consumer.consume(CHANNEL, message, 'osie-event-bus-service')
