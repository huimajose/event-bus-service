import time
from urllib.parse import urlparse

import jwt
import requests


class OutboxUnavailable(Exception):
    pass


class OutboxConflict(Exception):
    pass


class OutboxClient:
    def __init__(self, config):
        self.base_url = (config.get('DATABASE_MANAGER_URL') or '').rstrip('/')
        self.secret = config.get('EVENT_BUS_OUTBOX_SECRET')

    def _post(self, action, payload):
        if (not isinstance(self.secret, str) or len(self.secret.encode()) < 32
                or urlparse(self.base_url).scheme != 'https'):
            raise OutboxUnavailable()
        now = int(time.time())
        token = jwt.encode({'sub': 'EVENT-BUS-SERVICE', 'actor_type': 'service',
                            'token_kind': 'service_access', 'scopes': ['events.outbox'],
                            'iat': now, 'exp': now + 60, 'iss': 'osie-event-bus',
                            'aud': 'osie-dbm-outbox'}, self.secret, algorithm='HS256')
        try:
            response = requests.post(self.base_url + '/api/v1/pubnub-outbox/' + action,
                                     json=payload, timeout=(3, 5),
                                     headers={'Authorization': 'Bearer ' + token})
            if response.status_code == 409:
                raise OutboxConflict()
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (requests.RequestException, ValueError, TypeError):
            raise OutboxUnavailable() from None

    def enqueue(self, channel, message):
        data = self._post('enqueue', {'channel': channel, 'message': message})
        if data.get('event_id') != message['event_id'] or data.get('status') not in {
            'PENDING', 'PROCESSING', 'RETRY', 'PUBLISHED', 'DEAD_LETTER'
        }:
            raise OutboxUnavailable()
        return data

    def claim(self):
        data = self._post('claim', {})
        if 'event' not in data or (data['event'] is not None and not isinstance(data['event'], dict)):
            raise OutboxUnavailable()
        return data['event']

    def complete(self, event_id, lease, outcome, timetoken=None):
        data = self._post('complete', {'event_id': event_id, 'lease_token': lease,
                                       'outcome': outcome, 'timetoken': timetoken})
        expected = {'published': {'PUBLISHED'}, 'retry': {'RETRY', 'DEAD_LETTER'},
                    'dead_letter': {'DEAD_LETTER'}}[outcome]
        if data.get('event_id') != event_id or data.get('status') not in expected:
            raise OutboxUnavailable()
        return data
