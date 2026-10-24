import json
import re
from datetime import datetime, timezone
from uuid import UUID

import jwt


EVENT_TYPES = frozenset({
    'clinical.access.requested', 'clinical.access.approved',
    'clinical.access.rejected', 'clinical.delivery.available',
    'clinical.delivery.received',
})
CHANNEL = re.compile(r'osie\.network\.[a-z0-9-]{1,64}\.organization\.[a-z0-9-]{1,64}\.events\Z')


class EventError(Exception):
    def __init__(self, code, status):
        super().__init__(code)
        self.code, self.status = code, status


def producer_policy(config):
    try:
        policies = json.loads(config['EVENT_BUS_PRODUCERS'])
        if not isinstance(policies, dict) or not policies:
            raise ValueError()
        for name, policy in policies.items():
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,128}', name) or not isinstance(policy, dict):
                raise ValueError()
            secret = policy.get('secret')
            if not isinstance(secret, str) or len(secret.encode()) < 32:
                raise ValueError()
            organization = policy.get('organization_id')
            if not isinstance(organization, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,128}', organization):
                raise ValueError()
            channels, events = policy.get('channels'), policy.get('event_types')
            if not isinstance(channels, list) or not channels or not all(isinstance(c, str) and CHANNEL.fullmatch(c) for c in channels):
                raise ValueError()
            if not isinstance(events, list) or not events or not all(isinstance(e, str) and e in EVENT_TYPES for e in events):
                raise ValueError()
        return policies
    except (ValueError, TypeError, KeyError):
        raise EventError('publisher_policy_not_configured', 503) from None


def authenticate(header, config):
    policies = producer_policy(config)
    if not header.startswith('Bearer ') or not header[7:].strip():
        raise EventError('service_token_required', 401)
    token = header[7:].strip()
    # Unverified sub only selects a key; no claims are trusted until decode succeeds.
    try:
        subject = jwt.decode(token, options={'verify_signature': False}).get('sub')
        if not isinstance(subject, str) or subject not in policies:
            raise jwt.InvalidTokenError()
        policy = policies[subject]
        claims = jwt.decode(
            token, policy['secret'], algorithms=['HS256'],
            issuer=config['EVENT_BUS_ISSUER'], audience=config['EVENT_BUS_AUDIENCE'],
            options={'require': ['exp', 'iat', 'sub', 'jti', 'iss', 'aud']},
        )
        if (claims.get('actor_type') != 'service'
                or claims.get('token_kind') != 'service_access'
                or not isinstance(claims.get('scopes'), list)
                or 'events.publish' not in claims['scopes']
                or not isinstance(claims['jti'], str) or not claims['jti']
                or type(claims['exp']) is not int or type(claims['iat']) is not int
                or not 0 < claims['exp'] - claims['iat'] <= 300):
            raise jwt.InvalidTokenError()
        return subject, policy
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
        raise EventError('invalid_service_token', 401) from None


def validate_event(data, subject, policy):
    if not isinstance(data, dict) or set(data) != {'channel', 'message'}:
        raise EventError('invalid_event', 400)
    channel, message = data['channel'], data['message']
    if not isinstance(channel, str) or channel not in policy['channels']:
        raise EventError('channel_not_authorized', 403)
    fields = {'event_id', 'event_type', 'reference_id', 'occurred_at'}
    if not isinstance(message, dict) or set(message) != fields:
        raise EventError('invalid_event', 400)
    if not all(isinstance(value, str) for value in message.values()):
        raise EventError('invalid_event', 400)
    if message['event_type'] not in policy['event_types']:
        raise EventError('event_type_not_authorized', 403)
    try:
        for field in ('event_id', 'reference_id'):
            if str(UUID(message[field])) != message[field]:
                raise ValueError()
        occurred = datetime.fromisoformat(message['occurred_at'].replace('Z', '+00:00'))
        if occurred.tzinfo is None or len(message['occurred_at']) > 40:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise EventError('invalid_event', 400) from None
    return channel, {
        **message, 'occurred_at': occurred.astimezone(timezone.utc).isoformat(),
        'schema_version': 1, 'producer': subject,
        'source_organization_id': policy['organization_id'],
    }
