import copy
import json
import time
from unittest.mock import Mock

import jwt
import pytest
import requests

from app import create_app
from pubnub_client import PublishUnavailable
from services.outbox_client import OutboxClient, OutboxConflict, OutboxUnavailable
from worker import PublishWorker


EVENT_ID = '04d633de-5de5-49bd-8cc1-b521f1edb0fa'
LEASE = 'be80e22e-0e98-4470-a4cf-8530a9a247ff'
CHANNEL = 'osie.network.osie-demo.organization.hcl.events'
SECRET = 'a-synthetic-outbox-secret-at-least-32-bytes'


def config():
    return {'EVENT_BUS_PRODUCERS': json.dumps({'hospital-hml': {
        'secret': SECRET, 'organization_id': 'HML', 'channels': [CHANNEL],
        'event_types': ['clinical.access.requested']}})}


def record():
    return {'event_id': EVENT_ID, 'lease_token': LEASE, 'attempt_count': 1,
            'event': {'channel': CHANNEL, 'message': {
                'event_id': EVENT_ID, 'event_type': 'clinical.access.requested',
                'reference_id': LEASE, 'occurred_at': '2026-10-24T08:00:00+00:00',
                'schema_version': 1, 'producer': 'hospital-hml', 'source_organization_id': 'HML'}}}


def worker():
    store, publisher = Mock(), Mock()
    store.claim.return_value = record()
    publisher.publish.return_value = '123456789'
    return PublishWorker(config(), store, publisher), store, publisher


def test_worker_publishes_then_acks_the_lease():
    run, store, publisher = worker()
    assert run.process_one() == 'published'
    assert publisher.publish.call_args.args[1]['event_id'] == EVENT_ID
    store.complete.assert_called_once_with(EVENT_ID, LEASE, 'published', '123456789')


def test_pubnub_outage_retries_without_changing_event_id():
    run, store, publisher = worker()
    publisher.publish.side_effect = PublishUnavailable()
    assert run.process_one() == 'retry'
    store.complete.assert_called_once_with(EVENT_ID, LEASE, 'retry')


def test_ack_lost_after_publish_can_republish_same_id():
    run, store, publisher = worker()
    store.complete.side_effect = [OutboxUnavailable(), {}]
    with pytest.raises(OutboxUnavailable):
        run.process_one()
    # Simulate lease expiry/reclaim with a new lease, as DBM integration tests prove.
    reclaimed = record()
    reclaimed['lease_token'] = 'b5a38dc0-dad7-4079-a6c2-78f2bb4caf9f'
    store.claim.return_value = reclaimed
    assert run.process_one() == 'published'
    assert [call.args[1]['event_id'] for call in publisher.publish.call_args_list] == [EVENT_ID, EVENT_ID]


@pytest.mark.parametrize('mutate', [
    lambda r: r['event']['message'].update(source_organization_id='OTHER'),
    lambda r: r['event']['message'].update(producer='unknown'),
    lambda r: r['event'].update(channel='hospital.blocks'),
    lambda r: r['event']['message'].update(patient_name='not-allowed'),
])
def test_saved_event_cannot_bypass_policy(mutate):
    run, store, publisher = worker()
    saved = record()
    mutate(saved)
    store.claim.return_value = saved
    assert run.process_one() == 'dead_letter'
    publisher.publish.assert_not_called()
    store.complete.assert_called_once_with(EVENT_ID, LEASE, 'dead_letter')


def test_invalid_global_policy_retries_not_permanent_rejection():
    run, store, publisher = worker()
    run.config['EVENT_BUS_PRODUCERS'] = '{'
    assert run.process_one() == 'retry'
    publisher.publish.assert_not_called()


def test_idle_and_storage_outage_never_publish():
    run, store, publisher = worker()
    store.claim.return_value = None
    assert run.process_one() == 'idle'
    store.claim.side_effect = OutboxUnavailable()
    with pytest.raises(OutboxUnavailable):
        run.process_one()
    publisher.publish.assert_not_called()


def client():
    return OutboxClient({'DATABASE_MANAGER_URL': 'https://dbm.invalid',
                         'EVENT_BUS_OUTBOX_SECRET': SECRET})


def test_dbm_client_uses_dedicated_signed_credential(monkeypatch):
    def post(url, **kwargs):
        assert url == 'https://dbm.invalid/api/v1/pubnub-outbox/claim'
        claims = jwt.decode(kwargs['headers']['Authorization'][7:], SECRET,
                            algorithms=['HS256'], audience='osie-dbm-outbox', issuer='osie-event-bus')
        assert claims['sub'] == 'EVENT-BUS-SERVICE'
        assert claims['scopes'] == ['events.outbox']
        assert claims['exp'] - claims['iat'] == 60
        assert kwargs['timeout'] == (3, 5)
        assert kwargs['allow_redirects'] is False
        return Mock(status_code=200, json=lambda: {'event': None})
    monkeypatch.setattr(requests, 'post', post)
    assert client().claim() is None


def test_conflict_and_unavailable_are_distinct(monkeypatch):
    monkeypatch.setattr(requests, 'post', lambda *a, **k: Mock(status_code=409))
    with pytest.raises(OutboxConflict):
        client().claim()
    monkeypatch.setattr(requests, 'post', Mock(side_effect=requests.Timeout('secret-url')))
    with pytest.raises(OutboxUnavailable) as caught:
        client().claim()
    assert str(caught.value) == ''


def test_inbox_client_uses_distinct_scope_and_validates_receipt(monkeypatch):
    def post(url, **kwargs):
        assert url.endswith('/receive-notification')
        claims = jwt.decode(kwargs['headers']['Authorization'][7:], SECRET,
                            algorithms=['HS256'], audience='osie-dbm-outbox', issuer='osie-event-bus')
        assert claims['scopes'] == ['events.inbox']
        return Mock(status_code=200, json=lambda: {'event_id': EVENT_ID, 'duplicate': True})
    monkeypatch.setattr(requests, 'post', post)
    assert client().receive_notification(CHANNEL, record()['event']['message'])['duplicate'] is True


@pytest.mark.parametrize('cfg', [{}, {'DATABASE_MANAGER_URL': 'http://dbm', 'EVENT_BUS_OUTBOX_SECRET': SECRET}])
def test_configuration_fails_closed(cfg, monkeypatch):
    transport = Mock()
    monkeypatch.setattr(requests, 'post', transport)
    with pytest.raises(OutboxUnavailable):
        OutboxClient(cfg).claim()
    transport.assert_not_called()
