import os
from pathlib import Path
import hashlib
import logging
import boto3
from botocore.client import Config

logger = logging.getLogger(__name__)

class DiskImageCache:
    def __init__(self, config):
        self.cache_dir = Path(config.CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Using cache directory: {self.cache_dir}")

        # Initialize S3 client for MinIO
        self.s3_client = boto3.client(
            's3',
            endpoint_url=config.AWS_ENDPOINT_URL,
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4'),
            verify=False  # For self-signed certs, set to True in production if cert is valid
        )
        self.bucket = config.AWS_BUCKET_NAME

    def get_cached_path(self, file_hash: str, filename: str) -> Path:
        """Get the full path where a file should be cached"""
        # Create hash subdirectory if it doesn't exist
        hash_dir = self.cache_dir / file_hash
        hash_dir.mkdir(exist_ok=True)
        return hash_dir / filename

    def is_cached(self, file_hash: str, filename: str) -> bool:
        """Check if a file is already in the cache"""
        cached_path = self.get_cached_path(file_hash, filename)
        return cached_path.exists()

    def verify_file_hash(self, file_path: Path, expected_hash: str) -> bool:
        """Verify the SHA256 hash of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest() == expected_hash

    def download_to_cache(self, storage_path: str, file_hash: str, expected_size: int) -> Path:
        """
        Download a file from MinIO to the cache directory if it's not already there.
        Returns the path to the cached file.
        """
        # Extract filename from storage path
        filename = Path(storage_path).name
        cached_path = self.get_cached_path(file_hash, filename)

        # If file is already cached and correct size, skip download
        if cached_path.exists():
            if cached_path.stat().st_size == expected_size:
                logger.info(f"File {filename} ({file_hash}) already in cache")
                if self.verify_file_hash(cached_path, file_hash):
                    return cached_path
                else:
                    logger.warning(f"Cached file {filename} ({file_hash}) failed hash verification")
                    cached_path.unlink()
            else:
                logger.warning(f"Cached file {filename} ({file_hash}) has incorrect size")
                cached_path.unlink()

        # Download file
        logger.info(f"Downloading {storage_path} from MinIO to {cached_path}")
        try:
            self.s3_client.download_file(
                self.bucket,
                storage_path,
                str(cached_path)
            )
        except Exception as e:
            logger.error(f"Failed to download {storage_path}: {e}")
            if cached_path.exists():
                cached_path.unlink()
            raise

        # Verify size and hash
        if not cached_path.exists():
            raise FileNotFoundError(f"Download failed for {storage_path}")

        if cached_path.stat().st_size != expected_size:
            cached_path.unlink()
            raise ValueError(f"Downloaded file size mismatch for {storage_path}")

        if not self.verify_file_hash(cached_path, file_hash):
            cached_path.unlink()
            raise ValueError(f"Hash verification failed for {storage_path}")

        logger.info(f"Successfully downloaded and verified {storage_path}")
        return cached_path

    def get_disk_image(self, storage_path: str, file_hash: str, expected_size: int) -> Path:
        """
        Get a disk image, either from cache or downloading it.
        Returns the path to the image file.
        """
        try:
            return self.download_to_cache(storage_path, file_hash, expected_size)
        except Exception as e:
            logger.error(f"Failed to get disk image {storage_path}: {e}")
            raise