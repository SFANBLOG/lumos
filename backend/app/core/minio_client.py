"""
MinIO 对象存储客户端.

提供文件上传、预签名 URL 等功能。
"""

from __future__ import annotations

from functools import lru_cache

from loguru import logger
from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings

settings = get_settings()


@lru_cache
def get_minio_client() -> Minio:
    """获取 MinIO 客户端单例."""
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    return client


def ensure_bucket(bucket_name: str | None = None) -> None:
    """确保 bucket 存在."""
    client = get_minio_client()
    bucket = bucket_name or settings.minio_bucket
    found = client.bucket_exists(bucket)
    if not found:
        client.make_bucket(bucket)
        logger.info(f"🪣 MinIO bucket 创建: {bucket}")


def upload_file(
    object_name: str,
    data: bytes,
    length: int,
    bucket: str | None = None,
    content_type: str = "application/octet-stream",
) -> str:
    """
    上传文件到 MinIO.

    Returns:
        存储的对象名 (object_name)
    """
    client = get_minio_client()
    bucket = bucket or settings.minio_bucket
    ensure_bucket(bucket)

    client.put_object(
        bucket,
        object_name,
        data,
        length,
        content_type=content_type,
    )
    logger.info(f"☁️ 文件上传成功 | bucket={bucket} | object={object_name}")
    return object_name


def get_presigned_url(
    object_name: str,
    bucket: str | None = None,
    expires: int = 3600,
) -> str:
    """获取预签名下载 URL."""
    client = get_minio_client()
    bucket = bucket or settings.minio_bucket
    return client.presigned_get_object(bucket, object_name, expires)


def init_minio() -> None:
    """应用启动时初始化 MinIO bucket."""
    try:
        ensure_bucket()
        logger.info(f"☁️ MinIO 就绪 | bucket: {settings.minio_bucket}")
    except Exception as e:
        logger.error(f"❌ MinIO 初始化失败: {e}")
