"""
Solr client for semantic feedback, layout feedback, and metadata-value collections.
"""
from typing import Any

import pysolr
from app.config import settings

_solr_clients: dict[str, pysolr.Solr] = {}


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


def add_semantic_feedback(doc_id: str, fields: list[dict], embedding: list[float], run_id: str):
    """Store semantic feedback (embedding as string for default schema)."""
    import json
    c = semantic_collection()
    c.add([{
        "id": doc_id,
        "doc_id_s": doc_id,
        "run_id_s": run_id,
        "embedding_s": ",".join(str(x) for x in embedding),
        "fields_json_s": json.dumps(fields),
    }])


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


def get_metadata(doc_id: str) -> dict | None:
    """Get stored metadata for a doc."""
    import json
    try:
        # Simple term query; avoid special chars in doc_id
        q = f'doc_id_s:"{doc_id.replace(chr(34), "")}"'
        r = metadata_collection().search(q, rows=1)
        if r.docs:
            d = r.docs[0]
            return {
                "metadata": json.loads(d.get("metadata_s") or "{}"),
                "fields": json.loads(d.get("fields_json_s") or "[]"),
            }
    except Exception:
        pass
    return None
