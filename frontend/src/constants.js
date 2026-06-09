export const mono  = { fontFamily: "var(--font-mono)" };
export const body  = { fontFamily: "var(--font-body)" };
export const disp  = { fontFamily: "var(--font-display)" };

export const fieldStyle = {
  width: "100%", padding: "9px 12px",
  background: "var(--color-panel)", border: "1px solid var(--color-border)",
  borderRadius: "6px", color: "var(--color-text)",
  fontFamily: "var(--font-mono)", fontSize: "12px", outline: "none",
  boxSizing: "border-box",
};

export const STATUS_COLOR = {
  COMPLETED:  "var(--color-success)",
  PARTIAL:    "var(--color-warning)",
  FAILED:     "var(--color-error)",
  PROCESSING: "var(--color-accent2)",
  PENDING:    "var(--color-muted)",
};

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}