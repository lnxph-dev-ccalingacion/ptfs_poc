/**
 * Backend API client for OCR review flow.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000') + '/api';

/** Build same-origin PDF URL for a document (avoids CORS). */
export function documentPdfUrl(docId: string): string {
  const base = API_BASE.replace(/\/api\/?$/, '');
  return `${base}/api/document/${encodeURIComponent(docId)}/pdf`;
}

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ExtractedField {
  id: string;
  key: string;
  value: string;
  pageIndex: number;
  bbox: BBox;
  rule?: string;
}

export interface FileMetadata {
  documentType: string;
  title: string;
  source: string;
  date: string;
}

export interface UploadResponse {
  doc_id: string;
  pdf_url: string;
  fields: ExtractedField[];
}

export interface DocumentResponse {
  doc_id: string;
  pdf_url: string;
  metadata: FileMetadata;
  fields: ExtractedField[];
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: form,
  });
  return handleResponse<UploadResponse>(res);
}

export async function getDocument(docId: string): Promise<DocumentResponse> {
  const res = await fetch(`${API_BASE}/document/${encodeURIComponent(docId)}`);
  return handleResponse<DocumentResponse>(res);
}

export async function saveMetadata(docId: string, metadata: FileMetadata): Promise<void> {
  const res = await fetch(`${API_BASE}/document/${encodeURIComponent(docId)}/metadata`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(metadata),
  });
  await handleResponse<{ ok: boolean }>(res);
}

export async function submitReview(
  docId: string,
  metadata: FileMetadata,
  fields: ExtractedField[]
): Promise<void> {
  const res = await fetch(`${API_BASE}/document/${encodeURIComponent(docId)}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ metadata, fields }),
  });
  await handleResponse<{ ok: boolean }>(res);
}

export async function applyReview(applyTo: 'existing' | 'succeeding'): Promise<{ ok: boolean; message?: string }> {
  const res = await fetch(`${API_BASE}/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ apply_to: applyTo }),
  });
  return handleResponse<{ ok: boolean; message?: string }>(res);
}
