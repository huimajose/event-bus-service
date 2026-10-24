from flask import Blueprint, current_app, jsonify, request

from services.event_service import EventError, authenticate, validate_event
from services.outbox_client import OutboxClient, OutboxConflict, OutboxUnavailable


event_bp = Blueprint('event', __name__)


@event_bp.post('/publish')
def publish():
    try:
        subject, policy = authenticate(request.headers.get('Authorization', ''), current_app.config)
        channel, event = validate_event(request.get_json(silent=True), subject, policy)
    except EventError as error:
        current_app.logger.warning('event_rejected code=%s', error.code)
        return jsonify(error=error.code), error.status

    outbox = current_app.extensions.get('event_outbox')
    if outbox is None:
        outbox = OutboxClient(current_app.config)
        current_app.extensions['event_outbox'] = outbox
    try:
        record = outbox.enqueue(channel, event)
    except OutboxConflict:
        return jsonify(error='event_id_conflict'), 409
    except OutboxUnavailable:
        current_app.logger.warning('event_enqueue_unavailable producer=%s event_id=%s', subject, event['event_id'])
        return jsonify(error='event_enqueue_unavailable', event_id=event['event_id']), 503
    current_app.logger.info('event_persisted producer=%s event_id=%s channel=%s', subject, event['event_id'], channel)
    return jsonify(status='accepted', event_id=event['event_id'], state=record['status']), 202
