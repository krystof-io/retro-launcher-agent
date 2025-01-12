from typing import Dict
import logging
import time
import requests
from telnetlib import Telnet
from pathlib import Path
import threading
from .process_manager import ProcessManager

logger = logging.getLogger(__name__)

class PlaybackTimelineHandler:
    """handles playing back events like keypresses, mountind disk images, etc. against a running emulator"""
    def __init__(self, config_module):
        self.config = config_module

    def handle_playback(self, events, images, image_paths, current_image_index, stopCallback, processManager):
        """Dop the things
        :param process: child process (emulator)
        """
        print("Handling playback timeline events: ", events)

        for event in events:
            logger.info("Delay for %s, then execute command %s", event["time_offset_seconds"], event["event_type"])
            for i in range(event["time_offset_seconds"]):
                time.sleep(1)
                if not processManager.is_running:
                    return
            eventType = event["event_type"]
            logger.info("Process command: %s", event)
            if (eventType == "END_PLAYBACK"):
                stopCallback()
                return
            elif (eventType == "MOUNT_NEXT_DISK"):
                current_image_index += 1
                if current_image_index >= len(images):
                    current_image_index = 0
                nextImagePath = str(Path(image_paths[current_image_index]).resolve())
                attach_vice_image(nextImagePath);
            elif (eventType == "PRESS_KEYS"):
                logger.info("Pressing keys: %s", event["event_data"]["keys"])
                keys = event["event_data"]["keys"]
                requests.post(self.config.KEYBOARD_BANGER_URL,data=keys)

        logger.info("Done with playback timeline events for this program!")


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
        print("Sending command to VICE: ", command_string)
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
