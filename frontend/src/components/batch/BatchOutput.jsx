import { useState, useCallback, useEffect, useRef } from "react";
import { useDropzone } from "react-dropzone";
import { useOutputStore } from "../../store/outputStore";
import { useWsProgress } from "../../hooks/useWsProgress";
import {
  uploadBatch, fetchBatch, fetchBatchLogs, retryBatch, downloadExcel, downloadCertificate, downloadReportPDF,
} from "../../services/pumaApi";

// ── Helpers ───────────────────────────────────────────────────────────────────
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ── Upload form ───────────────────────────────────────────────────────────────
// FIX: Progress state (batchId, progress) used to be local — it was wiped
// every time setOutput("batch-progress", ...) was called because that causes
// OutputPanel to remount UploadForm fresh. The fix: store both values inside
// output.data (the store) so they survive remounts. initData carries whatever
// was already in output.data when the component mounts.
export function UploadForm({ initData = {} }) {
  const { addLog, setOutput, setLoading } = useOutputStore();
  const [files, setFiles]       = useState([]);
  // Seed from store so progress survives remounts
  const [batchId, setBatch]     = useState(initData.batch_id ?? null);
  const [progress, setProgress] = useState(initData.progress ?? null);

  // Keep store in sync whenever progress/batchId changes so the next mount
  // picks up the latest values.
  const syncStore = useCallback(
    (patch) => {
      useOutputStore.setState((s) => ({
        output: s.output ? { ...s.output, ...patch } : s.output,
      }));
    },
    []
  );

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
      const initialProgress = { processed: 0, total: res.total_pdfs, percent: 0, stage: "QUEUED" };
      setBatch(res.batch_id);
      setProgress(initialProgress);
      // Store both in output.data so if OutputPanel re-renders this component
      // from scratch the state is restored from initData.
      setOutput("batch-progress", { ...res, batch_id: res.batch_id, progress: initialProgress }, `Batch #${res.batch_id}`);
      addLog({ level: "success", message: `Batch #${res.batch_id} created — ${res.total_pdfs} PDFs queued` });
      setLoading(false);
    } catch (e) {
      addLog({ level: "error", message: `Upload failed: ${e.response?.data?.detail || e.message}` });
      setLoading(false);
    }
  };

  useWsProgress(batchId, {
    onProgress: (msg) => {
      const p = { processed: msg.processed, total: msg.total, percent: msg.progress_percent, stage: msg.stage };
      setProgress(p);
      syncStore({ progress: p });
      addLog({ level: "info", message: `[Batch #${msg.batch_id}] ${msg.stage} — ${msg.processed}/${msg.total}` });
    },
    onComplete: async (msg) => {
      const p = { processed: msg.processed, total: msg.total, percent: 100, stage: "DONE" };
      setProgress(p);
      syncStore({ progress: p });
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
      syncStore({ progress: null });
    },
  });

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "600px" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: 0, color: "var(--color-text)" }}>
        Upload PDFs
      </h2>

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
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text)" }}>{f.name}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
                {(f.size / 1024).toFixed(0)} KB
              </span>
            </div>
          ))}
        </div>
      )}

      {progress && (
        <div style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "14px", border: "1px solid var(--color-border)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-accent2)" }}>{progress.stage}</span>
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

// ── Status colors ─────────────────────────────────────────────────────────────
const STATUS_COLOR = {
  COMPLETED:  "var(--color-success)",
  PARTIAL:    "var(--color-warning)",
  FAILED:     "var(--color-error)",
  PROCESSING: "var(--color-accent2)",
  PENDING:    "var(--color-muted)",
};

