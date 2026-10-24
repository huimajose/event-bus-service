from flask import Blueprint, current_app, jsonify, request

from pubnub_client import PubNubPublisher, PublishUnavailable
from services.event_service import EventError, authenticate, validate_event


event_bp = Blueprint('event', __name__)


@event_bp.post('/publish')
def publish():
    try:
        subject, policy = authenticate(request.headers.get('Authorization', ''), current_app.config)
        channel, event = validate_event(request.get_json(silent=True), subject, policy)
    except EventError as error:
        current_app.logger.warning('event_rejected code=%s', error.code)
        return jsonify(error=error.code), error.status

    publisher = current_app.extensions.get('event_publisher')
    if publisher is None:
        publisher = PubNubPublisher(current_app.config)
        current_app.extensions['event_publisher'] = publisher
    try:
        timetoken = publisher.publish(channel, event)
    except PublishUnavailable:
        current_app.logger.warning('event_publish_unavailable producer=%s event_id=%s', subject, event['event_id'])
        return jsonify(error='event_publish_unavailable', event_id=event['event_id']), 503
    current_app.logger.info('event_published producer=%s event_id=%s channel=%s', subject, event['event_id'], channel)
    return jsonify(status='published', event_id=event['event_id'], timetoken=timetoken), 200
