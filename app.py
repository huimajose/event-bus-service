from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from config import Config
from routes.event_routes import event_bp


def create_app(config=None, publisher=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    app.extensions['event_publisher'] = publisher
    app.register_blueprint(event_bp)

    @app.get('/health')
    def health():
        return jsonify(status='ok', service='event-bus-service')

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.name.lower().replace(' ', '_')), error.code

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
