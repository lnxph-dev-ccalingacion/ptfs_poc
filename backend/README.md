# OCR Review Backend

FastAPI backend for document upload, OCR (PyMuPDF), object storage (MinIO), embeddings (sentence-transformers), and feedback storage (Solr).

## Run with Docker

From repo root:

```bash
docker compose up --build
```

- API: http://localhost:8000
- MinIO console: http://localhost:9001 (minioadmin / minioadmin)
- Solr: http://localhost:8983

## Run locally (no Docker)

1. Start MinIO and Solr (e.g. via Docker).
2. Create `.env` with `MINIO_ENDPOINT=localhost:9000`, `SOLR_URL=http://localhost:8983/solr`.
3. `pip install -r requirements.txt && uvicorn main:app --reload --port 8000`

## API

- `POST /api/upload` — upload PDF, returns `doc_id`, `pdf_url`, `fields`
- `GET /api/document/{doc_id}` — get document info
- `GET /api/document/{doc_id}/pdf` — stream PDF
- `POST /api/document/{doc_id}/metadata` — save metadata
- `POST /api/document/{doc_id}/review` — submit human review (writes to Solr)
- `POST /api/apply` — apply to existing or succeeding runs
