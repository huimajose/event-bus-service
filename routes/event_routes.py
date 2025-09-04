from flask import Blueprint, request, jsonify
from services.event_service import publish_event


event_bp = Blueprint("event", __name__)

@event_bp.route("/publish", methods=["POST"])
def publish():
    """
    Rota para publicar eventos no PubNub
    exemplo body:
    {
    
    "channel": "hospital.blocks",
    "message": {
        "hospital_id": "H001",
        "block_hash": "abc123",
        "timestamp": "2025-09-03T14:00:00Z"
    
        }
    }
    """

    data = request.json
    channel = data.get("channel")
    message = data.get("message")


    if not channel or not message:
        return jsonify({"error": "Channel and message are required"}), 400
    

    result = publish_event(channel, message)
    return jsonify(result)