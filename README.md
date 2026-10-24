# OSIE Event Bus — durable notification publisher

POST /publish authenticates producers, validates minimal metadata and persists in
DBM before returning 202. A separate worker publishes the saved event to PubNub.
No direct PostgreSQL connection, inline publication fallback or clinical payload.

## Prerequisites and run

Requires database-manager-service PR #78 and migration
`deploy/sql/025_pubnub_notification_outbox.sql`. Apply through the normal migration
process before enabling this version. Configure DATABASE_MANAGER_URL as the DBM
HTTPS origin, plus EVENT_BUS_OUTBOX_SECRET (same dedicated random secret >=32 bytes
in DBM and bus, distinct from producer/Auth/PubNub keys).

Install requirements.txt. Web: `gunicorn app:app --bind 0.0.0.0:$PORT`.
Worker: `python worker.py` separately; `python worker.py --once` attempts one claim.
SIGTERM stops claiming after the current attempt. GET /health is liveness only.

Set PUBNUB_PUBLISH_KEY/PUBNUB_SUBSCRIBE_KEY through the platform secret store.
If Access Manager is enabled, provision restricted PUBNUB_AUTH_KEY externally.
No administrative PubNub secret key is used. TLS and 3/5s SDK timeouts are enabled.

EVENT_BUS_PRODUCERS is secret JSON, for example (not a credential):

```json
{"hospital-hml":{"secret":"REPLACE_WITH_UNIQUE_RANDOM_SECRET_OF_AT_LEAST_32_BYTES","organization_id":"HOSPITAL-MUNICIPAL-LUBANGO","channels":["osie.network.osie-demo.organization.hcl.events"],"event_types":["clinical.access.requested"]}}
```

Assign exact channels only after checking membership; no wildcards or live registry
lookup. Use individual producer secrets. Restart web AND worker for policy updates.
Worker rechecks its effective policy on each attempt; config changes are not live.

Producer JWT: HS256, sub=policy key, iss=EVENT_BUS_ISSUER (default osie-services),
aud=osie-event-bus, actor_type=service, token_kind=service_access,
scopes includes events.publish, integer iat/exp, positive lifetime <=300s, nonempty
jti. Only the signature-verified identity is authorized. jti is not persisted.
DBM uses a separate short-lived credential, audience osie-dbm-outbox and scope
 events.outbox; producer JWTs never grant DBM access.

## Event contract

POST /publish with Authorization: Bearer <service JWT> and this strict JSON shape:

```json
{"channel":"osie.network.osie-demo.organization.hcl.events","message":{"event_id":"04d633de-5de5-49bd-8cc1-b521f1edb0fa","event_type":"clinical.access.requested","reference_id":"be80e22e-0e98-4470-a4cf-8530a9a247ff","occurred_at":"2026-10-24T08:00:00Z"}}
```

No extras. Canonical UUIDs and timestamp with timezone required. Event types:
clinical.access.requested/approved/rejected, clinical.delivery.available/received,
also restricted by producer. Server adds schema_version=1, producer and
source_organization_id from policy. No names, contacts, patient IDs, FHIR resources
or arbitrary URLs. Consumers resolve references through authorized APIs. An event
is never a clinical access grant or proof of a domain transition.

202 accepted means DBM COMMITTED, returning event_id and state. Same ID and canonical
content returns existing state, including PUBLISHED/DEAD_LETTER; changed content is
409. No resetting on re-enqueue. Retain all event fields across retries.
401 credential, 403 channel/type, 400 schema, 413 >8 KiB, 503 configuration/storage.
No persistence failure falls back to untracked publication.

Worker claims with a 60-second fenced lease. Only its current unexpired token can
ACK. Retry backoff is 2^attempt seconds, cap 300; eighth failure or expired eighth
claim becomes DEAD_LETTER. Expired earlier claims recover automatically. PubNub
acceptance followed by lost DBM ACK may republish the SAME event_id: at-least-once,
not exactly-once. PUBLISHED is PubNub ack, not hospital receipt. Consumers still
require durable inbox/deduplication before effects. No automatic record deletion.

## Validation and rollout

Run `python -m pytest tests -q` with pytest installed. DBM has separate API and
Postgres-16 integration tests. No actual PubNub publish is performed in unit tests.
SDK initialization uses synthetic keys. This does not certify the clinical flow.

Before deploy: apply migration, configure dedicated secrets and origin, approve
producer policy/PubNub grants, review historical credentials, start DBM then bus web
and worker. No .env autoload/debug. Previously versioned .env/bytecode are removed
from the new tree, not history. Secret values were not read for these changes.

Still pending: transactional outbox at the clinical producer, consumer inbox and
permissions, hospital/portal integration, durable audit, capacity/rate limiting,
retention and administrative DLQ replay. Existing rejected payloads remain rejected.

Rollback: stop the worker and preserve its table. Prefer secured phase-1 code over
the original anonymous publisher. Phase 1 changes HTTP semantics back to synchronous
publish and does not drain the queue. Never drop retained events or reset IDs.
