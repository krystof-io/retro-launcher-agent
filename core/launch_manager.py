# launch_manager.py

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from .errors import EmulatorError
from .binary_mapper import BinaryMapper


logger = logging.getLogger(__name__)


class LaunchManager:
    """Handles program launch configuration, validation, and command building"""

    def __init__(self, config, binary_mapper: BinaryMapper):
        self.config = config
        self.binary_mapper = binary_mapper


    def prepare_launch(self, config: Dict, image_paths: List[str]) -> Dict:
        """Prepare a program launch with complete validation"""
        try:
            # Validate the configuration
            self.validate_config(config)

            # Build launch command
            command = self.build_launch_command(config, image_paths)

            
            # Prepare command sequence if provided
            playback_timeline_events = None
            if "playback_timeline_events" in config:
                playback_timeline_events = self._prepare_playback_timeline_events(config)
            
            return {
                "command": command,
                "playback_timeline_events": playback_timeline_events,
                "binary": config["binary"],
                "program_title": config["program_title"]
            }

        except Exception as e:
            logger.error(f"Launch preparation failed: {e}")
            raise EmulatorError(
                "LAUNCH_PREPARATION_FAILED",
                f"Failed to prepare launch: {str(e)}"
            )

    def validate_config(self, config: Dict) -> None:
        """Validate program launch configuration"""
        # Check required fields
        required_fields = [
            "binary",
            "command_line_args",
            "images",
            "platform_name",
            "program_title",
            "programType",
            "authors"
        ]

        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            raise EmulatorError(
                "INVALID_CONFIG",
                f"Missing required fields: {', '.join(missing_fields)}"
            )

        # Validate binary existence and path
        binary_path = self.binary_mapper.get_path(config["binary"])
        if not binary_path or not os.path.exists(binary_path):
            raise EmulatorError(
                "BINARY_NOT_FOUND",
                f"Emulator binary not found: {config['binary']} at {binary_path}"
            )

        # Validate disk images configuration
        if not config["images"]:
            raise EmulatorError(
                "INVALID_CONFIG",
                "At least one disk image is required"
            )

        for image in config["images"]:
            self._validate_image_config(image)

        # Validate command list if present
        if "playback_timeline_events" in config:
            self._validate_playback_timeline_events(config["playback_timeline_events"])

    def _validate_image_config(self, image: Dict) -> None:
        """Validate a single disk image configuration"""
        required_fields = ["disk_number", "file_hash", "storage_path", "size"]
        missing_fields = [field for field in required_fields if field not in image]

        if missing_fields:
            raise EmulatorError(
                "INVALID_CONFIG",
                f"Missing image fields: {', '.join(missing_fields)}"
            )

        # Additional image validations
        if image["disk_number"] < 1:
            raise EmulatorError(
                "INVALID_CONFIG",
                "Disk number must be greater than 0"
            )

        if image["size"] <= 0:
            raise EmulatorError(
                "INVALID_CONFIG",
                "Image size must be greater than 0"
            )

    def _validate_playback_timeline_events(self, commands: List[Dict]) -> None:
        """Validate command sequence configuration"""
        for idx, cmd in enumerate(commands):
            if "command_type" not in cmd:
                raise EmulatorError(
                    "INVALID_CONFIG",
                    f"Missing 'command_type' in command sequence at position {idx}"
                )

            if "delay_seconds" not in cmd:
                raise EmulatorError(
                    "INVALID_CONFIG",
                    f"Missing 'delay_seconds' in command at position {idx}"
                )

            if cmd["delay_seconds"] < 0:
                raise EmulatorError(
                    "INVALID_CONFIG",
                    f"Invalid timing in command at position {idx}"
                )

    def build_launch_command(self, config: Dict, image_paths: List[str]) -> List[str]:
        """Build the emulator launch command"""
        binary_path = self.binary_mapper.get_path(config["binary"])
        if not binary_path:
            raise EmulatorError(
                "BINARY_NOT_FOUND",
                f"Binary path not found for {config['binary']}"
            )

        command = [binary_path]

        # Add configured arguments
        if config["command_line_args"]:
            args = config["command_line_args"].split()
            command.extend(args)

        # Add first image path for boot
        if image_paths:
            first_image_path = str(Path(image_paths[0]).resolve())
            logger.debug(f"Using boot image: {first_image_path}")
            command.append(first_image_path)

        logger.info(f"Built launch command: {' '.join(command)}")
        return command

    def _prepare_playback_timeline_events(self, config: Dict) -> List[Dict]:
        """Prepare command sequence for execution"""
        if not config.get("playback_timeline_events"):
            return []

        # Clone and validate command sequence
        sequence = []
        current_time = 0

        for cmd in config["playback_timeline_events"]:
            # Convert relative times to absolute
            command_time = current_time + cmd["delay_seconds"]
            sequence.append({
                "time": command_time,
                "command": cmd["command_type"],
                "params": {k: v for k, v in cmd.items()
                           if k not in ["command_type", "delay_seconds"]}
            })
            current_time = command_time

        return sorted(sequence, key=lambda x: x["time"])

    def get_binary_info(self, binary_name: str) -> Dict:
        """Get information about a binary"""
        binary_path = self.binary_mapper.get_path(binary_name)
        if not binary_path:
            raise EmulatorError(
                "BINARY_NOT_FOUND",
                f"Binary information not found for {binary_name}"
            )

        return {
            "name": binary_name,
            "path": binary_path,
            "exists": os.path.exists(binary_path),
            "size": os.path.getsize(binary_path) if os.path.exists(binary_path) else None
        }