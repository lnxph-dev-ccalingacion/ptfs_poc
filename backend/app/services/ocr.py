"""
Open-source OCR: extract every word and its bounding box using PyMuPDF.
Replaces AWS Textract for demo. We do **no** semantic labeling here; every
token is returned and the human review step is responsible for assigning
keys/meaning.
"""
from typing import Any
import logging
import random

import fitz  # PyMuPDF

logger = logging.getLogger("app.ocr")


def extract_words_by_page(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """
    Extract all words from each page with their bounding boxes.

    Returns a list of pages; each page has:
      - page_index
      - width, height
      - words: list of {text, x0, y0, x1, y1}
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[dict[str, Any]] = []
    for i, page in enumerate(doc):
        width = page.rect.width or 1
        height = page.rect.height or 1
        words_raw = page.get_text("words")  # [x0, y0, x1, y1, text, block_no, line_no, word_no]
        words = []
        for x0, y0, x1, y1, text, *_ in words_raw:
            if not str(text).strip():
                continue
            words.append(
                {
                    "text": str(text),
                    "x0": float(x0),
                    "y0": float(y0),
                    "x1": float(x1),
                    "y1": float(y1),
                }
            )
        pages.append({"page_index": i, "width": float(width), "height": float(height), "words": words})
    doc.close()
    return pages


def extract_key_value_fields(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """
    Extract *all* words on all pages as primitive fields for human review.

    Each returned field has:
      - id: string
      - key: always "Text" (or could be empty)
      - value: the word text
      - pageIndex: 0-based page index
      - bbox: normalized 0-1 bbox (x, y, width, height)
    """
    logger.info("OCR: opening PDF with PyMuPDF (fitz), size=%d bytes", len(pdf_bytes))
    pages = extract_words_by_page(pdf_bytes)
    total_words = sum(len(p.get("words") or []) for p in pages)
    logger.info("OCR: extracted %d pages, %d total words", len(pages), total_words)
    fields: list[dict[str, Any]] = []
    field_id = 1
    for page in pages:
        width = page["width"] or 1.0
        height = page["height"] or 1.0
        for w in page["words"]:
            x0 = w["x0"]
            y0 = w["y0"]
            x1 = w["x1"]
            y1 = w["y1"]
            fields.append(
                {
                    "id": str(field_id),
                    "key": "Text",
                    "value": w["text"],
                    "pageIndex": page["page_index"],
                    # PyMuPDF does not expose per-word confidence. For this POC,
                    # assign a random confidence in [0.5, 1.0] so the UI can
                    # demonstrate filtering and display. Replace this with a
                    # real score when integrating a proper OCR engine.
                    "confidence": round(random.uniform(0.5, 1.0), 2),
                    "bbox": {
                        "x": max(0.0, min(1.0, x0 / width)),
                        "y": max(0.0, min(1.0, y0 / height)),
                        "width": max(0.0, min(1.0, (x1 - x0) / width)),
                        "height": max(0.0, min(1.0, (y1 - y0) / height)),
                    },
                }
            )
            field_id += 1
    logger.info("OCR: returning %d fields (key=Text per word)", len(fields))
    return fields
