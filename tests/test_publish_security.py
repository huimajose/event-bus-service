import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest

from app import create_app
from pubnub_client import PubNubPublisher, PublishUnavailable
from services.outbox_client import OutboxUnavailable


SECRET = 'synthetic-event-bus-test-secret-32-bytes'
CHANNEL = 'osie.network.osie-demo.organization.hcl.events'
OTHER = 'osie.network.osie-demo.organization.hml.events'


@pytest.fixture
def setup():
    publisher = Mock()
    publisher.enqueue.return_value = {'event_id': '04d633de-5de5-49bd-8cc1-b521f1edb0fa', 'status': 'PENDING'}
    config = {'TESTING': True, 'EVENT_BUS_PRODUCERS': json.dumps({
        'hospital-hml': {'secret': SECRET, 'organization_id': 'HML',
                         'channels': [CHANNEL], 'event_types': ['clinical.access.requested']},
    })}
    app = create_app(config, publisher)
    return app.test_client(), publisher, app


def token(**overrides):
    now = int(time.time())
    claims = {'sub': 'hospital-hml', 'iss': 'osie-services', 'aud': 'osie-event-bus',
              'iat': now, 'exp': now + 60, 'jti': 'test-id', 'actor_type': 'service',
              'token_kind': 'service_access', 'scopes': ['events.publish']}
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm='HS256')


def payload():
    return {'channel': CHANNEL, 'message': {
        'event_id': '04d633de-5de5-49bd-8cc1-b521f1edb0fa',
        'event_type': 'clinical.access.requested',
        'reference_id': 'be80e22e-0e98-4470-a4cf-8530a9a247ff',
        'occurred_at': '2026-10-24T08:00:00Z',
    }}


def send(client, body=None, bearer=None):
    return client.post('/publish', json=payload() if body is None else body,
                       headers={'Authorization': 'Bearer ' + (bearer or token())})


def test_publish_derives_source_and_does_not_echo_message(setup):
    client, publisher, _ = setup
    response = send(client)
    assert response.status_code == 202
    channel, event = publisher.enqueue.call_args.args
    assert channel == CHANNEL
    assert event['source_organization_id'] == 'HML'
    assert event['producer'] == 'hospital-hml'
    assert event['schema_version'] == 1
    assert set(response.json) == {'status', 'event_id', 'state'}


def test_no_token_never_publishes(setup):
    client, publisher, _ = setup
    assert client.post('/publish', json=payload()).status_code == 401
    publisher.enqueue.assert_not_called()


@pytest.mark.parametrize('claims', [
    {'sub': 'unknown'}, {'actor_type': 'user'}, {'token_kind': 'user_refresh'},
    {'scopes': []}, {'scopes': 'events.publish'}, {'aud': 'users'}, {'iss': 'wrong'},
    {'exp': 1}, {'iat': int(time.time()) + 3600}, {'jti': ''},
    {'exp': int(time.time()) + 1000}, {'exp': '9999999999'},
])
def test_invalid_identity_rejected(setup, claims):
    client, publisher, _ = setup
    assert send(client, bearer=token(**claims)).status_code == 401
    publisher.enqueue.assert_not_called()


def test_bad_signature(setup):
    client, publisher, _ = setup
    claims = jwt.decode(token(), options={'verify_signature': False})
    wrong = jwt.encode(claims, 'another-synthetic-secret-at-least-32-bytes', algorithm='HS256')
    assert send(client, bearer=wrong).status_code == 401
    publisher.enqueue.assert_not_called()


@pytest.mark.parametrize('channel', [OTHER, 'hospital.blocks', '*', CHANNEL + '.extra', None, []])
def test_channel_boundary(setup, channel):
    client, publisher, _ = setup
    body = payload()
    body['channel'] = channel
    assert send(client, body).status_code == 403
    publisher.enqueue.assert_not_called()


@pytest.mark.parametrize('extra', ['name', 'phone', 'email', 'patient_id', 'resource', 'source_organization_id'])
def test_clinical_or_identity_fields_rejected(setup, extra):
    client, publisher, _ = setup
    body = payload()
    body['message'][extra] = 'must-not-be-published'
    assert send(client, body).status_code == 400
    publisher.enqueue.assert_not_called()


