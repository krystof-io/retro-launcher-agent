# emulator_manager.py

import logging
from typing import Dict, Optional
from .websocket_manager import WebSocketManager
from .state_manager import StateManager
from .process_manager import ProcessManager
from .launch_manager import LaunchManager
from .cache_manager import CacheManager
from .binary_mapper import BinaryMapper
from .errors import EmulatorError
from .states import EmulatorState
from .playback_timeline_handler import PlaybackTimelineHandler
import threading

logger = logging.getLogger(__name__)


class EmulatorManager:
    """Main coordinator for the emulator system"""

    _instance = None
    _initialized = False

    def __new__(cls, config):
        if cls._instance is None:
            cls._instance = super(EmulatorManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, config):
        """Only initialize once"""
        if EmulatorManager._initialized:
            return

        EmulatorManager._initialized = True
        self.config = config

        # Initialize component managers
        self.ws_manager = WebSocketManager()
        self.state_manager = StateManager()
        self.process_manager = ProcessManager(self._handle_process_update)
        self.binary_mapper = BinaryMapper(self.config)
        self.launch_manager = LaunchManager(self.config, self.binary_mapper)
        self.cache_manager = CacheManager(self.config)
        self.playback_timeline_handler = PlaybackTimelineHandler(self.config)

    def launch_program(self, config: Dict) -> Dict:
        """Launch a program with the specified configuration"""
        try:
            logger.info("Launching program with config:\n%s", config)

            # Validate current state
            if self.state_manager.current_state not in (EmulatorState.IDLE, EmulatorState.ERROR):
                raise EmulatorError(
                    "INVALID_STATE",
                    f"Cannot launch program in current state: {self.state_manager.current_state.name}"
                )

            # Update state and notify
            self.state_manager.set_state(EmulatorState.LAUNCHING)
            self.ws_manager.set_launch_id(config.get("launchId"))
            self._notify_status_update()

            # Prepare disk images
            image_paths = self.cache_manager.prepare_disk_images(config["images"])

            # Prepare launch
            launch_config = self.launch_manager.prepare_launch(config, image_paths)

            # Start the process
            self.process_manager.start_process(launch_config["command"])

            # Update state and store config
            self.state_manager.set_state(EmulatorState.RUNNING)
            self.state_manager.store_config(config)
            self._notify_status_update()

            # Start a new thread to handle commands
            playback_timeline_handler_thread = threading.Thread(
                target=self.playback_timeline_handler.handle_playback,
                args=(config["playback_timeline_events"], config["images"], image_paths, 0, self.stop_program,
                      self.process_manager)
            )
            playback_timeline_handler_thread.start()

            return {
                "status": "SUCCESS",
                "message": "Program launched successfully",
                "launchId": config.get("launchId")
            }

        except EmulatorError as e:
            return self._handle_error(e)
        except Exception as e:
            logger.error(f"Unexpected error in launch_program: {e}")
            return self._handle_error(EmulatorError("SYSTEM_ERROR", str(e)))

    def curate_program(self, config: Dict) -> Dict:
        """Launch a program, without any playback timeline events"""
        try:
            logger.info("Launching program with config:\n%s", config)

            # Validate current state
            if self.state_manager.current_state not in (EmulatorState.IDLE, EmulatorState.ERROR):
                raise EmulatorError(
                    "INVALID_STATE",
                    f"Cannot launch program in current state: {self.state_manager.current_state.name}"
                )

            # Update state and notify
            self.state_manager.set_state(EmulatorState.LAUNCHING)
            self.ws_manager.set_launch_id(config.get("launchId"))
            self._notify_status_update()

            # Prepare disk images
            image_paths = self.cache_manager.prepare_disk_images(config["images"])

            # Prepare launch
            launch_config = self.launch_manager.prepare_launch(config, image_paths)

            # Start the process
            self.process_manager.start_process(launch_config["command"])

            # Update state and store config
            self.state_manager.set_state(EmulatorState.RUNNING)
            self.state_manager.store_config(config)
            self._notify_status_update()

            return {
                "status": "SUCCESS",
                "message": "Program launched for curation successfully",
                "launchId": config.get("launchId")
            }

        except EmulatorError as e:
            return self._handle_error(e)
        except Exception as e:
            logger.error(f"Unexpected error in launch_program: {e}")
            return self._handle_error(EmulatorError("SYSTEM_ERROR", str(e)))

    def stop_program(self, force: bool = False) -> Dict:
        """Stop the currently running program"""
        try:
            logger.info(f"Stopping program with force={force}")

            if self.state_manager.current_state not in (EmulatorState.RUNNING, EmulatorState.ERROR):
                raise EmulatorError(
                    "INVALID_STATE",
                    f"Cannot stop program in current state: {self.state_manager.current_state.name}"
                )

            # Update state and notify
            self.state_manager.set_state(EmulatorState.STOPPING)
            self._notify_status_update()

            # Stop the process
            self.process_manager.stop_process(force)

            # Reset state and notify
            self.state_manager.set_state(EmulatorState.IDLE)
            self._notify_status_update()

            return {
                "status": "SUCCESS",
                "message": "Program stopped successfully"
            }

        except EmulatorError as e:
            return self._handle_error(e)
        except Exception as e:
            logger.error(f"Unexpected error in stop_program: {e}")
            return self._handle_error(EmulatorError("SYSTEM_ERROR", str(e)))

    def _handle_process_update(self, stats: Dict) -> None:
        """Handle process statistics updates"""
        self.state_manager.update_process_stats(stats)
        self._notify_status_update()

    def _handle_error(self, error: EmulatorError) -> Dict:
        """Handle errors and notify clients"""
        logger.error(f"Error occurred: {error.code} - {error.message}")

        self.state_manager.set_state(EmulatorState.ERROR)
        self.ws_manager.notify_error(error.code, error.message, error.details)

        return {
            "status": "ERROR",
            "message": error.message,
            "code": error.code
        }

    def _notify_status_update(self) -> None:
        """Send status update to all connected clients"""
        self.ws_manager.notify_status_update(self.state_manager.status_dict)

    # WebSocket connection management
    def add_connection(self, ws) -> None:
        """Add a new WebSocket connection"""
        self.ws_manager.add_connection(ws)
        # Send initial status
        current_status = self.state_manager.status_dict
        self.ws_manager.notify_single(ws, self.ws_manager.create_message(
            "STATUS_UPDATE", current_status))

    def remove_connection(self, ws) -> None:
        """Remove a WebSocket connection"""
        self.ws_manager.remove_connection(ws)

    # Monitor mode management
    def set_monitor_mode(self, mode_str: str) -> Dict:
        """Switch between real and simulated monitor modes"""
        try:
            result = self.state_manager.set_monitor_mode(mode_str)
            self._notify_status_update()
            return result
        except EmulatorError as e:
            return self._handle_error(e)

    def set_simulated_state(self, running: bool, demo: Optional[str] = None) -> Dict:
        """Set simulated state for testing"""
        try:
            result = self.state_manager.set_simulated_state(running, demo)
            self._notify_status_update()
            return result
        except EmulatorError as e:
            return self._handle_error(e)

    @property
    def status_dict(self) -> Dict:
        """Get current status dictionary"""
        return self.state_manager.status_dict

