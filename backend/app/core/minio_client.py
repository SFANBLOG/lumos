"""
MinIO 对象存储客户端.

提供文件上传、预签名 URL 等功能。
"""

from __future__ import annotations

from functools import lru_cache

from loguru import logger
from minio import Minio
from urllib3 import PoolManager
from urllib3.util import Timeout

from app.core.config import get_settings

settings = get_settings()


class StorageUnavailableError(RuntimeError):
    """对象存储暂不可用，调用方应返回可重试的 503。"""


@lru_cache
def get_minio_client() -> Minio:
    """获取 MinIO 客户端单例."""
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
        http_client=PoolManager(
            timeout=Timeout(
                connect=settings.dependency_connect_timeout_seconds,
                read=settings.dependency_read_timeout_seconds,
            ),
            retries=False,
        ),
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
    try:
        client = get_minio_client()
        bucket = bucket or settings.minio_bucket
        ensure_bucket(bucket)

        # minio SDK put_object 需要可读流, 兼容直接传 bytes 的调用方
        if isinstance(data, bytes):
            import io
            data = io.BytesIO(data)

        client.put_object(bucket, object_name, data, length, content_type=content_type)
    except Exception as exc:
        logger.warning("对象存储不可用，上传请求被拒绝: {}", type(exc).__name__)
        raise StorageUnavailableError("对象存储暂不可用，请稍后重试") from exc
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
    """声明对象存储为按需初始化，避免依赖未启动拖慢 API 可用性。"""
    logger.info(f"☁️ MinIO 将在首次文件上传时连接 | bucket: {settings.minio_bucket}")
