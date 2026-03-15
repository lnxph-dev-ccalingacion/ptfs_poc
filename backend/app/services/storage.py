"""
Object storage (MinIO/S3) client for storing PDFs and artifacts.
"""
import io
import uuid
from datetime import timedelta
from minio import Minio
from minio.error import S3Error
from app.config import settings

_client: Minio | None = None


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def ensure_bucket():
    try:
        if not get_minio().bucket_exists(settings.minio_bucket):
            get_minio().make_bucket(settings.minio_bucket)
    except Exception:
        pass


def upload_pdf(content: bytes, filename: str) -> str:
    """Upload PDF to object storage. Returns object key (doc_id)."""
    ensure_bucket()
    key = f"uploads/{uuid.uuid4().hex}_{filename}"
    get_minio().put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(content),
        len(content),
        content_type="application/pdf",
    )
    return key


def get_pdf_url(key: str, expiry_seconds: int = 3600) -> str:
    """Get presigned URL to download the PDF."""
    return get_minio().presigned_get_object(
        settings.minio_bucket,
        key,
        expires=timedelta(seconds=expiry_seconds),
    )


def get_pdf_bytes(key: str) -> bytes:
    """Download PDF as bytes."""
    resp = get_minio().get_object(settings.minio_bucket, key)
    try:
        return resp.read()
    finally:
        resp.close()


def delete_all_pdfs():
    """Delete all objects in the documents bucket."""
    client = get_minio()
    try:
        objects = client.list_objects(settings.minio_bucket, recursive=True)
    except Exception:
        return
    for obj in objects:
        try:
            client.remove_object(settings.minio_bucket, obj.object_name)
        except Exception:
            continue


def list_all_pdfs() -> list[dict]:
    """List all objects in the documents bucket."""
    client = get_minio()
    ensure_bucket()
    try:
        objects = client.list_objects(settings.minio_bucket, recursive=True)
    except Exception:
        return []
    results: list[dict] = []
    for obj in objects:
        results.append(
            {
                "key": obj.object_name,
                "size": getattr(obj, "size", None),
                "last_modified": getattr(obj, "last_modified", None),
            }
        )
    return results