@pytest.mark.parametrize('body', [[], 'text', {}, {'channel': CHANNEL}, {'channel': CHANNEL, 'message': []}])
def test_invalid_json_shape(setup, body):
    client, publisher, _ = setup
    assert send(client, body).status_code == 400
    publisher.enqueue.assert_not_called()


def test_null_json(setup):
    client, publisher, _ = setup
    response = client.post('/publish', data='null', content_type='application/json',
                           headers={'Authorization': 'Bearer ' + token()})
    assert response.status_code == 400
    publisher.enqueue.assert_not_called()


@pytest.mark.parametrize('field,value', [('event_id', 'patient-name'), ('reference_id', 'P-123'),
    ('occurred_at', '2026-10-24'), ('event_type', 'clinical.delivery.received')])
def test_invalid_metadata(setup, field, value):
    client, publisher, _ = setup
    body = payload()
    body['message'][field] = value
    assert send(client, body).status_code in (400, 403)
    publisher.enqueue.assert_not_called()


@pytest.mark.parametrize('policy', ['{}', '[]', '{', '{"x":{"secret":"short"}}'])
def test_missing_or_bad_policy_fails_closed(setup, policy):
    client, publisher, app = setup
    app.config['EVENT_BUS_PRODUCERS'] = policy
    assert send(client).status_code == 503
    publisher.enqueue.assert_not_called()


def test_payload_limit(setup):
    client, publisher, _ = setup
    body = payload()
    body['message']['extra'] = 'a' * 9000
    assert send(client, body).status_code == 413
    publisher.enqueue.assert_not_called()


def test_transport_failure_does_not_leak_credentials(setup, caplog):
    client, publisher, _ = setup
    publisher.enqueue.side_effect = OutboxUnavailable('sensitive-upstream-url')
    response = send(client)
    assert response.status_code == 503
    assert 'sensitive-upstream-url' not in response.text + caplog.text
    assert SECRET not in response.text + caplog.text


@pytest.mark.parametrize('error,result', [(True, None), (False, None), (False, SimpleNamespace(timetoken=None))])
def test_sdk_unsuccessful_envelope_is_not_success(error, result):
    publisher = PubNubPublisher({})
    client = Mock()
    client.publish.return_value.channel.return_value.message.return_value.sync.return_value = SimpleNamespace(
        status=SimpleNamespace(is_error=lambda: error), result=result)
    publisher._client = client
    with pytest.raises(PublishUnavailable):
        publisher.publish(CHANNEL, payload()['message'])


def test_sdk_exception_is_sanitized():
    publisher = PubNubPublisher({})
    client = Mock()
    client.publish.side_effect = RuntimeError('secret-url')
    publisher._client = client
    with pytest.raises(PublishUnavailable) as caught:
        publisher.publish(CHANNEL, {})
    assert str(caught.value) == ''


def test_sdk_success_timetoken():
    publisher = PubNubPublisher({})
    client = Mock()
    client.publish.return_value.channel.return_value.message.return_value.sync.return_value = SimpleNamespace(
        status=SimpleNamespace(is_error=lambda: False), result=SimpleNamespace(timetoken=123))
    publisher._client = client
    assert publisher.publish(CHANNEL, {}) == '123'


def test_only_one_publish_route_and_safe_health(setup):
    client, _, app = setup
    assert sum(rule.rule == '/publish' for rule in app.url_map.iter_rules()) == 1
    assert client.get('/health').json == {'status': 'ok', 'service': 'event-bus-service'}


def test_pinned_sdk_initializes_without_network_or_admin_secret():
    publisher = PubNubPublisher({'PUBNUB_PUBLISH_KEY': 'pub-c-test',
                                'PUBNUB_SUBSCRIBE_KEY': 'sub-c-test',
                                'PUBNUB_USER_ID': 'osie-event-bus-service'})
    client = publisher._get_client()
    try:
        assert client.config.user_id == 'osie-event-bus-service'
        assert client.config.ssl is True
        assert client.config.connect_timeout == 3
        assert client.config.non_subscribe_request_timeout == 5
        assert not client.config.secret_key
        assert publisher._get_client() is client
    finally:
        client.stop()
