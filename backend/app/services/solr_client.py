"""
Solr client for semantic feedback, layout feedback, OCR spans, and metadata-value collections.
"""
from typing import Any
import logging

import pysolr
from app.config import settings

_solr_clients: dict[str, pysolr.Solr] = {}
logger = logging.getLogger("app.solr")


def _solr(base: str) -> pysolr.Solr:
    if base not in _solr_clients:
        _solr_clients[base] = pysolr.Solr(f"{settings.solr_url}/{base}")
    return _solr_clients[base]


def semantic_collection() -> pysolr.Solr:
    return _solr(settings.solr_semantic_collection)


def layout_collection() -> pysolr.Solr:
    return _solr(settings.solr_layout_collection)


def metadata_collection() -> pysolr.Solr:
    return _solr(settings.solr_metadata_collection)


def ocr_spans_collection() -> pysolr.Solr:
    """Core that stores one row per OCR span (for BM25/fuzzy search)."""
    return _solr("ocr_spans")


def add_semantic_feedback(
    doc_id: str,
    fields: list[dict],
    embedding: list[float],
    run_id: str,
    document_type: str = "",
) -> None:
    """Store semantic feedback (embedding as string for default schema).
    document_type is stored as document_type_s so we can filter/list by type without joining metadata_value."""
    import json
    c = semantic_collection()
    doc = {
        "id": doc_id,
        "doc_id_s": doc_id,
        "run_id_s": run_id,
        "embedding_s": ",".join(str(x) for x in embedding),
        "fields_json_s": json.dumps(fields),
    }
    if document_type is not None and str(document_type).strip():
        doc["document_type_s"] = str(document_type).strip().lower()
    c.add([doc])


def add_metadata_values(doc_id: str, metadata: dict, fields: list[dict], run_id: str):
    """Store reviewed metadata/key-values."""
    import json
    c = metadata_collection()
    doc = {
        "id": doc_id,
        "doc_id_s": doc_id,
        "run_id_s": run_id,
        "metadata_s": json.dumps(metadata),
    }
    # Store all fields (including TEXT) in chunked string fields to avoid Lucene's 32k term limit.
    if fields:
        full = json.dumps(fields)
        max_len = 30000
        parts = [full[i:i + max_len] for i in range(0, len(full), max_len)]
        if len(parts) == 1:
            doc["fields_json_s"] = parts[0]
        else:
            for idx, part in enumerate(parts):
                # fields_json_s, fields_json_s_1, fields_json_s_2, ...
                suffix = "" if idx == 0 else f"_{idx}"
                doc[f"fields_json_s{suffix}"] = part
    c.add([doc])


def index_ocr_spans(doc_id: str, fields: list[dict]) -> None:
    """Index OCR word/field spans for a single document into ocr_spans."""
    import json

    docs = []
    for i, f in enumerate(fields):
        text = str(f.get("value") or "").strip()
        bbox = f.get("bbox") or {}
        page_index = f.get("pageIndex")
        if not text:
            continue
        if page_index is None:
            continue
        docs.append(
            {
                "id": f"{doc_id}-{i}",
                "doc_id_s": doc_id,
                "page_i": int(page_index),
                "text_t": text,
                "bbox_s": json.dumps(bbox),
            }
        )

    if not docs:
        return

    try:
        ocr_spans_collection().add(docs)
    except Exception:
        # Best-effort only; if ocr_spans is misconfigured, rest of pipeline should still work.
        return


def list_documents(limit: int = 20) -> list[dict]:
    """List recent documents from metadata_value (for homepage dropdown)."""
    import json
    try:
        r = metadata_collection().search("*:*", rows=limit, sort="id desc")
        docs: list[dict] = []
        for d in r.docs:
            doc_id = d.get("doc_id_s") or d.get("id")
            if not doc_id:
                continue
            meta_raw = d.get("metadata_s") or "{}"
            try:
                meta = json.loads(meta_raw)
            except Exception:
                meta = {}
            docs.append(
                {
                    "doc_id": doc_id,
                    "title": meta.get("title") or doc_id,
                    "metadata": meta,
                }
            )
        return docs
    except Exception:
        return []