// ── Download dropdown ─────────────────────────────────────────────────────────
function DownloadDropdown({ batchId, hasExcel, reports = [], reportCount = 0, onAction }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const activeReportCount = reportCount || reports.length || 0;

  const items = [
    hasExcel && {
      key: "excel",
      label: "Excel (.xlsx)",
      icon: "📊",
      desc: "All reports in this batch",
    },
    activeReportCount > 0 && {
      key: "pdfs",
      label: `Reports (.pdf)`,
      icon: "📄",
      desc: `${activeReportCount} renamed PDF(s)`,
    },
    activeReportCount > 0 && {
      key: "certificates",
      label: `Certificates (.docx)`,
      icon: "📝",
      desc: `${activeReportCount} certificate(s)`,
    },
    hasExcel && activeReportCount > 0 && {
      key: "all",
      label: "All files",
      icon: "📦",
      desc: "PDF, DOCX, and Excel for batch",
    },
  ].filter(Boolean);

  if (!items.length) return (
    <IconBtn title="No downloads available" disabled>⬇</IconBtn>
  );

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <IconBtn
        title="Downloads"
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        active={open}
      >
        ⬇
      </IconBtn>
      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 4px)",
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "8px",
            minWidth: "190px",
            zIndex: 50,
            boxShadow: "0 8px 24px rgba(0,0,0,0.3)",
            overflow: "hidden",
          }}
        >
          <div style={{ padding: "6px 12px 4px", fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", letterSpacing: "0.08em", borderBottom: "1px solid var(--color-border)" }}>
            DOWNLOAD
          </div>
          {items.map((item) => (
            <button
              key={item.key}
              onClick={(e) => { e.stopPropagation(); setOpen(false); onAction(item.key); }}
              style={{
                width: "100%", background: "none", border: "none",
                padding: "9px 14px", display: "flex", alignItems: "center", gap: "10px",
                cursor: "pointer", textAlign: "left",
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = "var(--color-panel)"}
              onMouseLeave={(e) => e.currentTarget.style.background = "none"}
            >
              <span style={{ fontSize: "14px" }}>{item.icon}</span>
              <div>
                <div style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-text)" }}>{item.label}</div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)" }}>{item.desc}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Icon button ───────────────────────────────────────────────────────────────
function IconBtn({ children, onClick, title, active, disabled, color }) {
  return (
    <button
      onClick={onClick}
      title={title}
      disabled={disabled}
      style={{
        background: active ? "rgba(99,102,241,0.12)" : "transparent",
        border: `1px solid ${active ? "rgba(99,102,241,0.3)" : "var(--color-border)"}`,
        color: disabled ? "var(--color-muted)" : (color || (active ? "var(--color-accent2)" : "var(--color-muted)")),
        width: "28px",
        height: "28px",
        borderRadius: "5px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: disabled ? "not-allowed" : "pointer",
        fontSize: "13px",
        opacity: disabled ? 0.35 : 1,
        transition: "all 0.12s",
        flexShrink: 0,
      }}
      onMouseEnter={(e) => { if (!disabled && !active) e.currentTarget.style.background = "var(--color-panel)"; }}
      onMouseLeave={(e) => { if (!disabled && !active) e.currentTarget.style.background = "transparent"; }}
    >
      {children}
    </button>
  );
}

// ── Batch list ────────────────────────────────────────────────────────────────
export function BatchList({ data, onAction }) {
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
        Batches{" "}
        <span style={{ color: "var(--color-muted)", fontSize: "12px", fontWeight: 400 }}>
          ({sorted.length})
        </span>
      </h2>

      {/* Column headers */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "48px 1fr 80px 90px 100px 96px",
        gap: "8px",
        padding: "4px 14px",
        fontFamily: "var(--font-mono)",
        fontSize: "9px",
        letterSpacing: "0.08em",
        color: "var(--color-muted)",
      }}>
        <span>#ID</span>
        <span>FACTORY / USER</span>
        <span>STATUS</span>
        <span>PDFs</span>
        <span>SUCCESS</span>
        <span style={{ textAlign: "right" }}>ACTIONS</span>
      </div>

      {sorted.map((b) => (
        <BatchRow key={b.id} batch={b} onAction={onAction} />
      ))}

      {sorted.length === 0 && (
        <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-muted)", padding: "32px 0", textAlign: "center" }}>
          No batches found.
        </div>
      )}
    </div>
  );
}

