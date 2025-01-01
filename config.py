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