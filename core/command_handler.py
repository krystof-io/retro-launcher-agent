from typing import Dict
import logging
import time

logger = logging.getLogger(__name__)


class CommandHandler:
    """handles commands like keypresses, mountind disk images, etc. against a running emulator"""

    def handle_commands(self, commands, images, current_image_index, stopCallback, process):
        """Dop the things
        :param process: child process (emulator)
        """
        print("Handling commands: ", commands)
        print("Images: ", images)

        for command in commands:
            logger.info("Delay for %s, then execute command %s", command["after_time_in_seconds"], command["command"])
            for i in range(command["after_time_in_seconds"]):
                time.sleep(1)
                if process.poll() is not None:
                    return;
            commandString = command["command"]
            logger.info("Process command: %s", command)
            if (commandString == "finish"):
                stopCallback()
                return
            elif (commandString == "mount_next"):
                current_image_index += 1
                if current_image_index >= len(images):
                    current_image_index = 0
                print(f"mount {images[current_image_index]}\n".encode())

            elif (commandString == "press_keys"):
                keys = command["keys"]
                for key in keys:
                   print(f"{key}\n".encode())