def search_semantic(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    """Vector similarity search in semantic feedback (demo: simple lookup)."""
    # Solr 9+ supports knn; for older/demo we might just return recent
    try:
        r = semantic_collection().search("*:*", rows=top_k, sort="id desc")
        return [dict(d) for d in r.docs]
    except Exception:
        return []


def list_semantic_feedback_docs(limit: int = 20) -> list[dict]:
    """List recent docs from semantic_feedback with embedding_s and fields_json_s for similarity checks."""
    try:
        r = semantic_collection().search("*:*", rows=limit, sort="id desc")
        return [dict(d) for d in r.docs]
    except Exception:
        return []


def get_document_types_from_semantic_feedback(limit: int = 500) -> list[str]:
    """Return distinct document_type values for docs in semantic_feedback.
    Uses document_type_s when present; falls back to metadata_value (same doc_id) for older docs."""
    try:
        r = semantic_collection().search("*:*", rows=limit, sort="id desc")
        seen_lower: set[str] = set()
        result: list[str] = []
        for d in r.docs:
            dt = d.get("document_type_s")
            if not dt:
                doc_id = d.get("doc_id_s") or d.get("id")
                if not doc_id:
                    continue
                rec = get_metadata(doc_id)
                if not rec:
                    continue
                dt = (rec.get("metadata") or {}).get("documentType") or ""
            dt = str(dt).strip()
            if dt and dt.lower() not in seen_lower:
                seen_lower.add(dt.lower())
                result.append(dt)
        return sorted(result, key=str.lower)
    except Exception:
        return []


def get_metadata(doc_id: str) -> dict | None:
    """Get stored metadata for a doc."""
    import json
    try:
        # Escape double-quotes in doc_id for Solr phrase query
        safe_id = doc_id.replace('"', '')
        q = f'doc_id_s:"{safe_id}"'
        r = metadata_collection().search(q, rows=1)
        if r.docs:
            d = r.docs[0]
            meta_raw = d.get("metadata_s") or "{}"
            try:
                metadata = json.loads(meta_raw)
            except Exception:
                metadata = {}

            # Reassemble chunked fields (fields_json_s, fields_json_s_1, fields_json_s_2, ...)
            def _chunk_order(key: str) -> int:
                if key == "fields_json_s":
                    return 0
                try:
                    return int(key.replace("fields_json_s_", ""))
                except ValueError:
                    return 999

            field_keys = sorted(
                (k for k in d.keys() if k.startswith("fields_json_s") and isinstance(d.get(k), str)),
                key=_chunk_order,
            )
            if field_keys:
                full_json = "".join(d[k] for k in field_keys)
                try:
                    fields = json.loads(full_json)
                except Exception:
                    fields = []
            else:
                fields = []

            return {"metadata": metadata, "fields": fields}
    except Exception:
        pass
    return None


def get_templates_from_semantic_feedback(document_type: str) -> list[dict]:
    """Return templates (key, rule, example_value) from semantic_feedback docs with document_type_s match.
    Use this for applying feedback on upload so docs in semantic_feedback are found by document_type."""
    import json
    doc_type = str(document_type or "").strip().lower()
    if not doc_type:
        return []
    safe = doc_type.replace('"', '')
    q = f'document_type_s:"{safe}"'
    try:
        r = semantic_collection().search(q, rows=50, sort="id desc")
        docs = r.docs
    except Exception as e:
        logger.warning("get_templates_from_semantic_feedback(%s): query failed: %s", document_type, e)
        return []
    templates: dict[str, dict] = {}
    for d in docs:
        raw = d.get("fields_json_s")
        if not raw:
            continue
        try:
            fields = json.loads(raw)
        except Exception:
            continue
        for f in fields:
            key = str(f.get("key") or "").strip()
            if not key or key.lower() == "text":
                continue
            if key in templates:
                continue
            templates[key] = {
                "key": key,
                "rule": f.get("rule") or "",
                "example_value": f.get("value") or "",
                "value": f.get("value") or "",
                "bbox": f.get("bbox"),
                "pageIndex": f.get("pageIndex", 0),
                # How to apply: semantic (OCR text+bbox) | spelling (feedback value, OCR bbox) | bbox (OCR text, feedback bbox) | spelling_and_bbox
                "correctionType": (f.get("correctionType") or "semantic").strip().lower(),
            }
    logger.info(
        "get_templates_from_semantic_feedback(%s): found %d docs, extracted %d template keys: %s",
        document_type,
        len(docs),
        len(templates),
        list(templates.keys()),
    )
    return list(templates.values())


def get_templates_for_document_type(document_type: str) -> list[dict]:
    """Return common field templates (key, rule) for a given documentType from metadata_value."""
    import json
    safe = document_type.replace('"', '')
    # Match the JSON snippet in metadata_s
    pattern = f'\\"documentType\\": \\"{safe}\\"'
    q = f'metadata_s:"{pattern}"'
    try:
        logger.info("get_templates_for_document_type(%s): Solr query=%s", document_type, q)
        r = metadata_collection().search(q, rows=50)
        logger.info(
            "get_templates_for_document_type(%s): numFound=%s",
            document_type,
            getattr(r, "hits", "unknown"),
        )
    except Exception as e:
        logger.exception("get_templates_for_document_type(%s) failed: %s", document_type, e)
        return []

    templates: dict[str, dict] = {}

    def _chunk_order(key: str) -> int:
        if key == "fields_json_s":
            return 0
        try:
            return int(key.replace("fields_json_s_", ""))
        except ValueError:
            return 999

    for d in r.docs:
        # Reassemble fields for each doc
        field_keys = sorted(
            (k for k in d.keys() if k.startswith("fields_json_s") and isinstance(d.get(k), str)),
            key=_chunk_order,
        )
        if not field_keys:
            continue
        try:
            full_json = "".join(d[k] for k in field_keys)
            fields = json.loads(full_json)
        except Exception:
            continue
        for f in fields:
            key = str(f.get("key") or "").strip()
            if not key:
                continue
            if key.lower() == "text":
                continue
            if key in templates:
                continue
            templates[key] = {
                "key": key,
                "rule": f.get("rule") or "",
                "example_value": f.get("value") or "",
                "value": f.get("value") or "",
                "bbox": f.get("bbox"),
                "pageIndex": f.get("pageIndex", 0),
                "correctionType": (f.get("correctionType") or "semantic").strip().lower(),
            }

    logger.info(
        "get_templates_for_document_type(%s): extracted %d template keys: %s",
        document_type,
        len(templates),
        list(templates.keys()),
    )
    return list(templates.values())


def list_doc_ids_for_document_type(document_type: str, limit: int = 100) -> list[dict]:
    """Return doc_ids and metadata for docs whose metadata.documentType matches."""
    import json
    safe = document_type.replace('"', '')
    pattern = f'\\"documentType\\": \\"{safe}\\"'
    q = f'metadata_s:"{pattern}"'
    try:
        logger.info("list_doc_ids_for_document_type(%s): Solr query=%s", document_type, q)
        r = metadata_collection().search(q, rows=limit)
        logger.info(
            "list_doc_ids_for_document_type(%s): numFound=%s",
            document_type,
            getattr(r, "hits", "unknown"),
        )
    except Exception as e:
        logger.exception("list_doc_ids_for_document_type(%s) failed: %s", document_type, e)
        return []
    docs: list[dict] = []
    for d in r.docs:
        doc_id = d.get("doc_id_s") or d.get("id")
        if not doc_id:
            continue
        meta_raw = d.get("metadata_s") or "{}"
        try:
            meta = json.loads(meta_raw)
        except Exception:
            meta = {}
        docs.append({"doc_id": doc_id, "metadata": meta})
    return docs


def search_ocr_spans(doc_id: str, query_text: str, top_k: int = 20) -> list[dict]:
    """BM25/fuzzy search spans for a specific doc_id using text_t; returns hits with text, page, bbox."""
    import json
    if not query_text or not query_text.strip():
        return []
    safe_doc = doc_id.replace('"', '')
    # Basic BM25 query scoped to this doc; could be enhanced with fuzzy ops
    q = f'doc_id_s:"{safe_doc}" AND text_t:({query_text})'
    try:
        r = ocr_spans_collection().search(q, rows=top_k)
    except Exception:
        return []
    spans: list[dict] = []
    for d in r.docs:
        try:
            bbox = json.loads(d.get("bbox_s") or "{}")
        except Exception:
            bbox = {}
        spans.append(
            {
                "id": d.get("id"),
                "text": d.get("text_t") or "",
                "pageIndex": d.get("page_i") or 0,
                "bbox": bbox,
            }
        )
    return spans


def delete_all_documents():
    """Delete all documents from MinIO-relevant Solr cores: metadata_value, semantic_feedback, layout_feedback."""
    try:
        metadata_collection().delete(q="*:*")
    except Exception:
        pass
    try:
        semantic_collection().delete(q="*:*")
    except Exception:
        pass
    try:
        layout_collection().delete(q="*:*")
    except Exception:
        pass
