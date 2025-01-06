from typing import Optional, Dict

class EmulatorError(Exception):
    """Base class for emulator-related errors"""
    def __init__(self, code: str, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)