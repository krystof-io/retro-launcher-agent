import os
import sys
import signal
import psutil
import subprocess
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ProcessManager:
    """Handles cross-platform process management"""

    @staticmethod
    def create_process(command: list) -> Tuple[subprocess.Popen, psutil.Process]:
        """
        Create a new process with appropriate platform-specific settings
        Returns tuple of (subprocess.Popen, psutil.Process)
        """
        creation_flags = 0
        if sys.platform == 'win32':
            # On Windows, create new process group
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            # On Unix, we'll use process groups via os.setpgid
            creation_flags = 0

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
            start_new_session=(sys.platform != 'win32'),  # Use new session on Unix
        )

        return process, psutil.Process(process.pid)

    @staticmethod
    def terminate_process(process: psutil.Process, force: bool = False) -> None:
        """
        Terminate a process and its children
        Args:
            process: psutil.Process to terminate
            force: If True, use SIGKILL/TERMINATE instead of SIGTERM/CTRL_BREAK
        """
        if not process.is_running():
            return

        try:
            if sys.platform == 'win32':
                ProcessManager._terminate_windows(process, force)
            else:
                ProcessManager._terminate_unix(process, force)
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"Process already terminated or access denied: {e}")
        except Exception as e:
            logger.error(f"Error terminating process: {e}")
            raise

    @staticmethod
    def _terminate_windows(process: psutil.Process, force: bool) -> None:
        """Windows-specific process termination"""
        if force:
            # Kill process tree
            children = process.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            process.kill()
        else:
            # Try graceful shutdown first using CTRL_BREAK_EVENT
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                # Wait up to 5 seconds for graceful shutdown
                process.wait(timeout=5)
            except (psutil.TimeoutExpired, Exception):
                # If graceful shutdown fails, force kill the process tree
                ProcessManager._terminate_windows(process, force=True)

    @staticmethod
    def _terminate_unix(process: psutil.Process, force: bool) -> None:
        """Unix-specific process termination"""
        try:
            pgid = os.getpgid(process.pid)
            if force:
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.killpg(pgid, signal.SIGTERM)
                try:
                    # Wait for process group to end
                    process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    # If graceful shutdown fails, force kill
                    os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            # Process group already ended
            pass