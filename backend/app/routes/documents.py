"""
Document processing and human review API.
"""
import uuid
import logging
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response

from app.config import settings
from app.schemas import ExtractedField, FileMetadata, ReviewPayload, ApplyRequest
from app.services.storage import upload_pdf, get_pdf_url, get_pdf_bytes
from app.services.ocr import extract_key_value_fields
from app.services.embeddings import embed_fields
from app.services.solr_client import (
    add_semantic_feedback,
    add_metadata_values,
    get_metadata,
    list_documents,
)

router = APIRouter(prefix=settings.api_prefix, tags=["documents"])

logger = logging.getLogger("app.upload")

# In-memory run state for demo (doc_id -> { metadata, fields })
_run_state: dict[str, dict] = {}
_run_id = "run_" + uuid.uuid4().hex[:8]


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF. Stored in object storage, OCR run, returns doc_id and extracted fields."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are allowed")
    content = await file.read()
    key = upload_pdf(content, file.filename or "document.pdf")
    fields = extract_key_value_fields(content)
    doc_id = key
    _run_state[doc_id] = {"metadata": {}, "fields": fields, "key": key}
    # Store an initial metadata-only record in Solr so we can list this
    # document in the homepage dropdown without hitting term-length limits.
    try:
        add_metadata_values(doc_id, {}, [], _run_id)
        logger.info("Stored document stub for doc_id=%s in metadata_value", doc_id)
    except Exception:
        # Best-effort; don't fail upload if Solr is unavailable
        logger.exception("Failed to store OCR result in Solr for doc_id=%s", doc_id)
    # Return proxy URL so frontend avoids MinIO CORS
    base = settings.api_prefix or "/api"
    pdf_url = f"{base}/document-pdf/{doc_id}"
    return {
        "doc_id": doc_id,
        "pdf_url": pdf_url,
        "fields": fields,
    }


@router.get("/documents")
async def list_docs():
    """List recently processed documents with their stored OCR/metadata."""
    return list_documents(limit=20)


@router.get("/document/{doc_id:path}")
async def get_document(doc_id: str):
    """Get document info: PDF URL and current extracted fields (and metadata if saved)."""
    # Prefer in-memory state from this process
    if doc_id in _run_state:
        rec = _run_state[doc_id]
        key = rec.get("key") or doc_id
        base = settings.api_prefix or "/api"
        pdf_url = f"{base}/document-pdf/{doc_id}"
        return {
            "doc_id": doc_id,
            "pdf_url": pdf_url,
            "metadata": rec.get("metadata", {}),
            "fields": rec["fields"],
        }

    # Fallback: fetch from Solr (previous run)
    stored = get_metadata(doc_id)
    if stored:
        key = doc_id  # doc_id is the MinIO key
        base = settings.api_prefix or "/api"
        pdf_url = f"{base}/document-pdf/{doc_id}"
        # Re-run OCR on demand instead of relying on large JSON stored in Solr
        content = get_pdf_bytes(key)
        fields = extract_key_value_fields(content)
        # Cache into in-memory state so subsequent metadata/review updates work
        _run_state[doc_id] = {
            "metadata": stored["metadata"],
            "fields": [f.model_dump() if isinstance(f, ExtractedField) else f for f in fields],
            "key": key,
        }
        return {
            "doc_id": doc_id,
            "pdf_url": pdf_url,
            "metadata": stored["metadata"],
            "fields": fields,
        }

    raise HTTPException(404, "Document not found")


@router.post("/document/{doc_id:path}/metadata")
async def save_metadata(doc_id: str, metadata: FileMetadata):
    """Save metadata for the document (assign step)."""
    if doc_id not in _run_state:
        raise HTTPException(404, "Document not found")
    meta_dict = metadata.model_dump()
    _run_state[doc_id]["metadata"] = meta_dict
    # Persist updated metadata to Solr as well, keeping existing fields
    try:
        fields = _run_state[doc_id].get("fields") or []
        add_metadata_values(doc_id, meta_dict, fields, _run_id)
    except Exception as e:
        # Metadata save should not crash the UI; surface as 502 so caller can react if needed
        raise HTTPException(502, f"Failed to persist metadata: {e}")
    return {"ok": True}


@router.post("/document/{doc_id:path}/review")
async def submit_review(doc_id: str, payload: ReviewPayload):
    """Submit human review: corrected metadata and fields. Stored in Solr feedback + metadata collections."""
    if doc_id not in _run_state:
        raise HTTPException(404, "Document not found")
    fields = [f.model_dump() for f in payload.fields]
    metadata = payload.metadata.model_dump()
    _run_state[doc_id]["metadata"] = metadata
    _run_state[doc_id]["fields"] = fields
    try:
        # For embeddings we can ignore word-level TEXT fields (focus on labeled fields),
        # but in Solr we store the full set of fields (including TEXT) so edits are reflected.
        high_level_fields = [
            f for f in fields
            if str(f.get("key", "")).lower() != "text"
        ]
        embedding = embed_fields(high_level_fields)
        add_semantic_feedback(doc_id, high_level_fields, embedding, _run_id)
        add_metadata_values(doc_id, metadata, fields, _run_id)
    except Exception as e:
        raise HTTPException(502, f"Feedback storage failed: {e}")
    return {"ok": True}


@router.post("/apply")
async def apply_review(body: ApplyRequest):
    """Apply review to existing runs or succeeding runs (demo: acknowledge only)."""
    if body.apply_to == "existing":
        return {"ok": True, "message": "Apply on existing runs requested. In production would re-run previous documents."}
    if body.apply_to == "succeeding":
        return {"ok": True, "message": "Apply on succeeding runs requested. Future documents will use this feedback."}
    raise HTTPException(400, "apply_to must be 'existing' or 'succeeding'")


@router.get("/pdf-url/{doc_id:path}")
async def pdf_proxy_url(doc_id: str):
    """Return redirect URL to presigned PDF (for frontend PDF viewer)."""
    if doc_id not in _run_state:
        raise HTTPException(404, "Document not found")
    key = _run_state[doc_id]["key"]
    url = get_pdf_url(key)
    return RedirectResponse(url=url)


@router.get("/document-pdf/{doc_id:path}")
async def get_pdf_stream(doc_id: str):
    """Stream PDF bytes (same-origin for frontend PDF viewer)."""
    # Use object key from in-memory state when available; otherwise doc_id itself
    key = _run_state.get(doc_id, {}).get("key") or doc_id
    content = get_pdf_bytes(key)
    return Response(content=content, media_type="application/pdf")
