"""
Document processing and human review API.
"""
import math
import uuid
import logging
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse, Response

from app.config import settings
from app.schemas import ExtractedField, FileMetadata, ReviewPayload, ApplyRequest
from app.services.storage import upload_pdf, get_pdf_url, get_pdf_bytes, delete_all_pdfs, list_all_pdfs
from app.services.ocr import extract_key_value_fields
from app.services.embeddings import embed_fields, embed_text
from app.services.solr_client import (
    add_semantic_feedback,
    add_metadata_values,
    get_metadata,
    get_document_types_from_semantic_feedback,
    get_templates_from_semantic_feedback,
    list_documents,
    delete_all_documents,
    get_templates_for_document_type,
    index_ocr_spans,
    list_doc_ids_for_document_type,
    list_semantic_feedback_docs,
    search_ocr_spans,
)
from app.services.solr_init import ensure_ocr_spans

router = APIRouter(prefix=settings.api_prefix, tags=["documents"])

logger = logging.getLogger("app.upload")

# In-memory run state for demo (doc_id -> { metadata, fields })
_run_state: dict[str, dict] = {}
_run_id = "run_" + uuid.uuid4().hex[:8]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# Thresholds for layout-aware matching: long example = match whole block of text, not one word
_LONG_EXAMPLE_MIN_CHARS = 40
_LONG_EXAMPLE_MIN_WORDS = 4
_BLOCK_SIMILARITY_THRESHOLD = 0.25


def _group_ocr_into_blocks(
    field_dicts: list[dict], y_tolerance: float = 0.015, line_gap_tolerance: float = 0.035
) -> list[dict]:
    """Group OCR word fields into lines (same y), then into blocks (consecutive lines).
    Returns list of blocks: { fields, text, pageIndex, bbox }."""
    if not field_dicts:
        return []
    # Sort by page, then y, then x
    def sort_key(d: dict) -> tuple:
        page = d.get("pageIndex", 0)
        bbox = d.get("bbox") or {}
        y = bbox.get("y", 0.0)
        x = bbox.get("x", 0.0)
        return (page, y, x)

    sorted_fields = sorted(
        [d for d in field_dicts if (d.get("value") or "").strip()],
        key=sort_key,
    )
    if not sorted_fields:
        return []

    blocks: list[dict] = []
    current_line: list[dict] = []
    current_page = None
    last_y = None
    current_block_lines: list[list[dict]] = []

    def make_block(lines: list[list[dict]]) -> dict | None:
        if not lines:
            return None
        all_fs = [f for line in lines for f in line]
        if not all_fs:
            return None
        texts = [str(f.get("value") or "").strip() for f in all_fs]
        text = " ".join(texts)
        page = all_fs[0].get("pageIndex", 0)
        bboxes = [f.get("bbox") or {} for f in all_fs]
        xs = [b.get("x", 0) for b in bboxes]
        ys = [b.get("y", 0) for b in bboxes]
        ws = [b.get("width", 0) for b in bboxes]
        hs = [b.get("height", 0) for b in bboxes]
        x_min = min(xs)
        y_min = min(ys)
        x_max = max(x + w for x, w in zip(xs, ws))
        y_max = max(y + h for y, h in zip(ys, hs))
        return {
            "fields": all_fs,
            "text": text,
            "pageIndex": page,
            "bbox": {"x": x_min, "y": y_min, "width": x_max - x_min, "height": y_max - y_min},
        }

    for d in sorted_fields:
        page = d.get("pageIndex", 0)
        bbox = d.get("bbox") or {}
        y = bbox.get("y", 0.0)
        if current_page is not None and page != current_page:
            if current_block_lines:
                blk = make_block(current_block_lines)
                if blk:
                    blocks.append(blk)
            current_line = []
            current_block_lines = []
        current_page = page
        if last_y is not None and abs(y - last_y) > y_tolerance:
            if current_line:
                current_block_lines.append(current_line)
            gap = (y - last_y) if last_y is not None else 0
            if current_block_lines and gap > line_gap_tolerance:
                blk = make_block(current_block_lines)
                if blk:
                    blocks.append(blk)
                current_block_lines = []
            current_line = [d]
        else:
            current_line.append(d)
        last_y = y
    if current_line:
        current_block_lines.append(current_line)
    if current_block_lines:
        blk = make_block(current_block_lines)
        if blk:
            blocks.append(blk)
    return blocks


