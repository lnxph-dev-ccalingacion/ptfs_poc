"""
API schemas matching frontend types.
"""
from typing import Any
from pydantic import BaseModel


class BBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class ExtractedField(BaseModel):
    id: str
    key: str
    value: str
    pageIndex: int
    # For backwards compatibility we support either a single bbox or
    # multiple boxes. Review payloads should prefer `bboxes`.
    bbox: BBox | None = None
    bboxes: list[BBox] | None = None
    rule: str | None = None


class FileMetadata(BaseModel):
    documentType: str = ""
    title: str = ""
    source: str = ""
    date: str = ""


class ReviewPayload(BaseModel):
    metadata: FileMetadata
    fields: list[ExtractedField]


class ApplyRequest(BaseModel):
    apply_to: str  # "existing" | "succeeding"
