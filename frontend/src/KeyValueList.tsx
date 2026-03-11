import { useState, useMemo } from 'react';
import type { ExtractedField } from './types';

interface KeyValueListProps {
  fields: ExtractedField[];
  hoveredField: ExtractedField | null;
  onHover: (field: ExtractedField | null) => void;
  isAddingField?: boolean;
  onStartAddField?: () => void;
  onCancelAddField?: () => void;
  onAddMetadata?: () => void;
}

export function KeyValueList({
  fields,
  hoveredField,
  onHover,
  isAddingField = false,
  onStartAddField,
  onCancelAddField,
  onAddMetadata,
}: KeyValueListProps) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return fields;
    return fields.filter((f) => {
      const key = (f.key ?? '').toLowerCase();
      const value = (f.value ?? '').toLowerCase();
      return key.includes(q) || value.includes(q);
    });
  }, [fields, query]);

  return (
    <div className="key-value-list">
      <div className="key-value-list-header">
        <h2 className="key-value-title">Extracted fields</h2>
        <div className="key-value-header-actions">
          <button
            type="button"
            className="key-value-meta-btn"
            onClick={onAddMetadata}
            title="Set document-level metadata (e.g. document type, title)"
          >
            Add document metadata
          </button>
          {!isAddingField ? (
            <button
              type="button"
              className="key-value-add-btn"
              onClick={onStartAddField}
              title="Add a field not extracted by OCR"
              aria-label="Add field"
            >
              <span className="key-value-add-icon" aria-hidden>+</span>
              Add field
            </button>
          ) : (
            <button
              type="button"
              className="key-value-cancel-btn"
              onClick={onCancelAddField}
            >
              Cancel
            </button>
          )}
        </div>
      </div>
      <div className="key-value-search">
        <input
          type="text"
          className="key-value-search-input"
          placeholder="Search by key or value…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {isAddingField && (
        <p className="key-value-hint key-value-hint--add">
          Drag on the PDF to highlight a region, then fill in the metadata and rule.
        </p>
      )}
      {!isAddingField && (
        <p className="key-value-hint">Hover a row to highlight its location in the PDF</p>
      )}
      <div className="key-value-rows">
        {filtered.map((field) => (
          <div
            key={field.id}
            className={`key-value-row ${hoveredField?.id === field.id ? 'key-value-row--hovered' : ''}`}
            onMouseEnter={() => onHover(field)}
            onMouseLeave={() => onHover(null)}
          >
            <div className="key-value-row-content">
              <dt className="key-value-key">{field.key}</dt>
              <dd className="key-value-value">{field.value}</dd>
            </div>
            {field.rule != null && field.rule !== '' && (
              <div className="key-value-rule" title="Rule">{field.rule}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
