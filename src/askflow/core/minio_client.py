from __future__ import annotations

import io

from minio import Minio
from minio.error import S3Error

from askflow.config import settings

minio_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


def ensure_bucket() -> None:
    if not minio_client.bucket_exists(settings.minio_bucket):
        minio_client.make_bucket(settings.minio_bucket)


def put_document_bytes(
    object_name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    ensure_bucket()
    minio_client.put_object(
        settings.minio_bucket,
        object_name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def get_document_bytes(object_name: str) -> bytes:
    response = minio_client.get_object(settings.minio_bucket, object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_document_bytes(object_name: str) -> None:
    try:
        minio_client.remove_object(settings.minio_bucket, object_name)
    except S3Error as error:
        if error.code != "NoSuchKey":
            raise
