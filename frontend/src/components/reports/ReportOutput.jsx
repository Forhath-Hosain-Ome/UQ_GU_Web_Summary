import { useOutputStore } from "../../store/outputStore";
import { downloadCertificate, fetchReport } from "../../services/pumaApi";

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ── Report list ───────────────────────────────────────────────────────────────
function ReportList({ data, onSelect }) {
  const results = data?.results || data || [];
  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "16px", fontWeight: 700, margin: "0 0 8px" }}>
        Reports <span style={{ color: "var(--color-muted)", fontSize: "12px", fontWeight: 400 }}>({results.length})</span>
      </h2>
      {results.map((r) => (
        <div
          key={r.id}
          onClick={() => onSelect(r.id)}
          style={{
            display: "flex", gap: "12px", padding: "10px 14px",
            background: "var(--color-surface)", borderRadius: "6px",
            border: "1px solid var(--color-border)",
            cursor: "pointer", transition: "border-color 0.15s", alignItems: "center",
          }}
          onMouseEnter={(e) => e.currentTarget.style.borderColor = "var(--color-accent)"}
          onMouseLeave={(e) => e.currentTarget.style.borderColor = "var(--color-border)"}
        >
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)", minWidth: "80px" }}>{r.style}</span>
          <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-text)", flex: 1 }}>{r.factory_name || r.factory_code}</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>{r.inspection_date}</span>
          <span style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--color-muted)", fontSize: "10px" }}>
            {r.po_numbers?.map((p) => p.number).join(", ")}
          </span>
          <span style={{ color: "var(--color-muted)", fontSize: "12px" }}>→</span>
        </div>
      ))}
    </div>
  );
}

// ── Report detail ─────────────────────────────────────────────────────────────
function ReportDetail({ data }) {
  const { addLog } = useOutputStore();

  const handleCert = async () => {
    try {
      const blob = await downloadCertificate(data.id);
      saveBlob(blob, `cert-${data.style}-${data.id}.docx`);
      addLog({ level: "success", message: `Certificate downloaded for ${data.style}` });
    } catch (e) {
      addLog({ level: "error", message: `Certificate download failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  const fields = [
    ["Style",          data?.style],
    ["Description",    data?.description],
    ["Factory Code",   data?.factory_code],
    ["Factory Name",   data?.factory_name],
    ["Final Customer", data?.final_customer],
    ["Inspection Date",data?.inspection_date],
    ["Sample Size",    data?.sample_size],
    ["PO Qty",         data?.po_qty],
    ["Actual Qty",     data?.actual_qty],
    ["Inspected Qty",  data?.inspected_qty],
    ["Major Defect",   data?.major_defect],
    ["Minor Defect",   data?.minor_defect],
  ];

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: 0 }}>
          {data?.style}
        </h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>#{data?.id}</span>
        <div style={{ flex: 1 }} />
        <button
          onClick={handleCert}
          style={{
            background: "rgba(34,211,160,0.1)", border: "1px solid rgba(34,211,160,0.25)",
            color: "var(--color-success)", padding: "5px 14px", borderRadius: "5px",
            fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer",
          }}
        >
          ⬇ Certificate (.docx)
        </button>
      </div>

      {/* Fields grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "8px" }}>
        {fields.map(([label, val]) => val && (
          <div key={label} style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "6px", padding: "10px 14px" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "4px" }}>{label.toUpperCase()}</div>
            <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-text)" }}>{val}</div>
          </div>
        ))}
      </div>

      {/* PO Numbers */}
      {data?.po_numbers?.length > 0 && (
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "8px" }}>PO NUMBERS</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
            {data.po_numbers.map((p) => (
              <span key={p.id} style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)", background: "rgba(99,102,241,0.1)", padding: "3px 10px", borderRadius: "4px" }}>
                {p.number}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Certificate history */}
      {data?.certificate_logs?.length > 0 && (
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "8px" }}>CERTIFICATE HISTORY</div>
          {data.certificate_logs.map((c) => (
            <div key={c.id} style={{ display: "flex", gap: "10px", padding: "7px 12px", background: "var(--color-surface)", borderRadius: "5px", border: "1px solid var(--color-border)", marginBottom: "4px", fontSize: "11px" }}>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-muted)" }}>{new Date(c.generated_at).toLocaleString()}</span>
              <span style={{ color: "var(--color-muted)" }}>by {c.generated_by || "anon"}</span>
              {c.was_downloaded
                ? <span style={{ color: "var(--color-success)", marginLeft: "auto" }}>✓ downloaded</span>
                : <span style={{ color: "var(--color-warning)", marginLeft: "auto" }}>not downloaded</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Router ────────────────────────────────────────────────────────────────────
export default function ReportOutput({ output }) {
  const { setOutput, setLoading, addLog } = useOutputStore();

  const handleSelect = async (id) => {
    setLoading(true);
    try {
      const data = await fetchReport(id);
      setOutput("report", data, `Report · ${data.style}`);
      addLog({ level: "info", message: `Loaded report ${data.style}` });
    } catch (e) {
      addLog({ level: "error", message: `Failed to load report #${id}` });
      setLoading(false);
    }
  };

  if (output.type === "report-list") return <ReportList data={output.data} onSelect={handleSelect} />;
  if (output.type === "report")      return <ReportDetail data={output.data} />;
  return null;
}
