from typing import Dict
import logging
import time
import requests
from telnetlib import Telnet
from pathlib import Path
import threading
from .process_manager import ProcessManager
from .command_handler import CommandHandler

logger = logging.getLogger(__name__)

class PlaybackTimelineHandler:
    """handles playing back events like keypresses, mountind disk images, etc. against a running emulator"""
    def __init__(self, config_module, command_handler=None):
        self.config = config_module
        self.command_handler = command_handler

    def handle_playback(self, events, images, image_paths, current_image_index, stopCallback, processManager):
        """Execute the playback timeline"""
        logger.info(f"Handling playback timeline events: {events}")

        for event in events:
            logger.info(f"Delay for {event['time_offset_seconds']}, then execute command {event['event_type']}")

            # Wait for the specified delay
            for i in range(event["time_offset_seconds"]):
                time.sleep(1)
                if not processManager.is_running:
                    return

            # Execute the command
            event_type = event["event_type"]
            logger.info(f"Processing command: {event}")

            try:
                if event_type == "END_PLAYBACK":
                    stopCallback()
                    return
                else:
                    # Execute command via command handler
                    self.command_handler.execute_command(
                        event_type,
                        event.get("event_data")
                    )
            except Exception as e:
                logger.error(f"Error executing command: {e}")
                # Consider whether to stop playback on error

        logger.info("Done with playback timeline events for this program!")