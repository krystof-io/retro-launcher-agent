from typing import Dict
import logging
import time
import requests
from telnetlib import Telnet
from pathlib import Path
import threading
from .process_manager import ProcessManager

logger = logging.getLogger(__name__)

class CommandHandler:
    """handles commands like keypresses, mountind disk images, etc. against a running emulator"""
    def __init__(self, config_module):
        self.config = config_module

    def handle_commands(self, commands, images, image_paths, current_image_index, stopCallback, processManager):
        """Dop the things
        :param process: child process (emulator)
        """
        print("Handling commands: ", commands)
        print("Images: ", images)

        for command in commands:
            logger.info("Delay for %s, then execute command %s", command["delay_seconds"], command["command"])
            for i in range(command["delay_seconds"]):
                time.sleep(1)
                if not processManager.is_running:
                    return
            commandString = command["command_type"]
            logger.info("Process command: %s", command)
            if (commandString == "FINISH"):
                stopCallback()
                return
            elif (commandString == "MOUNT_NEXT"):
                current_image_index += 1
                if current_image_index >= len(images):
                    current_image_index = 0
                nextImagePath = str(Path(image_paths[current_image_index]).resolve())
                attach_vice_image(nextImagePath);
            elif (commandString == "PRESS_KEYS"):
                logger.info("Pressing keys1: %s", command["command_data"])
                logger.info("Pressing keys: %s", command["keys"])
                keys = command["keys"]
                logger.info("Pressing keys: %s", keys)
                requests.post(self.config.KEYBOARD_BANGER_URL,data=keys)

        logger.info("Done with commands for this program!")


def attach_vice_image(full_image_file_path, timeout=1):
    logger.info("Connecting to vice to mount image: %s", full_image_file_path)
    try:
        # Create and connect in one step
        tn = Telnet('localhost', 6510, timeout=timeout)

        # Wait for VICE prompt
        response = tn.read_until(b'>', timeout=timeout)
        logger.debug("Initial response: %s", response.decode('ascii'))

        # Prepare and send command
        command_string = f'attach "{full_image_file_path}" 8\n'
        print("Sending command: ", command_string)
        tn.write(command_string.encode('ascii'))

        # Read the response until we see the prompt again
        result = tn.read_until(b'>', timeout=timeout)
        print("Result from attach: ", result.decode('ascii'))

        # Close the connection
        tn.close()

        return result.decode('ascii')

    except Exception as e:
        logger.error("Telnet error: %s", str(e))
        raise Exception("Unable to connect or send command via telnet") from e
