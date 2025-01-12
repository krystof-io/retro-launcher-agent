# process_manager.py

import os
import sys
import signal
import psutil
import threading
import logging
import subprocess
from typing import Optional, Tuple, Dict, Callable
from pathlib import Path
from .errors import EmulatorError

logger = logging.getLogger(__name__)


class ProcessManager:
    """Manages emulator process lifecycle and monitoring"""

    def __init__(self, state_update_callback: Callable[[Dict], None]):
        self._lock = threading.RLock()
        self._process: Optional[psutil.Process] = None
        self._subprocess: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._should_monitor = False
        self._state_update_callback = state_update_callback

    def start_process(self, command: list) -> None:
        """Start the emulator process with the given command"""
        with self._lock:
            if self._process and self._process.is_running():
                raise EmulatorError(
                    "PROCESS_EXISTS",
                    "Cannot start new process while current process is running"
                )

            try:
                # Create process with platform-specific settings
                creation_flags = 0
                if sys.platform == 'win32':
                    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

                logger.info(f"Starting process with command: {' '.join(command)}")
                self._subprocess = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creation_flags,
                    start_new_session=(sys.platform != 'win32')
                )

                self._process = psutil.Process(self._subprocess.pid)
                self._start_process_monitor()
                logger.info(f"Process started with PID: {self._process.pid}")

            except Exception as e:
                logger.error(f"Failed to start process: {e}")
                raise EmulatorError(
                    "PROCESS_START_FAILED",
                    f"Failed to start emulator process: {str(e)}"
                )

    def stop_process(self, force: bool = False) -> None:
        """Stop the emulator process"""
        with self._lock:
            if not self._process:
                logger.warning("No process to stop")
                return

            try:
                if sys.platform == 'win32':
                    self._stop_process_windows(force)
                else:
                    self._stop_process_unix(force)
            except Exception as e:
                logger.error(f"Error stopping process: {e}")
                raise EmulatorError(
                    "PROCESS_STOP_FAILED",
                    f"Failed to stop emulator process: {str(e)}"
                )
            finally:
                self._cleanup()

    def _stop_process_windows(self, force: bool) -> None:
        """Windows-specific process termination"""
        if force:
            # Kill process tree
            children = self._process.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            self._process.kill()
        else:
            # Try graceful shutdown first
            try:
                self._process.send_signal(signal.CTRL_BREAK_EVENT)
                self._process.wait(timeout=5)
            except (psutil.TimeoutExpired, Exception):
                # If graceful shutdown fails, force kill
                self._stop_process_windows(force=True)

    def _stop_process_unix(self, force: bool) -> None:
        """Unix-specific process termination"""
        try:
            pgid = os.getpgid(self._process.pid)
            if force:
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.killpg(pgid, signal.SIGTERM)
                try:
                    self._process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _start_process_monitor(self) -> None:
        """Start the process monitoring thread"""
        self._should_monitor = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_process,
            name="ProcessMonitor",
            daemon=True
        )
        self._monitor_thread.start()

    def _stop_process_monitor(self) -> None:
        """Stop the process monitoring thread"""
        self._should_monitor = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None

    def _monitor_process(self) -> None:
        """Monitor the emulator process and handle unexpected termination"""
        while self._should_monitor:
            try:
                if self._process and self._process.is_running():
                    # Update process stats
                    stats = {
                        "pid": self._process.pid,
                        "cpu_percent": self._process.cpu_percent(),
                        "memory_percent": self._process.memory_percent()
                    }
                    self._state_update_callback(stats)
                else:
                    logger.error("Emulator process terminated unexpectedly")
                    self._handle_process_termination()
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f"Error monitoring process: {e}")
                self._handle_process_termination()
                break
            threading.Event().wait(1.0)  # More efficient than time.sleep()

    def _handle_process_termination(self) -> None:
        """Handle unexpected process termination"""
        with self._lock:
            details = {
                "pid": self._process.pid if self._process else None,
                "exit_code": self._subprocess.returncode if self._subprocess else None
            }
            self._cleanup()
            raise EmulatorError(
                "PROCESS_TERMINATED",
                "Emulator process terminated unexpectedly",
                details
            )

    def _cleanup(self) -> None:
        """Clean up process-related resources"""
        self._stop_process_monitor()
        self._process = None
        self._subprocess = None

    @property
    def is_running(self) -> bool:
        """Check if the process is currently running"""
        with self._lock:
            return bool(self._process and self._process.is_running())

    def get_process_info(self) -> Optional[Dict]:
        """Get current process information"""
        with self._lock:
            if not self._process or not self._process.is_running():
                return None

            try:
                return {
                    "pid": self._process.pid,
                    "cpu_percent": self._process.cpu_percent(),
                    "memory_percent": self._process.memory_percent(),
                    "create_time": self._process.create_time()
                }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return None