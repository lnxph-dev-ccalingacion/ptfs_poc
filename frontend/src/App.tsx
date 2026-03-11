import { useState, useEffect } from 'react';
import { PdfViewerWithHighlights } from './PdfViewerWithHighlights';
import { KeyValueList } from './KeyValueList';
import { AddFieldModal, type AddFieldPayload } from './AddFieldModal';
import { DocumentMetadataModal } from './DocumentMetadataModal';
import { UploadStep, ApplyActionsStep } from './steps';
import { SAMPLE_PDF_URL, MOCK_EXTRACTED_FIELDS } from './mockOcrData';
import * as api from './api';
import type { ExtractedField, BBox } from './types';
import './App.css';

type Mode = 'new' | 'existing';

function nextId(fields: ExtractedField[]): string {
  const max = fields.reduce((m, f) => {
    const n = parseInt(f.id, 10);
    return Number.isNaN(n) ? m : Math.max(m, n);
  }, 0);
  return String(max + 1);
}

function App() {
  const [mode, setMode] = useState<Mode>('new');
  const [docId, setDocId] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [fileObjectUrl, setFileObjectUrl] = useState<string | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string>(SAMPLE_PDF_URL);
  const [fields, setFields] = useState<ExtractedField[]>(MOCK_EXTRACTED_FIELDS);
  const [hoveredField, setHoveredField] = useState<ExtractedField | null>(null);
  const [isAddingField, setIsAddingField] = useState(false);
  const [pendingSelection, setPendingSelection] = useState<{ pageIndex: number; bbox: BBox } | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [recentDocs, setRecentDocs] = useState<{ docId: string; label: string }[]>([]);
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [metadata, setMetadata] = useState<api.FileMetadata>({
    documentType: '',
    title: '',
    source: '',
    date: '',
  });
  const [showMetadataModal, setShowMetadataModal] = useState(false);

  // Client-side preview URL so user sees their local file immediately (before backend responds)
  useEffect(() => {
    if (!uploadedFile) {
      if (fileObjectUrl) URL.revokeObjectURL(fileObjectUrl);
      setFileObjectUrl(null);
      return;
    }
    const url = URL.createObjectURL(uploadedFile);
    setFileObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [uploadedFile]);

  // Load recent docs from backend on first mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/documents');
        if (!res.ok) return;
        const docs = await res.json();
        if (Array.isArray(docs)) {
          setRecentDocs(
            docs.map((d: any) => ({
              docId: d.doc_id,
              label: d.title || d.doc_id,
            })),
          );
        }
      } catch {
        // ignore
      }
    })();
  }, []);

  const displayPdfUrl = fileObjectUrl || pdfUrl;

  const resetState = () => {
    setDocId(null);
    setUploadedFile(null);
    setFileObjectUrl(null);
    setPdfUrl(SAMPLE_PDF_URL);
    setFields(MOCK_EXTRACTED_FIELDS);
    setHoveredField(null);
    setPendingSelection(null);
    setApiError(null);
    setCurrentPageIndex(0);
    setMetadata({
      documentType: '',
      title: '',
      source: '',
      date: '',
    });
  };

  const handleFileSelect = (file: File) => {
    setUploadedFile(file);
  };

  // New document type: upload -> backend OCR -> show human review
  const handleUploadAndOcr = async () => {
    setApiError(null);
    if (!uploadedFile) {
      setApiError('Please select a PDF file first.');
      return;
    }
    setLoading(true);
    try {
      const res = await api.uploadDocument(uploadedFile);
      setDocId(res.doc_id);
      setPdfUrl(res.pdf_url);
      setFields((res.fields as ExtractedField[]) || []);
      const label = uploadedFile.name || res.doc_id;
      const next = [
        { docId: res.doc_id, label },
        ...recentDocs.filter((d) => d.docId !== res.doc_id),
      ].slice(0, 10);
      setRecentDocs(next);
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Upload/OCR failed');
    } finally {
      setLoading(false);
    }
  };

  // Existing document type: load a selected docId and open it for review
  const handleLoadExisting = async (docIdToLoad: string) => {
    setApiError(null);
    const trimmed = docIdToLoad.trim();
    if (!trimmed) {
      setApiError('Select a document to load.');
      return;
    }
    setLoading(true);
    try {
      const res = await api.getDocument(trimmed);
      setDocId(res.doc_id);
      setPdfUrl(res.pdf_url);
      setFields((res.fields as ExtractedField[]) || []);
      if (res.metadata) {
        setMetadata(res.metadata);
      } else {
        setMetadata({
          documentType: '',
          title: '',
          source: '',
          date: '',
        });
      }
      setUploadedFile(null);
      setFileObjectUrl(null);
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Load document failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRerunPrevious = async () => {
    setApiError(null);
    if (!docId) {
      setApiError('No document id available. Upload or load a document first.');
      return;
    }
    setLoading(true);
    try {
      await api.submitReview(docId, metadata, fields);
      const res = await api.applyReview('existing');
      alert(res.message || 'Apply on existing runs requested.');
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Apply failed');
    } finally {
      setLoading(false);
    }
  };

  const handleApplySucceeding = async () => {
    setApiError(null);
    if (!docId) {
      setApiError('No document id available. Upload or load a document first.');
      return;
    }
    setLoading(true);
    try {
      await api.submitReview(docId, metadata, fields);
      const res = await api.applyReview('succeeding');
      alert(res.message || 'Apply on succeeding runs requested.');
    } catch (e) {
      setApiError(e instanceof Error ? e.message : 'Apply failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectionComplete = (pageIndex: number, bbox: BBox) => {
    setPendingSelection({ pageIndex, bbox });
  };

  const getSelectionValue = () => {
    if (!pendingSelection) return '';
    const { pageIndex, bbox } = pendingSelection;
    const selX0 = bbox.x;
    const selY0 = bbox.y;
    const selX1 = bbox.x + bbox.width;
    const selY1 = bbox.y + bbox.height;
    const wordsOnPage = fields.filter((f) => f.pageIndex === pageIndex && f.bbox);
    const inside = wordsOnPage.filter((f) => {
      const b = f.bbox!;
      const cx = b.x + b.width / 2;
      const cy = b.y + b.height / 2;
      return cx >= selX0 && cx <= selX1 && cy >= selY0 && cy <= selY1;
    });
    inside.sort((a, b) => {
      const ay = a.bbox!.y;
      const by = b.bbox!.y;
      if (Math.abs(ay - by) > 0.005) return ay - by;
      return a.bbox!.x - b.bbox!.x;
    });
    return inside.map((f) => f.value).join(' ');
  };

  const handleAddFieldSave = async (payload: AddFieldPayload) => {
    const newField: ExtractedField = {
      id: nextId(fields),
      key: payload.key,
      value: payload.value,
      pageIndex: payload.pageIndex,
      bbox: payload.bbox,
      rule: payload.rule || undefined,
    };

    // Remove underlying word-level TEXT fields inside the selection,
    // then add the new merged field instead.
    let nextFields: ExtractedField[];
    if (pendingSelection) {
      const { pageIndex, bbox } = pendingSelection;
      const selX0 = bbox.x;
      const selY0 = bbox.y;
      const selX1 = bbox.x + bbox.width;
      const selY1 = bbox.y + bbox.height;

      const filtered = fields.filter((f) => {
        if (f.pageIndex !== pageIndex || !f.bbox) return true;
        const b = f.bbox;
        const cx = b.x + b.width / 2;
        const cy = b.y + b.height / 2;
        const inside =
          cx >= selX0 && cx <= selX1 &&
          cy >= selY0 && cy <= selY1;
        // Drop only the original word-level TEXT fields inside the selection
        return !(inside && f.key.toLowerCase() === 'text');
      });
      nextFields = [...filtered, newField];
    } else {
      nextFields = [...fields, newField];
    }

    setFields(nextFields);

    // Persist updated fields to backend/Solr immediately so refresh keeps edits.
    if (docId) {
      try {
        await api.submitReview(docId, metadata, nextFields);
      } catch (err) {
        setApiError(err instanceof Error ? err.message : 'Failed to save field edits');
      }
    }
    setPendingSelection(null);
    setIsAddingField(false);
  };

  const handleAddFieldCancel = () => {
    setPendingSelection(null);
    setIsAddingField(false);
  };

  const showReview = !!docId;
  const visibleFields = fields.filter((f) => f.pageIndex === currentPageIndex);

  return (
    <div className="app">
      <header className="app-header">
        <h1>OCR Review — Human feedback</h1>
        <p>For new document types, upload a PDF and review OCR output. For existing types, open a document and re-apply rules.</p>
        {apiError && (
          <p className="app-api-error" role="alert">
            {apiError}
          </p>
        )}
        {loading && <p className="app-loading">Loading…</p>}
        <div className="app-mode-tabs">
          <button
            type="button"
            className={`app-mode-tab ${mode === 'new' ? 'app-mode-tab--active' : ''}`}
            onClick={() => {
              setMode('new');
              resetState();
            }}
          >
            New document type
          </button>
          <button
            type="button"
            className={`app-mode-tab ${mode === 'existing' ? 'app-mode-tab--active' : ''}`}
            onClick={() => {
              setMode('existing');
              resetState();
            }}
          >
            Existing document type
          </button>
        </div>
      </header>

      {mode === 'new' && (
        <UploadStep
          fileName={uploadedFile?.name ?? null}
          onFileSelect={handleFileSelect}
          onNext={handleUploadAndOcr}
          loading={loading}
        />
      )}

      {mode === 'existing' && (
        <div className="step-content">
          <h2 className="step-heading">Open existing document</h2>
          <p className="step-desc">Choose a previously processed document and open it for human review.</p>
          {recentDocs.length > 0 ? (
            <div className="metadata-label">
              <span style={{ marginBottom: '0.35rem', fontSize: '0.85rem', fontWeight: 600 }}>
                Previously uploaded documents
              </span>
              <select
                className="metadata-input"
                defaultValue=""
                onChange={(e) => {
                  const v = e.target.value;
                  if (!v) return;
                  void handleLoadExisting(v);
                }}
                disabled={loading}
              >
                <option value="">Select a document…</option>
                {recentDocs.map((d) => (
                  <option key={d.docId} value={d.docId}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <p className="step-desc">
              No documents found yet. Upload a PDF under "New document type" first, then it will appear here.
            </p>
          )}
        </div>
      )}

      {showReview && (
        <>
          <div className="app-layout">
            <aside className="app-panel app-panel--pdf">
              <PdfViewerWithHighlights
                fileUrl={displayPdfUrl}
                hoveredField={hoveredField}
                isAddingField={isAddingField}
                onSelectionComplete={handleSelectionComplete}
                onPageChange={setCurrentPageIndex}
              />
            </aside>
            <aside className="app-panel app-panel--kv">
              <KeyValueList
                fields={visibleFields}
                hoveredField={hoveredField}
                onHover={setHoveredField}
                isAddingField={isAddingField}
                onStartAddField={() => setIsAddingField(true)}
                onCancelAddField={() => setIsAddingField(false)}
                onAddMetadata={() => setShowMetadataModal(true)}
              />
              <div className="review-complete-bar">
                <button
                  type="button"
                  className="review-complete-btn review-complete-btn--existing"
                  onClick={handleRerunPrevious}
                >
                  Apply on existing runs
                </button>
                <button
                  type="button"
                  className="review-complete-btn review-complete-btn--succeeding"
                  onClick={handleApplySucceeding}
                >
                  Apply on succeeding runs
                </button>
              </div>
            </aside>
          </div>
          {pendingSelection && (
            <AddFieldModal
              pageIndex={pendingSelection.pageIndex}
              bbox={pendingSelection.bbox}
              initialValue={getSelectionValue()}
              onSave={handleAddFieldSave}
              onCancel={handleAddFieldCancel}
            />
          )}
          {showMetadataModal && (
            <DocumentMetadataModal
              initial={metadata}
              onSave={async (m) => {
                setMetadata(m);
                if (docId) {
                  try {
                    await api.saveMetadata(docId, m);
                  } catch (err) {
                    setApiError(err instanceof Error ? err.message : 'Failed to save document metadata');
                  }
                }
                setShowMetadataModal(false);
              }}
              onCancel={() => setShowMetadataModal(false)}
            />
          )}
        </>
      )}

      {showReview && (
        <ApplyActionsStep
          onRerunPrevious={handleRerunPrevious}
          onApplySucceeding={handleApplySucceeding}
          onStartOver={resetState}
        />
      )}
    </div>
  );
}

export default App;

