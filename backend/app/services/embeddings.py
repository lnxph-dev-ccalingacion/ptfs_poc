"""
Open-source embeddings (sentence-transformers) for feedback vector search.
No LLM calls; vector search only per architecture.
"""
from typing import Any

_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def embed_text(text: str) -> list[float]:
    """Generate embedding vector for text."""
    if not text or not text.strip():
        return [0.0] * 384  # all-MiniLM-L6-v2 dimension
    model = get_embedder()
    return model.encode(text, convert_to_numpy=True).tolist()


def embed_fields(fields: list[dict[str, Any]]) -> list[float]:
    """Embed a concatenated representation of key-value fields."""
    parts = [f"{f.get('key', '')} {f.get('value', '')}" for f in fields]
    return embed_text(" ".join(parts))
