import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MinIO (S3-compatible object storage)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "documents"
    minio_secure: bool = False

    # Solr
    solr_url: str = "http://localhost:8983/solr"
    solr_semantic_collection: str = "semantic_feedback"
    solr_layout_collection: str = "layout_feedback"
    solr_metadata_collection: str = "metadata_value"

    # App
    api_prefix: str = "/api"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
