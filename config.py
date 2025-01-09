# config.py
import os
from dotenv import load_dotenv

loaded = load_dotenv()
print(f"Loaded .env file: {loaded}")

class Config:
    # Network settings - defaults suitable for local development
    HOST = os.getenv('RETRO_AGENT_HOST', '0.0.0.0')  # Allow external connections
    PORT = int(os.getenv('RETRO_AGENT_PORT', '5000'))

    # Application settings
    DEBUG = os.getenv('RETRO_AGENT_DEBUG', 'true').lower() == 'true'  # Default to debug mode

    # Storage settings
    CACHE_DIR = os.getenv('RETRO_AGENT_CACHE_DIR', './image-cache')
    MAX_CACHE_SIZE = int(os.getenv('RETRO_AGENT_MAX_CACHE_SIZE', str(10 * 1024 * 1024 * 1024)))  # 10GB default

    BINARY_MAP_X64SC = os.getenv('BINARY_MAP_X64SC', '/home/pi/vice-install/bin/x64sc')
    BINARY_MAP_X64 = os.getenv('BINARY_MAP_X64', '/home/pi/vice-install/bin/x64')
    BINARY_MAP_AMIBERRY = os.getenv('BINARY_MAP_AMIBERRY', '/home/pi/amiberry/amiberry')

    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_ENDPOINT_URL = os.getenv('AWS_ENDPOINT_URL','https://minio.krystof.io:8443')
    AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME','retro-storage-dev')
