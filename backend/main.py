from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes.documents import router as documents_router
from app.services.storage import ensure_bucket
from app.services.solr_init import ensure_cores


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_bucket()
    ensure_cores()
    yield
    pass


app = FastAPI(
    title="OCR Review API",
    description="Document processing, human review, and feedback layer",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(documents_router)


@app.get("/health")
def health():
    return {"status": "ok"}
