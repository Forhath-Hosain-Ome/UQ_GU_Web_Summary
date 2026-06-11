import { BatchRow } from "./BatchRow"

export default function BatchList({ data, onAction }) {
  const results = data?.results || data || [];
  const sorted  = [...results].sort((a, b) => {
    const dateA = a.created_at || "";
    const dateB = b.created_at || "";
    if (dateA !== dateB) return dateB.localeCompare(dateA);
    return b.id - a.id;
  });

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "16px", fontWeight: 700, margin: "0 0 8px", color: "var(--color-text)" }}>
        Batches <span style={{ color: "var(--color-muted)", fontSize: "12px", fontWeight: 400 }}>({sorted.length})</span>
      </h2>

      <div style={{
        display: "grid", gridTemplateColumns: "48px 1fr 80px 90px 100px 96px",
        gap: "8px", padding: "4px 14px",
        fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.08em", color: "var(--color-muted)",
      }}>
        <span>#ID</span><span>FACTORY / USER</span><span>STATUS</span>
        <span>FOLDERS</span><span>SUCCESS</span><span style={{ textAlign: "right" }}>ACTIONS</span>
      </div>

      {sorted.map((b) => <BatchRow key={b.id} batch={b} onAction={onAction} />)}

      {sorted.length === 0 && (
        <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-muted)", padding: "32px 0", textAlign: "center" }}>
          No batches found.
        </div>
      )}
    </div>
  );
}