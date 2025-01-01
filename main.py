from flask import Flask, jsonify, request
from flask_sock import Sock
import json
import time
import threading
import psutil
from enum import Enum, auto
import traceback
import logging
from config import Config

# Configure logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
sock = Sock(app)


class MonitorMode(Enum):
    REAL = auto()  # Monitor actual VICE process
    SIMULATED = auto()  # Use simulated state for testing


class EmulatorState:
    def __init__(self):
        self._running = False
        self._start_time = None
        self._current_demo = None
        self._connections = set()
        self._lock = threading.RLock()
        self._monitor_mode = MonitorMode.REAL
        logger.debug("EmulatorState initialized")

    @property
    def monitor_mode(self):
        return self._monitor_mode

    @monitor_mode.setter
    def monitor_mode(self, mode):
        if not isinstance(mode, MonitorMode):
            raise ValueError("monitor_mode must be a MonitorMode enum value")
        with self._lock:
            logger.debug(f"Changing monitor mode from {self._monitor_mode} to {mode}")
            self._monitor_mode = mode

    @property
    def status_dict(self):
        logger.debug("Attempting to acquire lock for status_dict")
        start_time = time.time()
        with self._lock:
            try:
                logger.debug(f"Lock acquired for status_dict after {time.time() - start_time:.4f} seconds")
                uptime = int(time.time() - self._start_time) if self._start_time else 0
                status = {
                    'running': self._running,
                    'currentDemo': self._current_demo,
                    'uptime': uptime,
                    'monitorMode': self._monitor_mode.name
                }
                logger.debug(f"Returning status: {status}")
                return status
            except Exception as e:
                logger.error(f"Error in status_dict: {e}")
                logger.error(traceback.format_exc())
                raise
            finally:
                logger.debug("Releasing lock for status_dict")

    def update_state(self, running, demo=None):
        logger.debug(f"Attempting to update state. Running: {running}, Demo: {demo}")
        start_time = time.time()
        with self._lock:
            try:
                logger.debug(f"Lock acquired for update_state after {time.time() - start_time:.4f} seconds")
                old_state = self.status_dict
                logger.debug(f"Old state: {old_state}")

                self._running = running
                if running:
                    if not self._start_time:
                        self._start_time = time.time()
                    self._current_demo = demo
                else:
                    self._start_time = None
                    self._current_demo = None

                new_state = self.status_dict
                logger.debug(f"New state: {new_state}")

                if old_state != new_state:
                    logger.debug("State changed, notifying connections")
                    self._notify_all(new_state)
                else:
                    logger.debug("State unchanged")
            except Exception as e:
                logger.error(f"Error in update_state: {e}")
                logger.error(traceback.format_exc())
                raise
            finally:
                logger.debug("Releasing lock for update_state")

    def add_connection(self, ws):
        with self._lock:
            logger.debug(f"Adding WebSocket connection. Total connections before: {len(self._connections)}")
            self._connections.add(ws)
            logger.debug(f"Total connections after: {len(self._connections)}")

    def remove_connection(self, ws):
        with self._lock:
            logger.debug(f"Removing WebSocket connection. Total connections before: {len(self._connections)}")
            self._connections.discard(ws)
            logger.debug(f"Total connections after: {len(self._connections)}")

    def _notify_all(self, state):
        logger.debug(f"Notifying {len(self._connections)} connections")
        message = json.dumps(state)
        dead_connections = set()

        for ws in list(self._connections):  # Create a copy to safely iterate
            try:
                logger.debug(f"Sending message to connection: {ws}")
                ws.send(message)
            except Exception as e:
                logger.error(f"Error sending to connection: {e}")
                dead_connections.add(ws)

        for ws in dead_connections:
            self.remove_connection(ws)


emulator = EmulatorState()


def monitor_vice_process():
    """Monitor actual VICE process and update state accordingly"""
    logger.debug("Starting VICE process monitoring thread")
    while True:
        try:
            if emulator.monitor_mode == MonitorMode.REAL:
                vice_running = any('x64sc' in p.name() for p in psutil.process_iter(['name']))
                if vice_running != emulator._running:
                    logger.debug(f"VICE process state changed to: {vice_running}")
                    emulator.update_state(vice_running)
        except Exception as e:
            logger.error(f"Error monitoring process: {e}")
            logger.error(traceback.format_exc())
        time.sleep(1)


monitor_thread = threading.Thread(target=monitor_vice_process, daemon=True)
monitor_thread.start()


@sock.route('/ws')
def handle_websocket(ws):
    logger.debug("New WebSocket connection received")
    try:
        emulator.add_connection(ws)
        ws.send(json.dumps(emulator.status_dict))
        while True:
            ws.receive()  # Keep connection alive
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        logger.error(traceback.format_exc())
    finally:
        emulator.remove_connection(ws)
        logger.debug("WebSocket connection closed")


# Development endpoints for testing
@app.route('/dev/mode', methods=['POST'])
def set_monitor_mode():
    """Switch between real process monitoring and simulated state"""
    mode = request.json.get('mode', 'REAL')
    try:
        emulator.monitor_mode = MonitorMode[mode]
        return jsonify({
            'status': 'success',
            'mode': emulator.monitor_mode.name
        })
    except (KeyError, ValueError) as e:
        logger.error(f"Error setting monitor mode: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400


@app.route('/dev/state', methods=['POST'])
def set_state():
    """Manually set emulator state for testing"""
    if emulator.monitor_mode != MonitorMode.SIMULATED:
        return jsonify({
            'status': 'error',
            'message': 'Must be in SIMULATED mode to set state directly'
        }), 400

    running = request.json.get('running', False)
    demo = request.json.get('demo')
    emulator.update_state(running, demo)

    return jsonify({
        'status': 'success',
        'state': emulator.status_dict
    })


# Standard status endpoint for backward compatibility
@app.route('/status', methods=['GET'])
def get_status():
    return jsonify(emulator.status_dict)


if __name__ == '__main__':
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)