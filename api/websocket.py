import logging
import traceback
import json
from datetime import datetime, timezone
from core.emulator_manager import EmulatorManager

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
                    try:
                        data = json.loads(message)
                        message_type = data.get('type')

                        if message_type == 'HEARTBEAT':
                            # Respond to heartbeat with current timestamp
                            response = {
                                'type': 'HEARTBEAT',
                                'timestamp': datetime.now(timezone.utc).isoformat(),
                                'payload': {}
                            }
                            ws.send(json.dumps(response))
                        else:
                            # Handle other message types...
                            pass

                    except json.JSONDecodeError:
                        logger.error("Invalid message format")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            logger.error(traceback.format_exc())
        finally:
            emulator_instance.remove_connection(ws)
            logger.debug("WebSocket connection closed")