def _apply_templates_to_ocr_fields(
    ocr_fields: list, document_type: str
) -> tuple[list, bool, str]:
    """Apply saved templates to OCR fields using embedding similarity.
    Prefer semantic_feedback (document_type_s); fallback to metadata_value.
    Returns (merged_fields, feedback_applied, feedback_reason)."""
    # Prefer semantic_feedback so docs with document_type_s=letter are found
    templates = get_templates_from_semantic_feedback(document_type)
    template_source = "semantic_feedback"
    if not templates:
        logger.info(
            "_apply_templates_to_ocr_fields: no templates from semantic_feedback for document_type=%s, trying metadata_value",
            document_type,
        )
        templates = get_templates_for_document_type(document_type)
        template_source = "metadata_value"
    if not templates:
        logger.info("_apply_templates_to_ocr_fields: no templates from %s for document_type=%s", template_source, document_type)
        return ocr_fields, False, "no matching document type"
    logger.info(
        "_apply_templates_to_ocr_fields: using %s, document_type=%s, template keys=%s",
        template_source,
        document_type,
        [t["key"] for t in templates],
    )
    # Normalize to dicts
    field_dicts = [
        f.model_dump() if isinstance(f, ExtractedField) else dict(f)
        for f in ocr_fields
    ]
    existing_keys = {str(d.get("key") or "").strip().lower() for d in field_dicts}
    tmpl_vectors = {
        t["key"]: embed_text(f"{t['key']} {t.get('rule') or ''} {t.get('example_value') or ''}")
        for t in templates
    }
    # Layout-aware: group OCR into lines/blocks for long template values
    blocks = _group_ocr_into_blocks(field_dicts)
    logger.info("_apply_templates_to_ocr_fields: grouped OCR into %d blocks (layout)", len(blocks))
    used_ids: set[str] = set()
    new_fields: list[dict] = []
    for tmpl in templates:
        key = tmpl["key"]
        if key.lower() in existing_keys:
            logger.debug("_apply_templates_to_ocr_fields: skip template key=%s (already in OCR)", key)
            continue
        example = (tmpl.get("example_value") or "").strip()
        example_words = len(example.split())
        is_long_example = (
            len(example) >= _LONG_EXAMPLE_MIN_CHARS
            or example_words >= _LONG_EXAMPLE_MIN_WORDS
        )
        tmpl_vec = tmpl_vectors.get(key) or []
        if is_long_example and blocks:
            # Match whole block (paragraph) by embedding similarity — layout-aware
            best_block = None
            best_score = -1.0
            for blk in blocks:
                blk_ids = {f.get("id") for f in blk["fields"] if f.get("id")}
                if used_ids & blk_ids:
                    continue
                if not (blk.get("text") or "").strip():
                    continue
                blk_vec = embed_text(blk["text"])
                sim = _cosine(tmpl_vec, blk_vec)
                if sim > best_score:
                    best_score = sim
                    best_block = blk
            if best_block and best_score >= _BLOCK_SIMILARITY_THRESHOLD:
                for f in best_block["fields"]:
                    used_ids.add(f.get("id") or "")
                ct = (tmpl.get("correctionType") or "semantic").strip().lower()
                if ct == "spelling" or ct == "spelling_and_bbox":
                    out_value = tmpl.get("value") or tmpl.get("example_value") or best_block["text"]
                else:
                    out_value = best_block["text"]
                if ct == "bbox" or ct == "spelling_and_bbox":
                    out_bbox = tmpl.get("bbox")
                else:
                    out_bbox = best_block.get("bbox")
                new_fields.append({
                    "id": f"auto-{key}",
                    "key": key,
                    "value": out_value,
                    "pageIndex": best_block["pageIndex"],
                    "bbox": out_bbox,
                    "rule": tmpl.get("rule") or "",
                })
                logger.info(
                    "_apply_templates_to_ocr_fields: applied template key=%s (block) correctionType=%s best_score=%.4f",
                    key,
                    ct,
                    best_score,
                )
            else:
                logger.info(
                    "_apply_templates_to_ocr_fields: no block match for template key=%s best_score=%.4f (threshold %.2f)",
                    key,
                    best_score if best_block else -1.0,
                    _BLOCK_SIMILARITY_THRESHOLD,
                )
        else:
            # Short example: match single word (or phrase) by embedding
            best = None
            best_score = -1.0
            for d in field_dicts:
                fid = d.get("id") or ""
                if fid in used_ids:
                    continue
                text = (d.get("value") or "").strip()
                if not text:
                    continue
                cand_vec = embed_text(text)
                sim = _cosine(tmpl_vec, cand_vec)
                if sim > best_score:
                    best_score = sim
                    best = d
            if best and best_score > 0.3:
                used_ids.add(best.get("id") or "")
                ct = (tmpl.get("correctionType") or "semantic").strip().lower()
                if ct == "spelling" or ct == "spelling_and_bbox":
                    out_value = tmpl.get("value") or tmpl.get("example_value") or best.get("value") or ""
                else:
                    out_value = best.get("value") or ""
                if ct == "bbox" or ct == "spelling_and_bbox":
                    out_bbox = tmpl.get("bbox")
                else:
                    out_bbox = best.get("bbox")
                new_fields.append({
                    "id": f"auto-{key}",
                    "key": key,
                    "value": out_value,
                    "pageIndex": best.get("pageIndex", 0),
                    "bbox": out_bbox,
                    "rule": tmpl.get("rule") or "",
                })
                logger.info(
                    "_apply_templates_to_ocr_fields: applied template key=%s (word) correctionType=%s best_score=%.4f",
                    key,
                    ct,
                    best_score,
                )
            else:
                logger.info(
                    "_apply_templates_to_ocr_fields: no match for template key=%s best_score=%.4f (threshold 0.3)",
                    key,
                    best_score if best else -1.0,
                )
    # Keep all original OCR fields, add template-derived (no duplicate keys)
    out = list(field_dicts)
    for nf in new_fields:
        out.append(nf)
    if new_fields:
        return out, True, f"templates applied from {template_source} for document_type={document_type!r} ({len(new_fields)} fields)"
    return out, False, "templates found but no embedding match above threshold"


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str | None = Query(None, description="If set, apply saved templates for this type to fill corrected keys"),
):
    """Upload a PDF. Stored in object storage, OCR run, returns doc_id and extracted fields."""
    logger.info("upload_document: received file name=%s content_type=%s", file.filename, file.content_type)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        logger.warning("upload_document: rejected non-PDF filename=%s", file.filename)
        raise HTTPException(400, "Only PDF files are allowed")
    try:
        content = await file.read()
        logger.info("upload_document: read %d bytes", len(content))
        key = upload_pdf(content, file.filename or "document.pdf")
        logger.info("upload_document: uploaded to MinIO with key=%s", key)
        logger.info("upload_document: starting OCR (PyMuPDF)")
        fields = extract_key_value_fields(content)
        logger.info("upload_document: OCR done, extracted %d fields", len(fields))
        doc_id = key
        feedback_applied = False
        feedback_reason = "document_type not provided"
        # If document_type provided, check semantic_feedback and apply templates (semantic_feedback first, then metadata_value)
        if document_type and document_type.strip():
            doc_type = document_type.strip().lower()
            logger.info(
                "upload_document: document_type param=%r normalized=%r",
                document_type,
                doc_type,
            )
            # Check semantic_feedback collection: how many docs total and how many match this document_type
            try:
                semantic_docs = list_semantic_feedback_docs(limit=50)
                matching_by_type = [d for d in semantic_docs if (d.get("document_type_s") or "").strip().lower() == doc_type]
                logger.info(
                    "upload_document: semantic_feedback total docs=%d, with document_type_s=%s: %d docs (doc_ids: %s)",
                    len(semantic_docs),
                    doc_type,
                    len(matching_by_type),
                    [d.get("doc_id_s") or d.get("id") for d in matching_by_type[:5]],
                )
                if semantic_docs:
                    field_dicts = [
                        f.model_dump() if isinstance(f, ExtractedField) else dict(f)
                        for f in fields
                    ]
                    current_embedding = embed_fields(field_dicts)
                    similarities = []
                    for d in semantic_docs:
                        stored_id = d.get("doc_id_s") or d.get("id") or ""
                        emb_s = d.get("embedding_s") or ""
                        try:
                            stored_emb = [float(x.strip()) for x in emb_s.split(",") if x.strip()]
                        except (ValueError, TypeError):
                            continue
                        sim = _cosine(current_embedding, stored_emb)
                        similarities.append((stored_id, round(sim, 4)))
                    similarities.sort(key=lambda x: -x[1])
                    if similarities:
                        logger.info(
                            "upload_document: semantic_feedback embedding similarities with current upload: %s",
                            ", ".join(f"doc_id={sid!r} score={sco}" for sid, sco in similarities[:5]),
                        )
                    else:
                        logger.info("upload_document: semantic_feedback docs have no parseable embedding_s, skipping similarity log")
            except Exception:
                logger.exception("upload_document: failed to check semantic_feedback collection")
            # Apply templates: semantic_feedback first (by document_type_s), then metadata_value fallback
            logger.info("upload_document: applying corrections (templates) for document_type=%s", doc_type)
            try:
                fields, feedback_applied, feedback_reason = _apply_templates_to_ocr_fields(fields, doc_type)
                logger.info(
                    "upload_document: document_type=%s feedback_applied=%s feedback_reason=%s",
                    doc_type,
                    feedback_applied,
                    feedback_reason,
                )
            except Exception:
                logger.exception("upload_document: template application failed for document_type=%s, using raw OCR", doc_type)
                feedback_applied = False
                feedback_reason = "template application failed"
        _run_state[doc_id] = {"metadata": {}, "fields": fields, "key": key}
        # Store an initial metadata-only record in Solr so we can list this
        # document in the homepage dropdown without hitting term-length limits.
        fields_for_solr = [f.model_dump() if isinstance(f, ExtractedField) else f for f in fields]
        try:
            add_metadata_values(doc_id, {}, [], _run_id)
            logger.info("upload_document: stored document stub for doc_id=%s in metadata_value", doc_id)
        except Exception:
            # Best-effort; don't fail upload if Solr is unavailable
            logger.exception("upload_document: failed to store OCR result in Solr for doc_id=%s", doc_id)
        # Best-effort index of OCR spans for BM25/fuzzy search
        try:
            index_ocr_spans(doc_id, fields_for_solr)
            logger.info("upload_document: indexed OCR spans for doc_id=%s", doc_id)
        except Exception:
            logger.exception("upload_document: failed to index OCR spans for doc_id=%s", doc_id)
        # Return proxy URL so frontend avoids MinIO CORS
        base = settings.api_prefix or "/api"
        pdf_url = f"{base}/document-pdf/{doc_id}"
        logger.info("upload_document: completed successfully for doc_id=%s", doc_id)
        return {
            "doc_id": doc_id,
            "pdf_url": pdf_url,
            "fields": fields,
            "feedback_applied": feedback_applied,
            "feedback_reason": feedback_reason,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("upload_document: unexpected error: %s", e)
        raise HTTPException(500, "Upload/OCR failed")


@router.get("/documents")
async def list_docs():
    """List recently processed documents with their stored OCR/metadata."""
    return list_documents(limit=20)


@router.get("/semantic-feedback/document-types")
async def list_semantic_feedback_document_types(limit: int = Query(500, ge=1, le=2000)):
    """Return document_type values that have at least one doc in the Solr semantic_feedback collection.
    Types are resolved via metadata_value (same doc_id)."""
    types = get_document_types_from_semantic_feedback(limit=limit)
    return {"document_types": types}


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
        # Use stored reviewed fields from Solr when present; otherwise re-run OCR (e.g. stub doc).
        if stored.get("fields"):
            fields = stored["fields"]
        else:
            content = get_pdf_bytes(key)
            fields = extract_key_value_fields(content)
        _run_state[doc_id] = {
            "metadata": stored["metadata"],
            "fields": fields,
            "key": key,
        }
        return {
            "doc_id": doc_id,
            "pdf_url": pdf_url,
            "metadata": stored["metadata"],
            "fields": fields,
        }

    raise HTTPException(404, "Document not found")


def _normalize_document_type(meta_dict: dict) -> None:
    """Normalize documentType to lowercase so saves are case-insensitive."""
    dt = meta_dict.get("documentType") or ""
    meta_dict["documentType"] = str(dt).strip().lower()


def _bbox_changed(a: dict | None, b: dict | None, tolerance: float = 1e-5) -> bool:
    """True if bboxes differ (or one is missing)."""
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    for k in ("x", "y", "width", "height"):
        va = a.get(k, 0) or 0
        vb = b.get(k, 0) or 0
        if abs(float(va) - float(vb)) > tolerance:
            return True
    return False


def _auto_set_correction_type(
    submitted_fields: list[dict], original_fields: list[dict]
) -> list[dict]:
    """Set correctionType on each field from comparison with original (before edit) state.
    - bbox changed and value changed -> spelling_and_bbox
    - bbox changed only -> bbox
    - value changed only -> spelling (propagate corrected text)
    - key changed only (e.g. Text -> Content) or new field -> semantic (propagate key, use new doc OCR text)
    """
    orig_by_id: dict[str, dict] = {}
    for o in original_fields:
        d = o if isinstance(o, dict) else (o.model_dump() if hasattr(o, "model_dump") else {})
        oid = d.get("id")
        if oid:
            orig_by_id[oid] = d
    result = []
    for f in submitted_fields:
        fd = dict(f) if isinstance(f, dict) else f.model_dump()
        o = orig_by_id.get(fd.get("id") or "")
        val_new = (fd.get("value") or "").strip()
        val_orig = (o.get("value") or "").strip() if o else ""
        key_new = (fd.get("key") or "").strip()
        key_orig = (o.get("key") or "").strip() if o else ""
        bbox_changed = _bbox_changed(fd.get("bbox"), o.get("bbox")) if o else False
        value_changed = val_new != val_orig
        key_changed = key_new != key_orig
        if bbox_changed and value_changed:
            fd["correctionType"] = "spelling_and_bbox"
        elif bbox_changed:
            fd["correctionType"] = "bbox"
        elif value_changed:
            fd["correctionType"] = "spelling"
        elif key_changed or not o:
            fd["correctionType"] = "semantic"
        else:
            fd["correctionType"] = "semantic"
        result.append(fd)
    return result


@router.post("/document/{doc_id:path}/metadata")
async def save_metadata(doc_id: str, metadata: FileMetadata):
    """Save metadata for the document (assign step)."""
    if doc_id not in _run_state:
        raise HTTPException(404, "Document not found")
    meta_dict = metadata.model_dump()
    _normalize_document_type(meta_dict)
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
    """Submit human review: corrected metadata and fields. Stored in Solr feedback + metadata collections.
    correctionType is auto-set per field: bbox changed -> bbox; value changed -> spelling; key-only -> semantic."""
    if doc_id not in _run_state:
        raise HTTPException(404, "Document not found")
    original_fields = _run_state[doc_id].get("fields") or []
    submitted = [f.model_dump() for f in payload.fields]
    fields = _auto_set_correction_type(submitted, original_fields)
    logger.info(
        "submit_review: auto-set correctionType for %d fields: %s",
        len(fields),
        [(f.get("key"), f.get("correctionType")) for f in fields if str(f.get("key", "")).lower() != "text"],
    )
    metadata = payload.metadata.model_dump()
    _normalize_document_type(metadata)
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
        add_semantic_feedback(
            doc_id,
            high_level_fields,
            embedding,
            _run_id,
            document_type=metadata.get("documentType", ""),
        )
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


@router.post("/documents/purge")
async def purge_all_documents():
    """Delete all docs: MinIO bucket and Solr metadata_value, semantic_feedback, layout_feedback collections."""
    # Clear in-memory state
    _run_state.clear()
    # Best-effort delete in external systems
    delete_all_documents()  # metadata_value, semantic_feedback, layout_feedback
    delete_all_pdfs()       # MinIO
    return {"ok": True}


@router.get("/minio/objects")
async def list_minio_objects():
    """List all objects currently stored in the MinIO documents bucket."""
    return list_all_pdfs()


@router.get("/inventory")
async def inventory():
    """
    Combined inventory of Solr documents and MinIO objects.

    - solr_documents: documents stored in metadata_value (via list_documents)
    - minio_objects: all objects in the MinIO documents bucket
    """
    return {
        "solr_documents": list_documents(limit=500),
        "minio_objects": list_all_pdfs(),
    }


@router.get("/templates")
async def get_templates(document_type: str):
    """Get common field templates (keys/rules) for a given document type."""
    if not document_type:
        return []
    return get_templates_for_document_type(document_type)


@router.post("/solr/init-ocr-spans")
async def init_ocr_spans():
    """Initialize the ocr_spans core and schema in Solr."""
    ensure_ocr_spans()
    return {"ok": True}


@router.post("/document-types/{document_type}/rerun-existing")
async def rerun_existing_for_type(document_type: str, body: dict | None = None):
    """Re-run field extraction for all docs of a given document type (best-effort POC)."""
    from app.services.embeddings import embed_text
    import math

    limit = int((body or {}).get("limit") or 100)
    templates = get_templates_for_document_type(document_type)
    if not templates:
        return {"ok": True, "updated_count": 0}

    docs = list_doc_ids_for_document_type(document_type, limit=limit)
    updated = 0

    # Precompute template embeddings for vector similarity
    def cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    tmpl_vectors = {
        t["key"]: embed_text(f"{t['key']} {t.get('rule') or ''} {t.get('example_value') or ''}")
        for t in templates
    }

    for d in docs:
        doc_id = d["doc_id"]
        metadata = d["metadata"]

        # Fetch spans for this doc once (broad query)
        spans = search_ocr_spans(doc_id, "*:*", top_k=500)  # '*' query is approximated in helper
        if not spans:
            continue

        # For each template, pick best span using BM25 (via Solr ranking) + embedding rerank
        used_span_ids: set[str] = set()
        new_fields: list[dict] = []

        for tmpl in templates:
            key = tmpl["key"]
            example = (tmpl.get("example_value") or "").strip()
            query_text = example or key

            # BM25: get candidate spans via search_ocr_spans
            candidates = search_ocr_spans(doc_id, query_text, top_k=20) or spans
            if not candidates:
                continue

            best = None
            best_score = -1.0
            tmpl_vec = tmpl_vectors.get(key) or []

            for span in candidates:
                if span["id"] in used_span_ids:
                    continue
                text = span.get("text") or ""
                cand_vec = embed_text(text)
                sim = cosine(tmpl_vec, cand_vec)
                if sim > best_score:
                    best_score = sim
                    best = span

            if best and best_score > 0.3:
                used_span_ids.add(best["id"])
                new_fields.append(
                    {
                        "id": f"auto-{key}",
                        "key": key,
                        "value": best["text"],
                        "pageIndex": best["pageIndex"],
                        "bbox": best["bbox"],
                        "rule": tmpl.get("rule") or "",
                    }
                )

        if not new_fields:
            continue

        # Merge: keep all existing TEXT spans plus new high-level fields
        # For now we don't delete existing TEXT rows in Solr; just append new fields.
        try:
            existing = get_metadata(doc_id) or {"fields": []}
            fields = existing["fields"] + new_fields
            add_metadata_values(doc_id, metadata, fields, _run_id)
            updated += 1
        except Exception:
            continue

    return {"ok": True, "updated_count": updated}


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
