import { Document, Page, pdfjs } from 'react-pdf';
import type { ExtractedField, BBox } from './types';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { useCallback, useState, useRef, useEffect } from 'react';

try {
  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url
  ).toString();
} catch {
  pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
}

interface PdfViewerWithHighlightsProps {
  fileUrl: string;
  hoveredField: ExtractedField | null;
  isAddingField?: boolean;
  onSelectionComplete?: (pageIndex: number, bbox: BBox) => void;
  onPageChange?: (pageIndex: number) => void;
}

export function PdfViewerWithHighlights({
  fileUrl,
  hoveredField,
  isAddingField = false,
  onSelectionComplete,
  onPageChange,
}: PdfViewerWithHighlightsProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [pageSizes, setPageSizes] = useState<Map<number, { width: number; height: number }>>(new Map());
  const [selectionDraft, setSelectionDraft] = useState<{
    pageIndex: number;
    startX: number;
    startY: number;
    currentX: number;
    currentY: number;
  } | null>(null);
  const pageWrapRefs = useRef<Map<number, HTMLDivElement | null>>(new Map());
  const [currentPageIndex, setCurrentPageIndex] = useState(0);

  const updateCurrentPage = useCallback(
    (updater: number | ((prev: number) => number)) => {
      setCurrentPageIndex((prev) => {
        const next = typeof updater === 'function' ? (updater as (p: number) => number)(prev) : updater;
        if (next !== prev) {
          onPageChange?.(next);
        }
        return next;
      });
    },
    [onPageChange],
  );

  const onDocumentLoadSuccess = useCallback(
    ({ numPages }: { numPages: number }) => {
      setNumPages(numPages);
    },
    []
  );

  const onPageLoadSuccess = useCallback(
    (pageIndex: number) => (page: { width: number; height: number }) => {
      setPageSizes((prev) => {
        const next = new Map(prev);
        next.set(pageIndex, { width: page.width, height: page.height });
        return next;
      });
    },
    []
  );

  const handleSelectionStart = useCallback(
    (pageIndex: number, e: React.MouseEvent) => {
      if (!isAddingField || !onSelectionComplete) return;
      e.preventDefault();
      const el = pageWrapRefs.current.get(pageIndex);
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const startX = e.clientX - rect.left;
      const startY = e.clientY - rect.top;
      setSelectionDraft({ pageIndex, startX, startY, currentX: startX, currentY: startY });
    },
    [isAddingField, onSelectionComplete]
  );

  const handleSelectionMove = useCallback((e: MouseEvent) => {
    setSelectionDraft((prev) => {
      if (!prev) return null;
      const el = pageWrapRefs.current.get(prev.pageIndex);
      if (!el) return prev;
      const rect = el.getBoundingClientRect();
      const currentX = e.clientX - rect.left;
      const currentY = e.clientY - rect.top;
      return { ...prev, currentX, currentY };
    });
  }, []);

  const handleSelectionEnd = useCallback(() => {
    setSelectionDraft((prev) => {
      if (!prev || !onSelectionComplete) return null;
      const el = pageWrapRefs.current.get(prev.pageIndex);
      if (!el) return null;
      const rect = el.getBoundingClientRect();
      const currentX = prev.currentX;
      const currentY = prev.currentY;
      const startX = prev.startX;
      const startY = prev.startY;
      const x0 = Math.max(0, Math.min(startX, currentX));
      const y0 = Math.max(0, Math.min(startY, currentY));
      const x1 = Math.min(rect.width, Math.max(startX, currentX));
      const y1 = Math.min(rect.height, Math.max(startY, currentY));
      const w = x1 - x0;
      const h = y1 - y0;
      if (w < 4 || h < 4) return null;
      const bbox: BBox = {
        x: Math.max(0, Math.min(1, x0 / rect.width)),
        y: Math.max(0, Math.min(1, y0 / rect.height)),
        width: Math.max(0.01, Math.min(1, w / rect.width)),
        height: Math.max(0.01, Math.min(1, h / rect.height)),
      };
      onSelectionComplete(prev.pageIndex, bbox);
      return null;
    });
  }, [onSelectionComplete]);

  useEffect(() => {
    if (!selectionDraft) return;
    window.addEventListener('mousemove', handleSelectionMove);
    window.addEventListener('mouseup', handleSelectionEnd);
    return () => {
      window.removeEventListener('mousemove', handleSelectionMove);
      window.removeEventListener('mouseup', handleSelectionEnd);
    };
  }, [selectionDraft, handleSelectionMove, handleSelectionEnd]);

  return (
    <div className="pdf-viewer-wrap">
      <div className="pdf-page-controls">
        <button
          type="button"
          className="pdf-page-btn"
          onClick={() => updateCurrentPage((p) => Math.max(0, p - 1))}
          disabled={currentPageIndex === 0}
        >
          ‹ Prev
        </button>
        <span className="pdf-page-indicator">
          Page {numPages === 0 ? '–' : currentPageIndex + 1} of {numPages || '–'}
        </span>
        <button
          type="button"
          className="pdf-page-btn"
          onClick={() =>
            updateCurrentPage((p) =>
              numPages === 0 ? p : Math.min(numPages - 1, p + 1),
            )
          }
          disabled={numPages === 0 || currentPageIndex >= numPages - 1}
        >
          Next ›
        </button>
      </div>
      <Document
        file={fileUrl}
        onLoadSuccess={onDocumentLoadSuccess}
        loading={
          <div className="pdf-loading">Loading PDF…</div>
        }
        error={
          <div className="pdf-error">Failed to load PDF. Make sure the file is served from /sample/ADA146693.pdf</div>
        }
      >
        {numPages > 0 && (
          <div
            className="pdf-page-wrap"
            ref={(el) => {
              pageWrapRefs.current.set(currentPageIndex, el);
            }}
          >
            <Page
              pageNumber={currentPageIndex + 1}
              width={500}
              onLoadSuccess={onPageLoadSuccess(currentPageIndex)}
              renderTextLayer={true}
              renderAnnotationLayer={true}
            />
            {hoveredField?.pageIndex === currentPageIndex && (() => {
              const size = pageSizes.get(currentPageIndex);
              if (!size) return null;
              const { bbox } = hoveredField;
              const left = bbox.x * 500;
              const top = bbox.y * 500 * (size.height / size.width);
              const width = bbox.width * 500;
              const height = bbox.height * 500 * (size.height / size.width);
              return (
                <div
                  className="pdf-highlight-overlay"
                  style={{
                    left,
                    top,
                    width,
                    height,
                  }}
                  aria-hidden
                />
              );
            })()}
            {isAddingField && (
              <div
                className="pdf-selection-overlay"
                onMouseDown={(e) => handleSelectionStart(currentPageIndex, e)}
                title="Drag to highlight a region, then fill in metadata"
              >
                {selectionDraft?.pageIndex === currentPageIndex && (
                  <div
                    className="pdf-selection-draft"
                    style={{
                      left: Math.min(selectionDraft.startX, selectionDraft.currentX),
                      top: Math.min(selectionDraft.startY, selectionDraft.currentY),
                      width: Math.abs(selectionDraft.currentX - selectionDraft.startX),
                      height: Math.abs(selectionDraft.currentY - selectionDraft.startY),
                    }}
                  />
                )}
              </div>
            )}
          </div>
        )}
      </Document>
    </div>
  );
}
