export function PrimaryBtn({ children, onClick, disabled, danger }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`disp primary-btn ${
        disabled
        ? "primary-btn--disabled"
        : danger
        ? "primary-btn--danger"
        : "primary-btn--default"
      }`}
    >
      {children}
    </button>
  );
}

export function GhostBtn({ children, onClick, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} className={`mono ghost-btn`}>
      {children}
    </button>
  );
}

export function IconBtn({ children, onClick, title, disabled }) {
  return (
    <button onClick={onClick} title={title} disabled={disabled} className={` icon-btn`}>
      {children}
    </button>
  );
}

export function ErrBtn({ handleDownload, busy, batchId }) {
  return (
    <button
          onClick={handleDownload}
          disabled={busy}
          title={`Download error JSON for Batch #${batchId}`}
          className="download-btn"
        >
          {busy ? "…" : `⬇ Batch #${batchId}`}
        </button>
  );
}