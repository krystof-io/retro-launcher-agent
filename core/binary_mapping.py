from typing import Dict
import logging

logger = logging.getLogger(__name__)


class BinaryMapper:
    """Maps binary names to their executable paths"""

    def __init__(self, config_module):
        self.binary_paths: Dict[str, str] = {}

        # Load mappings from config
        for key in dir(config_module):
            if key.startswith('BINARY_MAP_'):
                binary_name = key.replace('BINARY_MAP_', '').lower()
                path = getattr(config_module, key)
                if path:
                    self.binary_paths[binary_name] = path
                    logger.debug(f"Mapped binary {binary_name} to {path}")

    def get_path(self, binary_name: str) -> str:
        """Get executable path for a binary name"""
        return self.binary_paths.get(binary_name.lower())