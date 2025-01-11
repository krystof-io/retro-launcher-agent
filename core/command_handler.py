from typing import Dict
import logging
import aiohttp
import time
import requests
import asyncio, telnetlib3
from pathlib import Path

logger = logging.getLogger(__name__)

class CommandHandler:
    """handles commands like keypresses, mountind disk images, etc. against a running emulator"""
    def __init__(self, config_module):
        self.config = config_module
        self.loop = asyncio.new_event_loop()

    def handle_commands(self, commands, images, current_image_index, stopCallback, process):
        return self.loop.run_until_complete(
            self._handle_commands_async(commands, images, current_image_index, stopCallback, process)
        )

    async def _handle_commands_async(self, commands, images, current_image_index, stopCallback, process):
        """Dop the things
        :param process: child process (emulator)
        """
        print("Handling commands: ", commands)
        print("Images: ", images)

        for command in commands:
            logger.info("Delay for %s, then execute command %s", command["after_time_in_seconds"], command["command"])
            for i in range(command["after_time_in_seconds"]):
                await asyncio.sleep(1)
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
                nextImagePath = str(Path(images[current_image_index]).resolve())
                await attach_vice_image(nextImagePath);
            elif (commandString == "press_keys"):
                keys = command["keys"]
                logger.info("Pressing keys: %s", keys)
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.config.KEYBOARD_BANGER_URL, data=keys) as response:
                        if response.status != 200:
                            logger.error("Failed to send keys: %s", await response.text())
                # requests.post(self.config.KEYBOARD_BANGER_URL,data=keys)

    def __del__(self):
        """Cleanup the event loop when the handler is destroyed"""
        if self.loop and not self.loop.is_closed():
            self.loop.close()


async def attach_vice_image(full_image_file_path, timeout=10):
    """Async function to attach a disk image to VICE emulator"""
    logger.info("Connecting to vice to mount image: %s", full_image_file_path)

    async def read_until_prompt(reader):
        """Helper function to read telnet response until prompt"""
        response = []
        try:
            while True:
                chunk = await reader.read(1024)
                if not chunk:
                    break
                response.append(chunk)
                if '>' in chunk:  # VICE prompt
                    break
        except Exception as e:
            logger.error("Error reading telnet response: %s", str(e))
            raise
        return ''.join(response)

    try:
        # Connect to VICE with timeout
        reader, writer = await asyncio.wait_for(
            telnetlib3.open_connection('localhost', 6510),
            timeout=timeout
        )

        try:
            # Wait for initial prompt
            initial_response = await read_until_prompt(reader)
            logger.debug("Connected to VICE: %s", initial_response)

            # Send attach command
            command_string = f'attach "{full_image_file_path}" 8\n'
            logger.debug("Sending command: %s", command_string)
            writer.write(command_string)
            await writer.drain()

            # Read response
            result = await read_until_prompt(reader)
            logger.debug("Result from attach: %s", result)

            if "error" in result.lower():
                raise Exception(f"VICE reported error: {result}")

            return result

        finally:
            # Ensure we always close the connection
            writer.close()
            await writer.wait_closed()

    except asyncio.TimeoutError:
        logger.error("Timeout while connecting to VICE")
        raise Exception("Telnet connection timeout")
    except Exception as e:
        logger.error("Failed to connect or send command via telnet: %s", str(e))
        raise Exception("Unable to connect via telnet") from e