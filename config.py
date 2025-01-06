# config.py
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Network settings - defaults suitable for local development
    HOST = os.getenv('RETRO_AGENT_HOST', '0.0.0.0')  # Allow external connections
    PORT = int(os.getenv('RETRO_AGENT_PORT', '5000'))

    # Application settings
    DEBUG = os.getenv('RETRO_AGENT_DEBUG', 'true').lower() == 'true'  # Default to debug mode

    # Storage settings
    CACHE_DIR = os.getenv('RETRO_AGENT_CACHE_DIR', './images')
    MAX_CACHE_SIZE = int(os.getenv('RETRO_AGENT_MAX_CACHE_SIZE', str(10 * 1024 * 1024 * 1024)))  # 10GB default