import logging
import traceback
from core.emulator_manager import emulator

logger = logging.getLogger(__name__)

def register_websocket_handlers(sock, emulator_instance):
    @sock.route('/ws')
    def handle_websocket(ws):
        logger.debug("New WebSocket connection received")
        try:
            emulator_instance.add_connection(ws)
            while True:
                message = ws.receive()
                if message:
                    logger.debug(f"Received message: {message}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            logger.error(traceback.format_exc())
        finally:
            emulator_instance.remove_connection(ws)
            logger.debug("WebSocket connection closed")