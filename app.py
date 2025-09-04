from flask import Flask, request, jsonify
from pubnub_client import publish_message

app = Flask(__name__)

@app.route("/publish", methods=["POST"])
def publish():
    data = request.get_json(silent=True) or {}  # garante dict
    channel = data.get("channel")
    message = data.get("message")
    if not channel or not message:
        return jsonify({"error": "channel e message são obrigatórios"}), 400
    
    result = publish_message(channel, message)
    return jsonify({
        "status": "ok",
        "channel": channel,
        "message": message,
        "timetoken": result.timetoken
    })

if __name__ == "__main__":
    app.run(port=5000, debug=True)
