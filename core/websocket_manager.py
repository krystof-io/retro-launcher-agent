# websocket_manager.py

import threading
import logging
import json
from datetime import datetime, timezone
from typing import Set, Dict, Any, Optional

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Handles WebSocket connections and message distribution"""

    def __init__(self):
        self._connections: Set = set()
        self._lock = threading.RLock()
        self._launch_id: Optional[str] = None

    def add_connection(self, ws) -> None:
        """Add a new WebSocket connection"""
        with self._lock:
            logger.debug(f"Adding WebSocket connection. Total before: {len(self._connections)}")
            self._connections.add(ws)
            logger.debug(f"Total connections after: {len(self._connections)}")

    def remove_connection(self, ws) -> None:
        """Remove a WebSocket connection"""
        with self._lock:
            logger.debug(f"Removing WebSocket connection. Total before: {len(self._connections)}")
            self._connections.discard(ws)
            logger.debug(f"Total connections after: {len(self._connections)}")

    def set_launch_id(self, launch_id: Optional[str]) -> None:
        """Set the current launch ID for message correlation"""
        with self._lock:
            self._launch_id = launch_id

    def create_message(self, msg_type: str, payload: Dict[str, Any]) -> Dict:
        """Create a protocol-compliant message envelope"""
        message = {
            "type": msg_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload
        }
        if self._launch_id:
            message["id"] = self._launch_id
        return message

    def notify_all(self, message: Dict) -> None:
        """Send message to all connected clients"""
        message_json = json.dumps(message)
        dead_connections = set()

        for ws in self._connections:
            try:
                ws.send(message_json)
            except Exception as e:
                logger.error(f"Error sending to connection: {e}")
                dead_connections.add(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self.remove_connection(ws)

    def notify_single(self, ws, message: Dict) -> None:
        """Send message to a single client"""
        try:
            ws.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending to connection: {e}")
            self.remove_connection(ws)

    def notify_status_update(self, status: Dict) -> None:
        """Notify all connections of a status update"""
        message = self.create_message("STATUS_UPDATE", status)
        self.notify_all(message)

    def notify_error(self, code: str, message: str, details: Optional[Dict] = None) -> None:
        """Notify all connections of an error"""
        error_message = self.create_message(
            "ERROR",
            {
                "code": code,
                "message": message,
                "details": details or {}
            }
        )
        self.notify_all(error_message)

    @property
    def connection_count(self) -> int:
        """Get the current number of active connections"""
        with self._lock:
            return len(self._connections)

    @property
    def has_connections(self) -> bool:
        """Check if there are any active connections"""
        with self._lock:
            return bool(self._connections)