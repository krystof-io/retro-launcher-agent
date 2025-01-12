from flask import Flask
from flask_sock import Sock
from config import Config
from api.routes import register_routes
from api.websocket import register_websocket_handlers
from core.emulator_manager import EmulatorManager
from utils.logging_config import configure_logging

app = Flask(__name__)
sock = Sock(app)
configure_logging()

def create_app():
    emulator = EmulatorManager(Config)
    # Register routes and handlers
    register_routes(app,emulator)
    register_websocket_handlers(sock, emulator)
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)

