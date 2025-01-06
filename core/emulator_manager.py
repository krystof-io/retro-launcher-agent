import threading
import time
import logging
import json
import os
import signal
import shutil
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Set, List
import psutil
from pathlib import Path
import subprocess
from .states import EmulatorState, MonitorMode
from .errors import EmulatorError
from .system_monitor import SystemMonitor
from config import Config

logger = logging.getLogger(__name__)


class EmulatorManager:
    def __init__(self):
        self._state = EmulatorState.IDLE
        self._monitor_mode = MonitorMode.REAL
        self._current_demo: Optional[str] = None
        self._start_time: Optional[float] = None
        self._process: Optional[psutil.Process] = None
        self._launch_id: Optional[str] = None
        self._connections: Set = set()
        self._lock = threading.RLock()
        self._current_config: Optional[Dict] = None

        # Ensure cache directory exists
        Path(Config.CACHE_DIR).mkdir(parents=True, exist_ok=True)
        logger.debug("EmulatorManager initialized")

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

    @property
    def status_dict(self) -> Dict:
        """Get current emulator status"""
        with self._lock:
            uptime = int(time.time() - (self._start_time or time.time()))
            status = {
                "running": self._state in (EmulatorState.RUNNING, EmulatorState.LAUNCHING),
                "currentDemo": self._current_demo,
                "uptime": uptime,
                "monitorMode": self._monitor_mode.name,
                "state": self._state.name,
                "systemStats": SystemMonitor.get_system_stats()
            }

            # Add process info if available
            if self._process and self._process.is_running():
                try:
                    status["process"] = {
                        "pid": self._process.pid,
                        "cpu_percent": self._process.cpu_percent(),
                        "memory_percent": self._process.memory_percent()
                    }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            return status

    def _validate_program_config(self, config: Dict) -> None:
        """Validate program launch configuration"""
        required_fields = ["binary", "args", "images"]
        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            raise EmulatorError(
                "INVALID_CONFIG",
                f"Missing required fields: {', '.join(missing_fields)}"
            )

        # Validate binary exists
        binary_path = os.path.join(Config.EMULATOR_BASE_PATH, config["binary"])
        if not os.path.exists(binary_path):
            raise EmulatorError(
                "BINARY_NOT_FOUND",
                f"Emulator binary not found: {config['binary']}"
            )

        # Validate disk images
        for image in config["images"]:
            required_image_fields = ["diskNumber", "fileHash", "storagePath", "size"]
            missing_image_fields = [field for field in required_image_fields if field not in image]
            if missing_image_fields:
                raise EmulatorError(
                    "INVALID_CONFIG",
                    f"Missing image fields: {', '.join(missing_image_fields)}"
                )

    def _prepare_disk_images(self, images: List[Dict]) -> List[str]:
        """Prepare disk images for launching program"""
        image_paths = []

        for image in images:
            cache_path = os.path.join(Config.CACHE_DIR, image["fileHash"])

            # If image doesn't exist in cache, we'd download it here
            # For now, just check if it exists
            if not os.path.exists(cache_path):
                raise EmulatorError(
                    "IMAGE_NOT_FOUND",
                    f"Disk image not found in cache: {image['fileHash']}"
                )

            # Verify file size
            if os.path.getsize(cache_path) != image["size"]:
                raise EmulatorError(
                    "IMAGE_CORRUPT",
                    f"Disk image size mismatch for: {image['fileHash']}"
                )

            image_paths.append(cache_path)

        return image_paths

    def _build_launch_command(self, config: Dict, image_paths: List[str]) -> List[str]:
        """Build the emulator launch command"""
        binary_path = os.path.join(Config.EMULATOR_BASE_PATH, config["binary"])
        command = [binary_path]

        # Add configured arguments
        command.extend(config["args"])

        # Add image paths
        for path in image_paths:
            command.extend(["-autostart", path])

        return command

    def launch_program(self, config: Dict) -> Dict:
        """Launch a program with the specified configuration"""
        with self._lock:
            try:
                if self._state not in (EmulatorState.IDLE, EmulatorState.ERROR):
                    raise EmulatorError(
                        "INVALID_STATE",
                        f"Cannot launch program in current state: {self._state.name}"
                    )

                # Validate configuration
                self._validate_program_config(config)

                self._state = EmulatorState.LAUNCHING
                self._launch_id = config.get("launchId")
                self._current_demo = config.get("programId")
                self._current_config = config
                self._notify_status_update()

                # Prepare disk images
                image_paths = self._prepare_disk_images(config["images"])

                # Build launch command
                command = self._build_launch_command(config, image_paths)

                # Launch the emulator
                logger.info(f"Launching emulator with command: {' '.join(command)}")
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True  # Create new process group
                )

                # Store process handle
                self._process = psutil.Process(process.pid)
                self._start_time = time.time()
                self._state = EmulatorState.RUNNING
                self._notify_status_update()

                return {
                    "status": "SUCCESS",
                    "message": "Program launched successfully",
                    "launchId": self._launch_id
                }

            except EmulatorError as e:
                self._state = EmulatorState.ERROR
                self._notify_error(e)
                return {
                    "status": "ERROR",
                    "message": e.message,
                    "code": e.code
                }
            except Exception as e:
                logger.error(f"Unexpected error in launch_program: {e}")
                self._state = EmulatorState.ERROR
                error = EmulatorError("SYSTEM_ERROR", str(e))
                self._notify_error(error)
                return {
                    "status": "ERROR",
                    "message": str(e),
                    "code": "SYSTEM_ERROR"
                }

    def stop_program(self, force: bool = False) -> Dict:
        """Stop the currently running program"""
        with self._lock:
            try:
                if self._state not in (EmulatorState.RUNNING, EmulatorState.ERROR):
                    raise EmulatorError(
                        "INVALID_STATE",
                        f"Cannot stop program in current state: {self._state.name}"
                    )

                self._state = EmulatorState.STOPPING
                self._notify_status_update()

                if self._process and self._process.is_running():
                    try:
                        # Try to stop the entire process group
                        pgid = os.getpgid(self._process.pid)
                        if force:
                            os.killpg(pgid, signal.SIGKILL)
                        else:
                            os.killpg(pgid, signal.SIGTERM)

                        # Wait for process to end
                        try:
                            self._process.wait(timeout=5)
                        except psutil.TimeoutExpired:
                            if not force:
                                # If normal termination failed, force kill
                                os.killpg(pgid, signal.SIGKILL)
                                self._process.wait(timeout=5)

                    except ProcessLookupError:
                        # Process already ended
                        pass
                    except psutil.NoSuchProcess:
                        # Process already ended
                        pass

                self._cleanup()
                return {
                    "status": "SUCCESS",
                    "message": "Program stopped successfully"
                }

            except EmulatorError as e:
                self._state = EmulatorState.ERROR
                self._notify_error(e)
                return {
                    "status": "ERROR",
                    "message": e.message,
                    "code": e.code
                }
            except Exception as e:
                logger.error(f"Unexpected error in stop_program: {e}")
                self._state = EmulatorState.ERROR
                error = EmulatorError("SYSTEM_ERROR", str(e))
                self._notify_error(error)
                return {
                    "status": "ERROR",
                    "message": str(e),
                    "code": "SYSTEM_ERROR"
                }

    def _cleanup(self):
        """Clean up after program termination"""
        self._state = EmulatorState.IDLE
        self._current_demo = None
        self._start_time = None
        self._process = None
        self._launch_id = None
        self._current_config = None
        self._notify_status_update()

    def _check_cache_size(self) -> None:
        """Check cache size and clean up if necessary"""
        total_size = sum(
            os.path.getsize(os.path.join(Config.CACHE_DIR, f))
            for f in os.listdir(Config.CACHE_DIR)
            if os.path.isfile(os.path.join(Config.CACHE_DIR, f))
        )

        if total_size > Config.MAX_CACHE_SIZE:
            # Implement cache cleanup strategy (e.g., LRU)
            logger.warning("Cache size exceeded limit, cleanup needed")
            # TODO: Implement cleanup strategy

    def add_connection(self, ws):
        """Add a WebSocket connection"""
        with self._lock:
            logger.debug(f"Adding WebSocket connection. Total before: {len(self._connections)}")
            self._connections.add(ws)
            # Send initial status
            self._notify_single(ws, self.create_message("STATUS_UPDATE", self.status_dict))
            logger.debug(f"Total connections after: {len(self._connections)}")

    def remove_connection(self, ws):
        """Remove a WebSocket connection"""
        with self._lock:
            logger.debug(f"Removing WebSocket connection. Total before: {len(self._connections)}")
            self._connections.discard(ws)
            logger.debug(f"Total connections after: {len(self._connections)}")

    def _notify_status_update(self):
        """Notify all connections of status update"""
        message = self.create_message("STATUS_UPDATE", self.status_dict)
        self._notify_all(message)

    def _notify_error(self, error: EmulatorError):
        """Notify all connections of an error"""
        message = self.create_message(
            "ERROR",
            {
                "code": error.code,
                "message": error.message,
                "details": error.details
            }
        )
        self._notify_all(message)

    def _notify_all(self, message: Dict):
        """Send message to all connected clients"""
        message_json = json.dumps(message)
        dead_connections = set()

        for ws in self._connections:
            try:
                ws.send(message_json)
            except Exception as e:
                logger.error(f"Error sending to connection: {e}")
                dead_connections.add(ws)

        for ws in dead_connections:
            self.remove_connection(ws)

    def _notify_single(self, ws, message: Dict):
        """Send message to a single client"""
        try:
            ws.send(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending to connection: {e}")
            self.remove_connection(ws)

    def set_monitor_mode(self, mode_str: str) -> Dict:
        """Switch between real process monitoring and simulated state"""
        try:
            mode = MonitorMode[mode_str]
            with self._lock:
                self._monitor_mode = mode
                if mode == MonitorMode.SIMULATED:
                    self._simulated_running = False
                self._notify_status_update()
            return {
                "status": "success",
                "mode": mode.name
            }
        except KeyError:
            raise EmulatorError(
                "INVALID_MODE",
                f"Invalid monitor mode: {mode_str}. Must be one of {[m.name for m in MonitorMode]}"
            )

    def set_simulated_state(self, running: bool, demo: Optional[str] = None) -> Dict:
        """Set emulator state for testing in simulated mode"""
        with self._lock:
            if self._monitor_mode != MonitorMode.SIMULATED:
                raise EmulatorError(
                    "INVALID_MODE",
                    "Must be in SIMULATED mode to set state directly"
                )

            if running:
                self._state = EmulatorState.RUNNING
                self._current_demo = demo
                if not self._start_time:
                    self._start_time = time.time()
            else:
                self._state = EmulatorState.IDLE
                self._current_demo = None
                self._start_time = None

            self._notify_status_update()
            return {
                "status": "success",
                "state": self.status_dict
            }



# Create singleton instance
emulator = EmulatorManager()