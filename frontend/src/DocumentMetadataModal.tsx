import { useState, useEffect } from 'react';
import type { FileMetadata } from './api';
import './AddFieldModal.css';

interface DocumentMetadataModalProps {
  initial: FileMetadata;
  onSave: (metadata: FileMetadata) => void;
  onCancel: () => void;
}

export function DocumentMetadataModal({ initial, onSave, onCancel }: DocumentMetadataModalProps) {
  const [documentType, setDocumentType] = useState(initial.documentType ?? '');
  const [title, setTitle] = useState(initial.title ?? '');
  const [source, setSource] = useState(initial.source ?? '');
  const [date, setDate] = useState(initial.date ?? '');

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [onCancel]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      documentType: documentType.trim(),
      title: title.trim(),
      source: source.trim(),
      date: date.trim(),
    });
  };

  return (
    <div className="add-field-modal-backdrop" onClick={onCancel}>
      <div
        className="add-field-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="doc-metadata-modal-title"
      >
        <h2 id="doc-metadata-modal-title" className="add-field-modal-title">
          Document metadata
        </h2>
        <p className="add-field-modal-hint">Set metadata that applies to the whole document.</p>
        <form onSubmit={handleSubmit} className="add-field-form">
          <label className="add-field-label">
            Document type
          </label>
          <input
            type="text"
            className="add-field-input"
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value)}
            placeholder="e.g. Letter, Invoice, Contract"
          />
          <label className="add-field-label">Title</label>
          <input
            type="text"
            className="add-field-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Customer onboarding letter"
          />
          <label className="add-field-label">Source</label>
          <input
            type="text"
            className="add-field-input"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="e.g. Email, Scan, Upload portal"
          />
          <label className="add-field-label">Date</label>
          <input
            type="text"
            className="add-field-input"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            placeholder="e.g. 2024-03-05"
          />
          <div className="add-field-actions">
            <button type="button" className="add-field-btn add-field-btn--secondary" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="add-field-btn add-field-btn--primary">
              Save metadata
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

