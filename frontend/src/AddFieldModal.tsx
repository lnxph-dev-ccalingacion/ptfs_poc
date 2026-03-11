import { useState, useEffect } from 'react';
import type { BBox } from './types';
import './AddFieldModal.css';

export interface AddFieldPayload {
  key: string;
  value: string;
  rule: string;
  pageIndex: number;
  bbox: BBox;
}

interface AddFieldModalProps {
  pageIndex: number;
  bbox: BBox;
  onSave: (payload: AddFieldPayload) => void;
  onCancel: () => void;
  initialValue?: string;
}

export function AddFieldModal({ pageIndex, bbox, onSave, onCancel, initialValue }: AddFieldModalProps) {
  const [key, setKey] = useState('');
  const [value, setValue] = useState(initialValue ?? '');
  const [rule, setRule] = useState('');

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [onCancel]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const k = key.trim();
    if (!k) return;
    onSave({
      key: k,
      value: value.trim(),
      rule: rule.trim(),
      pageIndex,
      bbox,
    });
  };

  return (
    <div className="add-field-modal-backdrop" onClick={onCancel}>
      <div
        className="add-field-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="add-field-modal-title"
      >
        <h2 id="add-field-modal-title" className="add-field-modal-title">
          Add field (page {pageIndex + 1})
        </h2>
        <p className="add-field-modal-hint">
          You highlighted a region on the PDF. Enter the metadata and rule for this field.
        </p>
        <form onSubmit={handleSubmit} className="add-field-form">
          <label className="add-field-label">
            Key (field name) <span className="add-field-required">*</span>
          </label>
          <input
            type="text"
            className="add-field-input"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="e.g. Contract Number"
            autoFocus
            required
          />
          <label className="add-field-label">Value (auto from selection, editable)</label>
          <input
            type="text"
            className="add-field-input"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Extracted or manual value"
          />
          <label className="add-field-label">Rule (optional)</label>
          <input
            type="text"
            className="add-field-input"
            value={rule}
            onChange={(e) => setRule(e.target.value)}
            placeholder="e.g. Must match pattern, required, etc."
          />
          <div className="add-field-actions">
            <button type="button" className="add-field-btn add-field-btn--secondary" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="add-field-btn add-field-btn--primary" disabled={!key.trim()}>
              Save field
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
