# OSIE Event Bus — publisher gate

Authenticated server-to-server PubNub publishing. This phase protects the publisher;
it does not provide a durable outbox/inbox, retries, deduplication, consumer access
grants or hospital integration. Do not certify delivery from a publish acknowledgement.

## Run

Install requirements.txt and start `gunicorn app:app --bind 0.0.0.0:$PORT`.
GET /health is liveness only. Without a valid producer policy, POST /publish returns
503. Debug mode and automatic loading of a repository .env are disabled.

Set PUBNUB_PUBLISH_KEY and PUBNUB_SUBSCRIBE_KEY through the platform secret store.
If Access Manager is enabled, supply the narrowly scoped PUBNUB_AUTH_KEY granted
by the administrator. This service does not provision PubNub access grants.
The publisher does not need the PubNub administrative secret key.

EVENT_BUS_PRODUCERS is a JSON object configured as a secret, for example:

```json
{
  "hospital-hml": {
    "secret": "REPLACE_WITH_UNIQUE_RANDOM_SECRET_OF_AT_LEAST_32_BYTES",
    "organization_id": "HOSPITAL-MUNICIPAL-LUBANGO",
    "channels": ["osie.network.osie-demo.organization.hcl.events"],
    "event_types": ["clinical.access.requested"]
  }
}
```

The example is not a credential. Provision a separate random secret for each
producer; use a separate environment/keyset for tests. Empty or invalid policies
fail closed. A channel is an exact match, not a wildcard. Administrators must
assign channels only after verifying the institution's network membership.
Policies are static for this phase; no live registry/membership lookup exists yet.

JWT contract: HS256 using the producer's own secret; sub identifies the producer;
iss=EVENT_BUS_ISSUER (default osie-services), aud=osie-event-bus,
actor_type=service, token_kind=service_access, scopes includes events.publish,
iat/exp integer seconds and positive lifetime <=300 seconds, nonempty jti.
The unverified sub selects a key only; all authorization follows signature checks.
JWT replay prevention is not yet implemented: jti is required but not stored.

## Publish

POST /publish with Authorization: Bearer <service JWT> and JSON:

```json
{
  "channel": "osie.network.osie-demo.organization.hcl.events",
  "message": {
    "event_id": "04d633de-5de5-49bd-8cc1-b521f1edb0fa",
    "event_type": "clinical.access.requested",
    "reference_id": "be80e22e-0e98-4470-a4cf-8530a9a247ff",
    "occurred_at": "2026-10-24T08:00:00Z"
  }
}
```

Only event_id, event_type, reference_id and occurred_at are accepted inside
message. UUIDs must be canonical; occurred_at includes timezone. The server adds
schema_version=1, producer and source_organization_id from its verified policy.
Allowed event types are clinical.access.requested/approved/rejected and
clinical.delivery.available/received; each producer also needs its own allowlist.
Names, contacts, patient identifiers, clinical payloads, arbitrary URLs and extra
fields are rejected. Consumers must resolve references through authorized APIs;
an event is never a clinical access grant or proof that a transition happened.

200 published means PubNub acknowledged the publish and returned a timetoken.
401 rejects credentials; 403 rejects channels/types; 400 rejects schema; 413 rejects
bodies over 8 KiB; 503 means configuration or publish unavailable. Failure responses
never expose SDK errors or credentials. A timeout can occur after an actual publish;
callers must retain event_id for eventual consumer deduplication, not generate a new
ID on every retry. There is no persistent retry guarantee in this phase.

Existing anonymous /publish callers must migrate to this contract. Legacy generic
channels and raw message forwarding are no longer supported. The old subscriber
and direct publisher examples were retired. Audit entries currently use platform
logs and include technical identifiers only; durable audit remains pending.

## Tests and rollout

Run `python -m pytest tests -q` with pytest installed. Tests use synthetic credentials,
fake transport and no clinical data. CI runs the same suite. Real PubNub, Access
Manager grants, multi-instance load and authenticated hospital smoke remain required.
Do not deploy until producer policies and consumer permissions are provisioned.

The repository previously tracked .env and bytecode; this change removes them from
the new tree. It does not remove history or rotate credentials. Treat any genuine
credentials previously committed as requiring review and rotation before rollout.
No existing secret values were read or copied for this change.
