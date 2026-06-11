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

export function IconBtn2({ children, onClick, title, active, disabled, color }) {
  return (
    <button
      onClick={onClick}
      title={title}
      disabled={disabled}
      style={{
        background: active ? "rgba(99,102,241,0.12)" : "transparent",
        border: `1px solid ${active ? "rgba(99,102,241,0.3)" : "var(--color-border)"}`,
        color: disabled ? "var(--color-muted)" : (color || (active ? "var(--color-accent2)" : "var(--color-muted)")),
        width: "28px", height: "28px", borderRadius: "5px",
        display: "flex", alignItems: "center", justifyContent: "center",
        cursor: disabled ? "not-allowed" : "pointer",
        fontSize: "13px", opacity: disabled ? 0.35 : 1, transition: "all 0.12s", flexShrink: 0,
      }}
      onMouseEnter={(e) => { if (!disabled && !active) e.currentTarget.style.background = "var(--color-panel)"; }}
      onMouseLeave={(e) => { if (!disabled && !active) e.currentTarget.style.background = "transparent"; }}
    >
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

export function Btn({ children, onClick, accent }) {
  return (
    <button onClick={onClick} style={{ background: accent ? "rgba(99,102,241,0.12)" : "var(--color-surface)", border: `1px solid ${accent ? "rgba(99,102,241,0.3)" : "var(--color-border)"}`, color: accent ? "var(--color-accent2)" : "var(--color-muted)", padding: "5px 14px", borderRadius: "5px", fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer", transition: "all 0.15s" }}>
      {children}
    </button>
  );
}