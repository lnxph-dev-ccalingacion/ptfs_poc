import './Steps.css';

interface ApplyActionsStepProps {
  onRerunPrevious: () => void;
  onApplySucceeding: () => void;
  onStartOver?: () => void;
}

export function ApplyActionsStep({
  onRerunPrevious,
  onApplySucceeding,
  onStartOver,
}: ApplyActionsStepProps) {
  return (
    <div className="step-content step-apply">
      <h2 className="step-heading">Apply review</h2>
      <p className="step-desc">
        Human review is complete. Choose how to apply this feedback.
      </p>
      <div className="apply-actions">
        <button
          type="button"
          className="apply-action-btn apply-action-btn--previous"
          onClick={onRerunPrevious}
        >
          <span className="apply-action-label">Rerun on previous files</span>
          <span className="apply-action-hint">
            Apply this review to files already processed in this batch
          </span>
        </button>
        <button
          type="button"
          className="apply-action-btn apply-action-btn--succeeding"
          onClick={onApplySucceeding}
        >
          <span className="apply-action-label">Apply to succeeding files</span>
          <span className="apply-action-hint">
            Use this review for files processed after this one
          </span>
        </button>
      </div>
      {onStartOver && (
        <button
          type="button"
          className="step-back-btn"
          onClick={onStartOver}
        >
          Start over with a new file
        </button>
      )}
    </div>
  );
}