function BatchRow({ batch, onAction }) {
  const color    = STATUS_COLOR[batch.status] || "var(--color-muted)";
  const canRetry = (batch.status === "PARTIAL" || batch.status === "FAILED");
  const hasExcel = !!batch.excel_report_path || batch.excel_available;
  const reports  = batch.reports || [];

  return (
    <div
      onClick={() => onAction("view", batch.id)}
      style={{
        display: "grid",
        gridTemplateColumns: "48px 1fr 80px 90px 100px 96px",
        gap: "8px",
        padding: "10px 14px",
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderLeft: `3px solid ${color}`,
        borderRadius: "7px",
        alignItems: "center",
        transition: "border-color 0.15s",
        cursor: "pointer",
      }}
    >
      {/* ID */}
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)" }}>
        #{batch.id}
      </span>

      {/* Factory / user */}
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-text)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {batch.factory_code || "—"}
        </div>
        {batch.created_by && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
            by {batch.created_by.username}
          </div>
        )}
      </div>

      {/* Status badge */}
      <span style={{
        fontFamily: "var(--font-mono)", fontSize: "9px",
        color, background: `${color}18`,
        padding: "2px 7px", borderRadius: "3px",
        whiteSpace: "nowrap", display: "inline-block",
      }}>
        {batch.status}
      </span>

      {/* PDF counters */}
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-muted)" }}>
        {batch.processed_pdfs}/{batch.total_pdfs}
      </span>

      {/* Success rate */}
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: batch.success_rate === 100 ? "var(--color-success)" : "var(--color-warning)" }}>
        {batch.success_rate}%
      </span>

      {/* Actions */}
      <div style={{ display: "flex", gap: "4px", justifyContent: "flex-end" }} onClick={(e) => e.stopPropagation()}>
        <IconBtn
          title={canRetry ? "Retry failed PDFs" : "No failures to retry"}
          disabled={!canRetry}
          color="var(--color-warning)"
          onClick={() => onAction("retry", batch.id)}
        >↺</IconBtn>
        <IconBtn title="View logs" onClick={() => onAction("logs", batch.id)}>∷</IconBtn>
        <DownloadDropdown
          batchId={batch.id}
          hasExcel={hasExcel}
          reports={reports}
          reportCount={batch.report_count || reports.length || 0}
          onAction={(key) => onAction(key, batch.id, { reports, hasExcel })}
        />
      </div>
    </div>
  );
}

