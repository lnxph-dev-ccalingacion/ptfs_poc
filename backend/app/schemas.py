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


# When applying feedback: which part of the correction to apply on new docs
# semantic = key/label only: on new docs use MATCHED OCR text + OCR bbox (propagate the key, not the exact text)
# spelling = user fixed text: on new docs use FEEDBACK value + matched OCR bbox (propagate corrected text)
# bbox = user moved/resized box: use matched OCR text + FEEDBACK bbox
# spelling_and_bbox = both value and bbox from feedback
CORRECTION_TYPES = {"semantic", "spelling", "bbox", "spelling_and_bbox"}


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
    # Optional: how to apply this field when matching on new uploads (can be auto-set in /review).
    # semantic = use matched OCR text + OCR bbox | spelling = use this value + OCR bbox
    # bbox = use OCR text + this bbox | spelling_and_bbox = use this value + this bbox
    correctionType: str | None = None


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
