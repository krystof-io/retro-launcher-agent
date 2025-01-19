# core/command_handler.py

import logging
import requests
from telnetlib import Telnet
from pathlib import Path

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles execution of emulator commands for both curation and playback modes"""

    def __init__(self, config_module, image_paths=None):
        self.config = config_module
        self.image_paths = image_paths
        self.current_image_index = 0

    def execute_command(self, command_type, command_data=None):
        """Execute a command of the specified type with optional data"""
        try:
            if command_type == "MOUNT_NEXT_DISK":
                return self._handle_mount_next_disk()
            elif command_type == "PRESS_KEYS":
                return self._handle_press_keys(command_data.get("keys"))
            else:
                raise ValueError(f"Unknown command type: {command_type}")
        except Exception as e:
            logger.error(f"Error executing command {command_type}: {e}")
            raise

    def _handle_mount_next_disk(self):
        """Mount the next disk in sequence"""
        if not self.image_paths:
            raise ValueError("No disk images available")

        self.current_image_index += 1
        if self.current_image_index >= len(self.image_paths):
            self.current_image_index = 0

        next_image_path = str(Path(self.image_paths[self.current_image_index]).resolve())
        return self._attach_vice_image(next_image_path)

    def _handle_press_keys(self, keys):
        """Send keypress commands to the emulator"""
        if not keys:
            raise ValueError("No keys specified for keypress command")

        logger.info(f"Sending keypress: {keys}")
        response = requests.post(self.config.KEYBOARD_BANGER_URL, data=keys)
        response.raise_for_status()
        return True

    def _attach_vice_image(self, full_image_file_path, timeout=1):
        """Attach a disk image to the VICE emulator via monitor"""
        logger.info(f"Connecting to VICE to mount image: {full_image_file_path}")

        try:
            # Create and connect in one step
            tn = Telnet('localhost', 6510, timeout=timeout)

            # Wait for VICE prompt
            response = tn.read_until(b'>', timeout=timeout)
            logger.debug(f"Initial response: {response.decode('ascii')}")

            # Prepare and send command
            command_string = f'attach "{full_image_file_path}" 8\n'
            logger.debug(f"Sending command to VICE: {command_string}")
            tn.write(command_string.encode('ascii'))

            # Read the response until we see the prompt again
            result = tn.read_until(b'>', timeout=timeout)
            logger.debug(f"Result from attach: {result.decode('ascii')}")

            # Close the connection
            tn.close()

            return True
        except Exception as e:
            logger.error(f"Telnet error: {str(e)}")
            raise RuntimeError("Unable to connect or send command via telnet") from e

    def set_image_paths(self, paths):
        """Update the available disk image paths"""
        self.image_paths = paths
        self.current_image_index = 0