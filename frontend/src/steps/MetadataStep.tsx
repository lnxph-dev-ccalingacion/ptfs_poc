import { useState } from 'react';
import './Steps.css';

export interface FileMetadata {
  documentType: string;
  title: string;
  source: string;
  date: string;
}

const DEFAULT_METADATA: FileMetadata = {
  documentType: '',
  title: '',
  source: '',
  date: '',
};

interface MetadataStepProps {
  initialMetadata?: Partial<FileMetadata>;
  onNext: (metadata: FileMetadata) => void;
}

export function MetadataStep({ initialMetadata, onNext }: MetadataStepProps) {
  const [meta, setMeta] = useState<FileMetadata>({
    ...DEFAULT_METADATA,
    ...initialMetadata,
  });

  const update = (key: keyof FileMetadata, value: string) => {
    setMeta((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onNext(meta);
  };

  return (
    <div className="step-content step-metadata">
      <h2 className="step-heading">Assign metadata</h2>
      <p className="step-desc">Add metadata for this file. You can edit extracted values later in human review.</p>
      <form onSubmit={handleSubmit} className="metadata-form">
        <label className="metadata-label">
          Document type
          <input
            type="text"
            className="metadata-input"
            value={meta.documentType}
            onChange={(e) => update('documentType', e.target.value)}
            placeholder="e.g. Report, Contract"
          />
        </label>
        <label className="metadata-label">
          Title
          <input
            type="text"
            className="metadata-input"
            value={meta.title}
            onChange={(e) => update('title', e.target.value)}
            placeholder="Document title"
          />
        </label>
        <label className="metadata-label">
          Source
          <input
            type="text"
            className="metadata-input"
            value={meta.source}
            onChange={(e) => update('source', e.target.value)}
            placeholder="e.g. DTIC, Internal"
          />
        </label>
        <label className="metadata-label">
          Date
          <input
            type="text"
            className="metadata-input"
            value={meta.date}
            onChange={(e) => update('date', e.target.value)}
            placeholder="e.g. February 1984"
          />
        </label>
        <button type="submit" className="step-next-btn">
          Next: Human review
        </button>
      </form>
    </div>
  );
}
