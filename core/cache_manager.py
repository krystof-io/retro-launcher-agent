# cache_manager.py

import os
import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
import boto3
from botocore.client import Config
from .errors import EmulatorError

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages local disk image cache and S3/MinIO interactions"""

    def __init__(self, config):
        self._lock = threading.RLock()
        self.cache_dir = Path(config.CACHE_DIR)
        self.max_cache_size = config.MAX_CACHE_SIZE

        # Create cache directory if it doesn't exist
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

    def prepare_disk_images(self, images: List[Dict]) -> List[str]:
        """Prepare all disk images for a program launch"""
        with self._lock:
            try:
                # Sort images by disk number
                sorted_images = sorted(images, key=lambda x: x["disk_number"])
                image_paths = []

                for image in sorted_images:
                    cached_path = self.get_disk_image(
                        storage_path=image["storage_path"],
                        file_hash=image["file_hash"],
                        expected_size=image["size"]
                    )
                    image_paths.append(str(cached_path))

                return image_paths

            except Exception as e:
                logger.error(f"Failed to prepare disk images: {e}")
                raise EmulatorError(
                    "IMAGE_PREPARATION_FAILED",
                    f"Failed to prepare disk images: {str(e)}"
                )

    def get_disk_image(self, storage_path: str, file_hash: str, expected_size: int) -> Path:
        """Get a disk image from cache or download it"""
        try:
            # Check cache size and cleanup if needed
            self._check_cache_size()

            # Get cached path and check if file exists
            cached_path = self._get_cached_path(file_hash, Path(storage_path).name)

            if self._is_valid_cached_file(cached_path, file_hash, expected_size):
                logger.info(f"Using cached file: {cached_path}")
                return cached_path

            # Download and verify file
            return self._download_and_verify(storage_path, cached_path, file_hash, expected_size)

        except Exception as e:
            logger.error(f"Failed to get disk image {storage_path}: {e}")
            raise EmulatorError(
                "IMAGE_RETRIEVAL_FAILED",
                f"Failed to get disk image: {str(e)}",
                {"storage_path": storage_path, "file_hash": file_hash}
            )

    def _get_cached_path(self, file_hash: str, filename: str) -> Path:
        """Get the full path where a file should be cached"""
        hash_dir = self.cache_dir / file_hash
        hash_dir.mkdir(exist_ok=True)
        return hash_dir / filename

    def _is_valid_cached_file(self, file_path: Path, expected_hash: str, expected_size: int) -> bool:
        """Check if a cached file is valid"""
        if not file_path.exists():
            return False

        # Check file size first (faster than hash)
        if file_path.stat().st_size != expected_size:
            logger.warning(f"Cached file {file_path} has incorrect size")
            file_path.unlink()
            return False

        # Verify file hash
        if not self._verify_file_hash(file_path, expected_hash):
            logger.warning(f"Cached file {file_path} failed hash verification")
            file_path.unlink()
            return False

        return True

    def _verify_file_hash(self, file_path: Path, expected_hash: str) -> bool:
        """Verify the SHA256 hash of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest() == expected_hash

    def _download_and_verify(self, storage_path: str, cached_path: Path,
                             expected_hash: str, expected_size: int) -> Path:
        """Download and verify a file from MinIO"""
        logger.info(f"Downloading {storage_path} from MinIO to {cached_path}")

        try:
            # Download file
            self.s3_client.download_file(
                self.bucket,
                storage_path,
                str(cached_path)
            )

            # Verify downloaded file
            if not self._is_valid_cached_file(cached_path, expected_hash, expected_size):
                raise EmulatorError(
                    "IMAGE_VERIFICATION_FAILED",
                    "Downloaded file failed verification"
                )

            logger.info(f"Successfully downloaded and verified {storage_path}")
            return cached_path

        except Exception as e:
            if cached_path.exists():
                cached_path.unlink()
            raise EmulatorError(
                "DOWNLOAD_FAILED",
                f"Failed to download file: {str(e)}"
            )

    def _check_cache_size(self) -> None:
        """Check cache size and clean up if necessary"""
        total_size = sum(
            f.stat().st_size
            for f in self.cache_dir.glob('**/*')
            if f.is_file()
        )

        if total_size > self.max_cache_size:
            logger.warning("Cache size exceeded limit, starting cleanup")
            self._cleanup_cache(total_size)

    def _cleanup_cache(self, current_size: int) -> None:
        """Clean up cache using LRU strategy"""
        # Get all files with their access times
        files = []
        for path in self.cache_dir.glob('**/*'):
            if path.is_file():
                files.append((path, path.stat().st_atime))

        # Sort by access time (oldest first)
        files.sort(key=lambda x: x[1])

        # Remove files until we're under the limit
        target_size = self.max_cache_size * 0.8  # Aim for 80% capacity
        for file_path, _ in files:
            if current_size <= target_size:
                break

            size = file_path.stat().st_size
            try:
                file_path.unlink()
                current_size -= size
                logger.debug(f"Removed cached file: {file_path}")
            except OSError as e:
                logger.error(f"Failed to remove cached file {file_path}: {e}")

        # Remove empty directories
        for path in self.cache_dir.glob('**/*'):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()

    def clear_cache(self) -> None:
        """Clear the entire cache directory"""
        with self._lock:
            try:
                # Remove all files
                for path in self.cache_dir.glob('**/*'):
                    if path.is_file():
                        path.unlink()

                # Remove empty directories
                for path in self.cache_dir.glob('**/*'):
                    if path.is_dir():
                        path.rmdir()

                logger.info("Cache cleared successfully")

            except Exception as e:
                logger.error(f"Failed to clear cache: {e}")
                raise EmulatorError(
                    "CACHE_CLEAR_FAILED",
                    f"Failed to clear cache: {str(e)}"
                )

    def get_cache_stats(self) -> Dict:
        """Get current cache statistics"""
        with self._lock:
            total_size = 0
            file_count = 0

            for path in self.cache_dir.glob('**/*'):
                if path.is_file():
                    total_size += path.stat().st_size
                    file_count += 1

            return {
                "total_size": total_size,
                "max_size": self.max_cache_size,
                "usage_percent": (total_size / self.max_cache_size) * 100,
                "file_count": file_count
            }