// ── Per-PDF retry modal ───────────────────────────────────────────────────────
function RetryModal({ failedPdfs, onConfirm, onCancel }) {
  const [selected, setSelected] = useState(
    failedPdfs.filter((f) => !f.retried).map((f) => f.filename)
  );

  const toggle = (filename) =>
    setSelected((prev) =>
      prev.includes(filename) ? prev.filter((n) => n !== filename) : [...prev, filename]
    );

  const allUnretried = failedPdfs.filter((f) => !f.retried);

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200,
    }}>
      <div className="fade-up" style={{
        background: "var(--color-surface)", border: "1px solid var(--color-border)",
        borderRadius: "12px", padding: "24px 28px", minWidth: "400px", maxWidth: "560px",
        display: "flex", flexDirection: "column", gap: "16px",
      }}>
        <div style={{ fontFamily: "var(--font-display)", fontSize: "15px", fontWeight: 700, color: "var(--color-text)" }}>
          Retry Failed PDFs
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
          Select which files to retry. Uncheck to skip.
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px", maxHeight: "300px", overflowY: "auto" }}>
          {failedPdfs.map((f) => (
            <label key={f.filename} style={{
              display: "flex", alignItems: "flex-start", gap: "10px",
              padding: "8px 12px", borderRadius: "6px",
              background: f.retried ? "rgba(34,211,160,0.05)" : "rgba(244,63,94,0.05)",
              border: `1px solid ${f.retried ? "rgba(34,211,160,0.15)" : "rgba(244,63,94,0.15)"}`,
              cursor: f.retried ? "default" : "pointer",
              opacity: f.retried ? 0.5 : 1,
            }}>
              <input
                type="checkbox"
                disabled={f.retried}
                checked={selected.includes(f.filename)}
                onChange={() => toggle(f.filename)}
                style={{ marginTop: "2px", accentColor: "var(--color-accent)" }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text)", wordBreak: "break-all" }}>
                  {f.filename}
                  {f.retried && <span style={{ color: "var(--color-success)", marginLeft: "8px" }}>✓ already retried</span>}
                </div>
                {f.reason && (
                  <div style={{ fontFamily: "var(--font-body)", fontSize: "10px", color: "var(--color-muted)", marginTop: "2px" }}>
                    {f.reason}
                  </div>
                )}
              </div>
            </label>
          ))}
        </div>
        <div style={{ display: "flex", gap: "8px", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
            {selected.length} of {allUnretried.length} selected
          </span>
          <div style={{ display: "flex", gap: "8px" }}>
            <button onClick={onCancel} style={ghostBtn}>Cancel</button>
            <button
              disabled={!selected.length}
              onClick={() => onConfirm(selected)}
              style={{
                ...ghostBtn,
                background: selected.length ? "var(--color-accent)" : "var(--color-border)",
                color: selected.length ? "#fff" : "var(--color-muted)",
                borderColor: selected.length ? "var(--color-accent)" : "var(--color-border)",
                cursor: selected.length ? "pointer" : "not-allowed",
              }}
            >
              Retry {selected.length ? `(${selected.length})` : ""}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

const ghostBtn = {
  background: "transparent", border: "1px solid var(--color-border)",
  color: "var(--color-muted)", padding: "6px 16px", borderRadius: "5px",
  fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer",
};

// ── Batch detail ──────────────────────────────────────────────────────────────
export function BatchDetail({ data }) {
  const { addLog, setOutput } = useOutputStore();
  const [showRetryModal, setShowRetryModal] = useState(false);

  const color         = STATUS_COLOR[data?.status] || "var(--color-muted)";
  const failedRecords = data?.failed_pdf_records || [];
  const failedCount   = data?.failed_pdfs_count ?? failedRecords.length;
  const hasRetryable  = failedRecords.some((f) => !f.retried);
  const canRetry      = (data?.status === "PARTIAL" || data?.status === "FAILED") && hasRetryable;

  const handleRetryConfirm = async (filenames) => {
    setShowRetryModal(false);
    addLog({ level: "info", message: `Retrying ${filenames.length} PDF(s) in Batch #${data.id}…` });
    try {
      const res = await retryBatch(data.id, filenames);
      addLog({ level: "success", message: `Retry started — ${res.files_retrying?.length} file(s)` });
      const updated = await fetchBatch(data.id);
      setOutput("batch", updated, `Batch #${data.id}`);
    } catch (e) {
      addLog({ level: "error", message: `Retry failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  const handleExcel = async () => {
    try {
      const blob = await downloadExcel(data.id);
      saveBlob(blob, `batch-${data.id}.xlsx`);
      addLog({ level: "success", message: `Excel downloaded for Batch #${data.id}` });
    } catch (e) {
      addLog({ level: "error", message: `Excel download failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {showRetryModal && (
        <RetryModal
          failedPdfs={failedRecords}
          onConfirm={handleRetryConfirm}
          onCancel={() => setShowRetryModal(false)}
        />
      )}

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
        {data?.created_by && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
            by {data.created_by.username}
          </span>
        )}
        <div style={{ flex: 1 }} />
        {data?.excel_available && (
          <Btn onClick={handleExcel} accent>⬇ Excel</Btn>
        )}
        {canRetry && (
          <Btn onClick={() => setShowRetryModal(true)}>↺ Retry Failed</Btn>
        )}
      </div>

      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px" }}>
        {[
          ["Total PDFs",   data?.total_pdfs],
          ["Processed",    data?.processed_pdfs],
          ["Failed",       failedCount],
          ["Success Rate", `${data?.success_rate}%`],
        ].map(([label, val]) => (
          <Stat key={label} label={label} value={val} />
        ))}
      </div>

      {/* Failed PDFs */}
      {failedRecords.length > 0 && (
        <Section title="Failed PDFs">
          {failedRecords.map((f) => (
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
              <div key={r.id} style={{ display: "flex", gap: "12px", padding: "8px 12px", background: "var(--color-panel)", borderRadius: "5px", border: "1px solid var(--color-border)", fontSize: "12px", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-accent2)", minWidth: "80px" }}>{r.style}</span>
                <span style={{ color: "var(--color-muted)" }}>{r.factory_code}</span>
                <span style={{ color: "var(--color-muted)" }}>{r.inspection_date}</span>
                {r.report_number && (
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-accent)" }}>#{r.report_number}</span>
                )}
                <span style={{ color: "var(--color-muted)", fontSize: "10px", flex: 1 }}>
                  POs: {r.po_numbers?.map((p) => p.number).join(", ")}
                </span>
                {/* FIX: use pdf_filename (stored by backend on InspectionReport) so the
                    downloaded .docx is named after the source PDF, e.g. ABC123.docx.
                    Falls back to style-id.docx if the field is absent. */}
                <ReportCertBtn reportId={r.id} style={r.style} pdfFilename={r.pdf_filename} />
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

// ── Per-report certificate button ─────────────────────────────────────────────
// FIX: accepts pdfFilename so the download is named after the original PDF.
function ReportCertBtn({ reportId, style: styleName, pdfFilename }) {
  const { addLog } = useOutputStore();
  const [busy, setBusy] = useState(false);

  const pdfName = pdfFilename || `${styleName}-${reportId}.pdf`;
  const docxName = pdfName.replace(/\.pdf$/i, ".docx");

  const handleClick = async (e) => {
    e.stopPropagation();
    setBusy(true);
    addLog({ level: "info", message: `Downloading PDF + certificate for ${styleName}…` });
    try {
      const pdfBlob = await downloadReportPDF(reportId);
      saveBlob(pdfBlob, pdfName);
      addLog({ level: "success", message: `PDF downloaded: ${pdfName}` });
    } catch (err) {
      addLog({ level: "error", message: `PDF failed: ${err.response?.data?.detail || err.message}` });
    }

    try {
      const certBlob = await downloadCertificate(reportId);
      saveBlob(certBlob, docxName);
      addLog({ level: "success", message: `Certificate downloaded: ${docxName}` });
    } catch (err) {
      addLog({ level: "error", message: `Certificate failed: ${err.response?.data?.detail || err.message}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={busy}
      title={`Download ${docxName}`}
      style={{
        background: "rgba(34,211,160,0.08)",
        border: "1px solid rgba(34,211,160,0.2)",
        color: "var(--color-success)",
        padding: "3px 10px",
        borderRadius: "4px",
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        cursor: busy ? "wait" : "pointer",
        opacity: busy ? 0.6 : 1,
        whiteSpace: "nowrap",
      }}
    >
      {busy ? "…" : "⬇ cert"}
    </button>
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

  const handleAction = async (action, id, meta = {}) => {
    switch (action) {
      case "view":
        setLoading(true);
        try {
          const data = await fetchBatch(id);
          setOutput("batch", data, `Batch #${id}`);
          addLog({ level: "info", message: `Loaded Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load Batch #${id}` });
          setLoading(false);
        }
        break;

      case "retry":
        setLoading(true);
        try {
          const data = await fetchBatch(id);
          setOutput("batch", data, `Batch #${id}`);
          addLog({ level: "info", message: `Loaded Batch #${id} — select files to retry` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load Batch #${id}` });
          setLoading(false);
        }
        break;

      case "logs":
        setLoading(true);
        try {
          const data = await fetchBatchLogs(id);
          setOutput("logs", data, `Logs · Batch #${id}`);
          addLog({ level: "info", message: `Logs loaded — ${data.total_failed} failed` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load logs for Batch #${id}` });
          setLoading(false);
        }
        break;

      case "excel":
        addLog({ level: "info", message: `Downloading Excel for Batch #${id}…` });
        try {
          const blob = await downloadExcel(id);
          saveBlob(blob, `batch-${id}.xlsx`);
          addLog({ level: "success", message: `Excel downloaded for Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Excel download failed: ${e.response?.data?.detail || e.message}` });
        }
        break;

      case "pdfs": {
        const reports = meta.reports?.length ? meta.reports : (await fetchBatch(id)).reports || [];
        addLog({ level: "info", message: `Downloading ${reports.length} PDF(s) for Batch #${id}…` });
        for (const report of reports) {
          try {
            const pdfName = report.pdf_filename || `${report.style}-${report.id}.pdf`;
            const blob = await downloadReportPDF(report.id);
            saveBlob(blob, pdfName);
            addLog({ level: "success", message: `PDF downloaded: ${pdfName}` });
          } catch (e) {
            addLog({ level: "error", message: `PDF failed: ${report.style}: ${e.response?.data?.detail || e.message}` });
          }
        }
        break;
      }

      case "certificates": {
        const reports = meta.reports?.length ? meta.reports : (await fetchBatch(id)).reports || [];
        addLog({ level: "info", message: `Downloading ${reports.length} certificate(s) for Batch #${id}…` });
        for (const report of reports) {
          try {
            const blob = await downloadCertificate(report.id);
            const docxName = report.pdf_filename
              ? report.pdf_filename.replace(/\.pdf$/i, ".docx")
              : `cert-${report.style}-${report.id}.docx`;
            saveBlob(blob, docxName);
            addLog({ level: "success", message: `Certificate downloaded: ${docxName}` });
          } catch (e) {
            addLog({ level: "error", message: `Certificate failed: ${report.style}: ${e.response?.data?.detail || e.message}` });
          }
        }
        break;
      }

      case "all": {
        const reports = meta.reports?.length ? meta.reports : (await fetchBatch(id)).reports || [];
        const includeExcel = meta.hasExcel ?? false;
        addLog({ level: "info", message: `Downloading all files for Batch #${id}…` });
        for (const report of reports) {
          try {
            const pdfName = report.pdf_filename || `${report.style}-${report.id}.pdf`;
            const pdfBlob = await downloadReportPDF(report.id);
            saveBlob(pdfBlob, pdfName);
            addLog({ level: "success", message: `PDF downloaded: ${pdfName}` });
          } catch (e) {
            addLog({ level: "error", message: `PDF failed: ${report.style}: ${e.response?.data?.detail || e.message}` });
          }
          try {
            const docxName = report.pdf_filename
              ? report.pdf_filename.replace(/\.pdf$/i, ".docx")
              : `cert-${report.style}-${report.id}.docx`;
            const certBlob = await downloadCertificate(report.id);
            saveBlob(certBlob, docxName);
            addLog({ level: "success", message: `Certificate downloaded: ${docxName}` });
          } catch (e) {
            addLog({ level: "error", message: `Certificate failed: ${report.style}: ${e.response?.data?.detail || e.message}` });
          }
        }
        if (includeExcel) {
          try {
            const blob = await downloadExcel(id);
            saveBlob(blob, `batch-${id}.xlsx`);
            addLog({ level: "success", message: `Excel downloaded for Batch #${id}` });
          } catch (e) {
            addLog({ level: "error", message: `Excel failed: ${e.response?.data?.detail || e.message}` });
          }
        }
        break;
      }
    }
  };

  if (output.type === "batch-list")     return <BatchList data={output.data} onAction={handleAction} />;
  if (output.type === "batch")          return <BatchDetail data={output.data} />;
  if (output.type === "logs")           return <BatchLogsView data={output.data} />;
  // FIX: pass output.data as initData so UploadForm seeds batchId + progress
  // from the store instead of always starting from null.
  if (output.type === "batch-progress") return <UploadForm initData={output.data ?? {}} />;
  return null;
}