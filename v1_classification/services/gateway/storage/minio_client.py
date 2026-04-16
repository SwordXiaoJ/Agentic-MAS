# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import io
import time
import logging
from datetime import timedelta
from typing import Optional
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class MinIOClient:
    """Client for MinIO object storage"""

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        secure: bool = False,
        bucket_name: str = "classify-bucket"
    ):
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self.bucket_name = bucket_name
        self._bucket_ready = False
        self._ensure_bucket_with_retry()

    def _ensure_bucket_with_retry(self, max_retries: int = 5, delay: float = 2.0):
        """Ensure bucket exists, retrying if MinIO is not ready yet"""
        for attempt in range(max_retries):
            try:
                if not self.client.bucket_exists(self.bucket_name):
                    self.client.make_bucket(self.bucket_name)
                    logger.info(f"Created bucket: {self.bucket_name}")
                self._bucket_ready = True
                return
            except (S3Error, Exception) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"MinIO not ready (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"MinIO connection failed after {max_retries} attempts: {e}")
                    logger.error("Gateway will start but storage operations will fail until MinIO is available")

    def _ensure_bucket(self):
        """Ensure bucket exists (lazy check for late MinIO availability)"""
        if self._bucket_ready:
            return
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
            self._bucket_ready = True
        except S3Error as e:
            logger.error(f"Error ensuring bucket exists: {e}")
            raise

    def upload_image(
        self,
        file_data: bytes,
        object_name: str,
        content_type: str = "image/jpeg"
    ) -> str:
        """
        Upload image to MinIO.

        Args:
            file_data: Image bytes
            object_name: Object key/path in bucket
            content_type: MIME type

        Returns:
            Object reference (s3://bucket/key)
        """
        self._ensure_bucket()
        try:
            file_obj = io.BytesIO(file_data)
            self.client.put_object(
                self.bucket_name,
                object_name,
                file_obj,
                length=len(file_data),
                content_type=content_type
            )
            logger.info(f"Uploaded image: {object_name}")
            return f"s3://{self.bucket_name}/{object_name}"

        except S3Error as e:
            logger.error(f"Error uploading image: {e}")
            raise

    def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate presigned URL for object.

        Args:
            object_name: Object key/path in bucket
            expires: URL expiration time

        Returns:
            Presigned URL
        """
        try:
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_name,
                expires=expires
            )
            return url
        except S3Error as e:
            logger.error(f"Error generating presigned URL: {e}")
            raise

    def download_image(self, object_name: str) -> bytes:
        """Download image from MinIO"""
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error(f"Error downloading image: {e}")
            raise

    def delete_image(self, object_name: str) -> None:
        """Delete image from MinIO"""
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info(f"Deleted image: {object_name}")
        except S3Error as e:
            logger.error(f"Error deleting image: {e}")
            raise
