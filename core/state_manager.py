# state_manager.py

import threading
import time
import logging
from typing import Dict, Optional
from datetime import datetime
from .states import EmulatorState, MonitorMode
from .system_monitor import SystemMonitor
from .errors import EmulatorError

logger = logging.getLogger(__name__)


class StateManager:
    """Manages emulator state and provides status information"""

    def __init__(self):
        self._lock = threading.RLock()
        self._state = EmulatorState.IDLE
        self._monitor_mode = MonitorMode.REAL
        self._current_demo: Optional[str] = None
        self._start_time: Optional[float] = None
        self._current_config: Optional[Dict] = None
        self._simulated_running = False

    @property
    def current_state(self) -> EmulatorState:
        """Get current emulator state"""
        with self._lock:
            return self._state

    @property
    def monitor_mode(self) -> MonitorMode:
        """Get current monitor mode"""
        with self._lock:
            return self._monitor_mode

    @property
    def current_demo(self) -> Optional[str]:
        """Get currently running demo ID"""
        with self._lock:
            return self._current_demo

    @property
    def uptime(self) -> int:
        """Get current uptime in seconds"""
        with self._lock:
            if not self._start_time:
                return 0
            return int(time.time() - self._start_time)

    def set_state(self, new_state: EmulatorState, demo_id: Optional[str] = None) -> None:
        """Update emulator state"""
        with self._lock:
            old_state = self._state
            self._state = new_state

            if demo_id is not None:
                self._current_demo = demo_id

            # Handle state-specific actions
            if new_state == EmulatorState.RUNNING:
                if not self._start_time:
                    self._start_time = time.time()
            elif new_state == EmulatorState.IDLE:
                self._reset_state()

            logger.info(f"State transition: {old_state} -> {new_state}")

    def set_monitor_mode(self, mode_str: str) -> Dict:
        """Switch between real process monitoring and simulated state"""
        try:
            mode = MonitorMode[mode_str]
            with self._lock:
                self._monitor_mode = mode
                if mode == MonitorMode.SIMULATED:
                    self._simulated_running = False
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
                self._reset_state()

            return {
                "status": "success",
                "state": self.status_dict
            }

    def _reset_state(self) -> None:
        """Reset state to initial values"""
        self._state = EmulatorState.IDLE
        self._current_demo = None
        self._start_time = None
        self._current_config = None

    def store_config(self, config: Dict) -> None:
        """Store current program configuration"""
        with self._lock:
            self._current_config = config

    @property
    def status_dict(self) -> Dict:
        """Get current emulator status dictionary"""
        with self._lock:
            status = {
                "running": self._state in (EmulatorState.RUNNING, EmulatorState.LAUNCHING),
                "currentDemo": self._current_demo,
                "uptime": self.uptime,
                "monitorMode": self._monitor_mode.name,
                "state": self._state.name,
                "systemStats": SystemMonitor.get_system_stats()
            }

            # Add process stats if available
            if hasattr(self, '_process_stats'):
                status['process'] = self._process_stats

            return status

    def update_process_stats(self, stats: Dict) -> None:
        """Update process statistics"""
        with self._lock:
            self._process_stats = stats

    def validate_state_transition(self, target_state: EmulatorState) -> None:
        """Validate if a state transition is allowed"""
        with self._lock:
            valid_transitions = {
                EmulatorState.IDLE: [EmulatorState.LAUNCHING],
                EmulatorState.LAUNCHING: [EmulatorState.RUNNING, EmulatorState.ERROR],
                EmulatorState.RUNNING: [EmulatorState.STOPPING, EmulatorState.ERROR],
                EmulatorState.STOPPING: [EmulatorState.IDLE, EmulatorState.ERROR],
                EmulatorState.ERROR: [EmulatorState.IDLE]
            }

            if target_state not in valid_transitions[self._state]:
                raise EmulatorError(
                    "INVALID_STATE_TRANSITION",
                    f"Cannot transition from {self._state.name} to {target_state.name}"
                )