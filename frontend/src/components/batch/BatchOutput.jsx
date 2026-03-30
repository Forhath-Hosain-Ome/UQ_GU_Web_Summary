import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useOutputStore } from "../../store/outputStore";
import { useWsProgress } from "../../hooks/useWsProgress";
import { uploadBatch, fetchBatches, fetchBatch, fetchBatchLogs, retryBatch, downloadExcel } from "../../services/pumaApi";

// ── Upload form ───────────────────────────────────────────────────────────────
export function UploadForm() {
  const { addLog, setOutput, setLoading } = useOutputStore();
  const [files, setFiles]   = useState([]);
  const [batchId, setBatch] = useState(null);
  const [progress, setProgress] = useState(null);

  const onDrop = useCallback((accepted) => setFiles(accepted), []);
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: true,
  });

  const handleUpload = async () => {
    if (!files.length) return;
    setLoading(true);
    addLog({ level: "info", message: `Uploading ${files.length} PDF(s)…` });
    try {
      const res = await uploadBatch(files);
      setBatch(res.batch_id);
      setProgress({ processed: 0, total: res.total_pdfs, percent: 0, stage: "QUEUED" });
      addLog({ level: "success", message: `Batch #${res.batch_id} created — ${res.total_pdfs} PDFs queued` });
      setOutput("batch-progress", res, `Batch #${res.batch_id}`);
      setLoading(false);
    } catch (e) {
      addLog({ level: "error", message: `Upload failed: ${e.response?.data?.detail || e.message}` });
      setLoading(false);
    }
  };

  // WS progress for the active batch
  useWsProgress(batchId, {
    onProgress: (msg) => {
      setProgress({ processed: msg.processed, total: msg.total, percent: msg.progress_percent, stage: msg.stage });
      addLog({ level: "info", message: `[Batch #${msg.batch_id}] ${msg.stage} — ${msg.processed}/${msg.total}` });
    },
    onComplete: async (msg) => {
      setProgress({ processed: msg.processed, total: msg.total, percent: 100, stage: "DONE" });
      addLog({ level: "success", message: `Batch #${msg.batch_id} complete — ${msg.report_count} reports saved` });
      if (msg.failed > 0)
        addLog({ level: "warning", message: `${msg.failed} PDF(s) failed in Batch #${msg.batch_id}` });
      const full = await fetchBatch(msg.batch_id);
      setOutput("batch", full, `Batch #${msg.batch_id}`);
      setBatch(null);
    },
    onError: (msg) => {
      addLog({ level: "error", message: `Batch #${msg.batch_id} error: ${msg.error_message}` });
      setProgress(null);
    },
  });

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "600px" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: 0, color: "var(--color-text)" }}>
        Upload PDFs
      </h2>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        style={{
          border: `2px dashed ${isDragActive ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "10px",
          padding: "40px 24px",
          textAlign: "center",
          cursor: "pointer",
          background: isDragActive ? "rgba(99,102,241,0.06)" : "var(--color-surface)",
          transition: "all 0.2s",
        }}
      >
        <input {...getInputProps()} />
        <div style={{ fontSize: "28px", marginBottom: "10px" }}>⬆</div>
        <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-muted)" }}>
          {isDragActive ? "Drop PDFs here…" : "Drag & drop PDFs or click to select"}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", marginTop: "6px", opacity: 0.6 }}>
          PDF only · 50 MB per file max
        </div>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {files.map((f, i) => (
            <div
              key={i}
              style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "7px 12px", background: "var(--color-surface)",
                borderRadius: "5px", border: "1px solid var(--color-border)",
              }}
            >
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text)" }}>
                {f.name}
              </span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
                {(f.size / 1024).toFixed(0)} KB
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Progress bar */}
      {progress && (
        <div style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "14px", border: "1px solid var(--color-border)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-accent2)" }}>
              {progress.stage}
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
              {progress.processed}/{progress.total}
            </span>
          </div>
          <div style={{ height: "4px", background: "var(--color-border)", borderRadius: "2px", overflow: "hidden" }}>
            <div
              style={{
                height: "100%",
                width: `${progress.percent}%`,
                background: progress.stage === "DONE" ? "var(--color-success)" : "var(--color-accent)",
                borderRadius: "2px",
                transition: "width 0.5s ease",
              }}
            />
          </div>
        </div>
      )}

      <button
        onClick={handleUpload}
        disabled={!files.length || !!batchId}
        style={{
          background: files.length && !batchId ? "var(--color-accent)" : "var(--color-border)",
          color: files.length && !batchId ? "#fff" : "var(--color-muted)",
          border: "none",
          padding: "10px 24px",
          borderRadius: "6px",
          fontFamily: "var(--font-display)",
          fontSize: "13px",
          fontWeight: 600,
          letterSpacing: "0.06em",
          cursor: files.length && !batchId ? "pointer" : "not-allowed",
          transition: "all 0.15s",
          alignSelf: "flex-start",
        }}
      >
        {batchId ? "PROCESSING…" : "UPLOAD & PROCESS"}
      </button>
    </div>
  );
}

// ── Batch list ────────────────────────────────────────────────────────────────
export function BatchList({ data, onSelect }) {
  const results = data?.results || data || [];
  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "16px", fontWeight: 700, margin: "0 0 8px", color: "var(--color-text)" }}>
        Batches <span style={{ color: "var(--color-muted)", fontSize: "12px", fontWeight: 400 }}>({results.length})</span>
      </h2>
      {results.map((b) => (
        <BatchCard key={b.id} batch={b} onClick={() => onSelect(b.id)} />
      ))}
    </div>
  );
}

const STATUS_COLOR = {
  COMPLETED:  "var(--color-success)",
  PARTIAL:    "var(--color-warning)",
  FAILED:     "var(--color-error)",
  PROCESSING: "var(--color-accent2)",
  PENDING:    "var(--color-muted)",
};

function BatchCard({ batch, onClick }) {
  const color = STATUS_COLOR[batch.status] || "var(--color-muted)";
  return (
    <div
      onClick={onClick}
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderLeft: `3px solid ${color}`,
        borderRadius: "7px",
        padding: "12px 16px",
        cursor: "pointer",
        transition: "border-color 0.15s",
        display: "flex",
        alignItems: "center",
        gap: "16px",
      }}
      onMouseEnter={(e) => e.currentTarget.style.borderColor = color}
      onMouseLeave={(e) => e.currentTarget.style.borderColor = "var(--color-border)"}
    >
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", gap: "10px", alignItems: "center", marginBottom: "4px" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)" }}>
            #{batch.id}
          </span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color, background: `${color}18`, padding: "1px 7px", borderRadius: "3px" }}>
            {batch.status}
          </span>
          <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-text)" }}>
            {batch.factory_code || "—"}
          </span>
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
          {batch.processed_pdfs}/{batch.total_pdfs} PDFs · {batch.success_rate}% success
        </div>
      </div>
      <span style={{ color: "var(--color-muted)", fontSize: "12px" }}>→</span>
    </div>
  );
}

// ── Batch detail ──────────────────────────────────────────────────────────────
export function BatchDetail({ data }) {
  const { addLog } = useOutputStore();
  const color = STATUS_COLOR[data?.status] || "var(--color-muted)";

  const handleRetry = async () => {
    try {
      await retryBatch(data.id);
      addLog({ level: "info", message: `Retry triggered for Batch #${data.id}` });
    } catch (e) {
      addLog({ level: "error", message: `Retry failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  const handleExcel = async () => {
    try {
      const blob = await downloadExcel(data.id);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = `batch-${data.id}.xlsx`; a.click();
      URL.revokeObjectURL(url);
      addLog({ level: "success", message: `Excel downloaded for Batch #${data.id}` });
    } catch (e) {
      addLog({ level: "error", message: `Excel download failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: 0 }}>
          Batch #{data?.id}
        </h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color, background: `${color}18`, padding: "2px 10px", borderRadius: "4px" }}>
          {data?.status}
        </span>
        <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-muted)" }}>
          {data?.factory_code}
        </span>
        <div style={{ flex: 1 }} />
        {data?.excel_available && (
          <Btn onClick={handleExcel} accent>⬇ Excel</Btn>
        )}
        {(data?.status === "PARTIAL" || data?.status === "FAILED") && (
          <Btn onClick={handleRetry}>↺ Retry Failed</Btn>
        )}
      </div>

      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px" }}>
        {[
          ["Total PDFs", data?.total_pdfs],
          ["Processed", data?.processed_pdfs],
          ["Failed", data?.failed_pdfs?.length ?? 0],
          ["Success Rate", `${data?.success_rate}%`],
        ].map(([label, val]) => (
          <Stat key={label} label={label} value={val} />
        ))}
      </div>

      {/* Failed PDFs */}
      {data?.failed_pdfs?.length > 0 && (
        <Section title="Failed PDFs">
          {data.failed_pdfs.map((f) => (
            <div key={f.id} style={{ padding: "8px 12px", background: "rgba(244,63,94,0.06)", borderRadius: "5px", borderLeft: "2px solid var(--color-error)", marginBottom: "4px" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-error)" }}>{f.filename}</div>
              <div style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--color-muted)", marginTop: "2px" }}>{f.reason}</div>
              {f.retried && <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-success)" }}>✓ retried</span>}
            </div>
          ))}
        </Section>
      )}

      {/* Reports list */}
      {data?.reports?.length > 0 && (
        <Section title={`Reports (${data.reports.length})`}>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {data.reports.map((r) => (
              <div key={r.id} style={{ display: "flex", gap: "12px", padding: "8px 12px", background: "var(--color-panel)", borderRadius: "5px", border: "1px solid var(--color-border)", fontSize: "12px" }}>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-accent2)", minWidth: "80px" }}>{r.style}</span>
                <span style={{ color: "var(--color-muted)" }}>{r.factory_code}</span>
                <span style={{ color: "var(--color-muted)" }}>{r.inspection_date}</span>
                <span style={{ color: "var(--color-muted)", fontSize: "10px" }}>POs: {r.po_numbers?.map(p => p.number).join(", ")}</span>
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

// ── Logs view ─────────────────────────────────────────────────────────────────
export function BatchLogsView({ data }) {
  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "16px", fontWeight: 700, margin: 0 }}>
          Batch #{data?.batch_id} · Logs
        </h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-warning)", background: "rgba(245,158,11,0.1)", padding: "2px 8px", borderRadius: "3px" }}>
          {data?.total_failed} failed · {data?.unretried} unretried
        </span>
      </div>
      {data?.failed_pdfs?.map((f) => (
        <div key={f.id} style={{ padding: "10px 14px", background: "var(--color-surface)", borderRadius: "6px", borderLeft: `2px solid ${f.retried ? "var(--color-success)" : "var(--color-error)"}` }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: f.retried ? "var(--color-success)" : "var(--color-error)" }}>{f.filename}</div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--color-muted)", marginTop: "4px" }}>{f.reason}</div>
        </div>
      ))}
      {data?.error_log && (
        <Section title="Raw Error Log">
          <pre style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.7, margin: 0 }}>
            {data.error_log}
          </pre>
        </Section>
      )}
    </div>
  );
}

// ── Shared subcomponents ──────────────────────────────────────────────────────
function Stat({ label, value }) {
  return (
    <div style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "7px", padding: "12px 14px" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "6px" }}>{label.toUpperCase()}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: "20px", fontWeight: 700, color: "var(--color-text)" }}>{value ?? "—"}</div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.08em", color: "var(--color-muted)", marginBottom: "8px" }}>{title.toUpperCase()}</div>
      {children}
    </div>
  );
}

function Btn({ children, onClick, accent }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: accent ? "rgba(99,102,241,0.12)" : "var(--color-surface)",
        border: `1px solid ${accent ? "rgba(99,102,241,0.3)" : "var(--color-border)"}`,
        color: accent ? "var(--color-accent2)" : "var(--color-muted)",
        padding: "5px 14px",
        borderRadius: "5px",
        fontFamily: "var(--font-mono)",
        fontSize: "11px",
        cursor: "pointer",
        transition: "all 0.15s",
      }}
    >
      {children}
    </button>
  );
}

// ── Router component ──────────────────────────────────────────────────────────
export default function BatchOutput({ output }) {
  const { setOutput, setLoading, addLog } = useOutputStore();

  const handleSelectBatch = async (id) => {
    setLoading(true);
    try {
      const data = await fetchBatch(id);
      setOutput("batch", data, `Batch #${id}`);
      addLog({ level: "info", message: `Loaded Batch #${id}` });
    } catch (e) {
      addLog({ level: "error", message: `Failed to load Batch #${id}` });
      setLoading(false);
    }
  };

  if (output.type === "batch-list")     return <BatchList data={output.data} onSelect={handleSelectBatch} />;
  if (output.type === "batch")          return <BatchDetail data={output.data} />;
  if (output.type === "logs")           return <BatchLogsView data={output.data} />;
  if (output.type === "batch-progress") return <UploadForm />;
  return null;
}
