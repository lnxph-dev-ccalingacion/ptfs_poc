import { useRef } from 'react';
import './Steps.css';

interface UploadStepProps {
  fileName: string | null;
  onFileSelect: (file: File) => void;
  onNext: () => void;
  onUseSample?: () => void;
  loading?: boolean;
}

export function UploadStep({ fileName, onFileSelect, onNext, onUseSample, loading }: UploadStepProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.type === 'application/pdf') {
      onFileSelect(file);
    }
  };

  return (
    <div className="step-content step-upload">
      <h2 className="step-heading">Upload file</h2>
      <p className="step-desc">Choose a PDF to process and review.</p>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        onChange={handleChange}
        className="step-file-input"
        aria-label="Select PDF file"
      />
      <button
        type="button"
        className="step-browse-btn"
        onClick={() => inputRef.current?.click()}
      >
        {fileName ? `Selected: ${fileName}` : 'Browse or drop PDF'}
      </button>
      {fileName && (
        <button type="button" className="step-next-btn" onClick={onNext} disabled={loading}>
          {loading ? 'Uploading…' : 'Upload & run OCR'}
        </button>
      )}
      {onUseSample && (
        <button type="button" className="step-back-btn" onClick={onUseSample} style={{ marginTop: '0.75rem' }}>
          Use sample file instead
        </button>
      )}
    </div>
  );
}
