# PTFS KV POC — OCR Review + Human Feedback

Only **MinIO** and **Solr** are containerized. Run the **backend** and **frontend** locally so you can debug and change code.

## 1. Start MinIO and Solr (Docker)

From the project root:

```bash
docker compose up -d
```

This starts:

- **MinIO** — http://localhost:9000 (API), http://localhost:9001 (console; minioadmin / minioadmin)
- **Solr** — http://localhost:8983

Give Solr a minute to become ready on first start.

## 2. Run the backend (terminal)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API uses `localhost:9000` for MinIO and `http://localhost:8983/solr` for Solr by default (see `backend/app/config.py`). Override with a `.env` in `backend/` if needed.

## 3. Run the frontend (another terminal)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The dev server proxies `/api` to `http://localhost:8000`.

---

**Summary:** `docker compose up -d` for MinIO + Solr only; run backend and frontend in two terminals with `uvicorn` and `npm run dev`.
