/**
 * AuditOutput.jsx
 * ----------------
 * Rendered by OutputPanel when output.source === "audit".
 *
 * Handles these output.type values:
 *   audit-upload          → UploadView
 *   audit-batch-list      → AuditBatchList
 *   audit-batch           → AuditBatchDetail
 *   audit-batch-logs      → AuditBatchLogsView
 *   audit-export          → ExportView
 *   audit-retry-search    → RetrySearchView
 *   audit-retry-upload    → RetryUploadView
 *   audit-settings        → SettingsView (buyers / factories / pairs)
 */

import { useState, useRef, useCallback, useEffect } from "react";
import { useOutputStore } from "../../store/outputStore";
import { useAuthStore }   from "../../store/authStore";
import {
  uploadBatch,
  fetchBatch,
  searchBlocked,
  downloadErrorJson,
  uploadFixedJson,
  downloadSummary,
} from "../../services/finalSummaryApi";

// ─────────────────────────────────────────────────────────────────────────────
// Shared primitives
// ─────────────────────────────────────────────────────────────────────────────

const mono  = { fontFamily: "var(--font-mono)" };
const body  = { fontFamily: "var(--font-body)" };
const disp  = { fontFamily: "var(--font-display)" };

const fieldStyle = {
  width: "100%", padding: "9px 12px",
  background: "var(--color-panel)", border: "1px solid var(--color-border)",
  borderRadius: "6px", color: "var(--color-text)",
  fontFamily: "var(--font-mono)", fontSize: "12px", outline: "none",
  boxSizing: "border-box",
};

const STATUS_COLOR = {
  COMPLETED:  "var(--color-success)",
  PARTIAL:    "var(--color-warning)",
  FAILED:     "var(--color-error)",
  PROCESSING: "var(--color-accent2)",
  PENDING:    "var(--color-muted)",
};

function Label({ children, required }) {
  return (
    <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "5px" }}>
      {children}{required && <span style={{ color: "var(--color-error)", marginLeft: "2px" }}>*</span>}
    </div>
  );
}

function SectionTitle({ children }) {
  return (
    <div style={{ ...mono, fontSize: "10px", letterSpacing: "0.1em", color: "var(--color-muted)", marginBottom: "10px" }}>
      {children}
    </div>
  );
}

function Card({ children, accent }) {
  return (
    <div style={{
      background: "var(--color-surface)", border: "1px solid var(--color-border)",
      borderLeft: accent ? `3px solid ${accent}` : "1px solid var(--color-border)",
      borderRadius: "7px", padding: "14px 16px",
    }}>
      {children}
    </div>
  );
}

function PrimaryBtn({ children, onClick, disabled, danger }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      background: disabled ? "var(--color-border)" : (danger ? "var(--color-error)" : "var(--color-accent)"),
      color: disabled ? "var(--color-muted)" : "#fff",
      border: "none", padding: "10px 24px", borderRadius: "6px",
      ...disp, fontSize: "13px", fontWeight: 600, letterSpacing: "0.06em",
      cursor: disabled ? "not-allowed" : "pointer", transition: "all 0.15s",
    }}>
      {children}
    </button>
  );
}

function GhostBtn({ children, onClick, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      background: "transparent", border: "1px solid var(--color-border)",
      color: disabled ? "var(--color-muted)" : "var(--color-text)",
      padding: "8px 18px", borderRadius: "6px",
      ...mono, fontSize: "11px", cursor: disabled ? "not-allowed" : "pointer", transition: "all 0.15s",
      opacity: disabled ? 0.5 : 1,
    }}>
      {children}
    </button>
  );
}

function StatGrid({ stats }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${stats.length}, 1fr)`, gap: "8px" }}>
      {stats.map(([label, val, color]) => (
        <div key={label} style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "7px", padding: "12px 14px" }}>
          <div style={{ ...mono, fontSize: "9px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "5px" }}>{label}</div>
          <div style={{ ...disp, fontSize: "20px", fontWeight: 700, color: color || "var(--color-text)" }}>{val ?? "—"}</div>
        </div>
      ))}
    </div>
  );
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// WS hook for audit batches
function useAuditWs(batchId, { onProgress, onComplete, onError } = {}) {
  const cbsRef = useRef({ onProgress, onComplete, onError });
  useEffect(() => { cbsRef.current = { onProgress, onComplete, onError }; });

  useEffect(() => {
    if (!batchId) return;
    const token = useAuthStore.getState().access;
    if (!token) return;
    let cancelled = false;

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/ws/audit-batches/${batchId}/progress/?token=${token}`;
    const ws = new WebSocket(url);

    ws.onmessage = (e) => {
      if (cancelled) return;
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.event === "progress") cbsRef.current.onProgress?.(msg);
      if (msg.event === "complete") { cbsRef.current.onComplete?.(msg); ws.close(1000); }
      if (msg.event === "error")    cbsRef.current.onError?.(msg);
    };
    ws.onerror = () => ws.close();

    return () => {
      cancelled = true;
      if (ws.readyState === WebSocket.OPEN) ws.close(1000);
    };
  }, [batchId]);
}

// ─────────────────────────────────────────────────────────────────────────────
// Upload view
// ─────────────────────────────────────────────────────────────────────────────
function UploadView({ data }) {
  const { addLog, setOutput } = useOutputStore();
  const options  = data?.options ?? { pairs: [], buyers: [], factories: [] };
  const pairs    = options.pairs ?? [];

  const [files,    setFiles]    = useState([]);
  const [pairId,   setPairId]   = useState("");
  const [date,     setDate]     = useState(new Date().toISOString().slice(0, 10));
  const [isDrag,   setIsDrag]   = useState(false);
  const [batchId,  setBatchId]  = useState(null);
  const [progress, setProgress] = useState(null);
  const [busy,     setBusy]     = useState(false);
  const inputRef = useRef(null);

  // Derived: the selected pair object
  const selectedPair = pairs.find(p => String(p.id) === String(pairId));

  const addFiles = useCallback((incoming) => {
    const valid = [...incoming].filter(f =>
      f.name.toLowerCase().endsWith(".xlsx") || f.name.toLowerCase().endsWith(".xls")
    );
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...valid.filter(f => !names.has(f.name))];
    });
  }, []);

  const onDrop = useCallback((e) => {
    e.preventDefault(); setIsDrag(false);
    addFiles(e.dataTransfer.files);
  }, [addFiles]);

  useAuditWs(batchId, {
    onProgress: (msg) => {
      setProgress({ processed: msg.processed, total: msg.total, percent: msg.progress_percent, stage: msg.stage });
      addLog({ level: "info", message: `[Batch #${msg.batch_id}] ${msg.stage} — ${msg.processed}/${msg.total}` });
    },
    onComplete: async (msg) => {
      setProgress({ processed: msg.processed, total: msg.total, percent: 100, stage: "DONE" });
      addLog({ level: "success", message: `Batch #${msg.batch_id} complete — ${msg.report_count} record(s) saved` });
      if (msg.failed > 0)
        addLog({ level: "warning", message: `${msg.failed} file(s) failed — use Retry › Download Error JSON to fix` });
      setBusy(false);
      // Navigate to batch detail
      try {
        const batch = await fetchBatch(msg.batch_id);
        setOutput("audit-batch", batch, `Batch #${msg.batch_id}`, { source: "audit" });
      } catch {}
    },
    onError: (msg) => {
      addLog({ level: "error", message: `Batch error: ${msg.error_message}` });
      setBusy(false); setProgress(null); setBatchId(null);
    },
  });

  const handleUpload = async () => {
    if (!files.length || !pairId || !date || busy) return;
    setBusy(true);
    addLog({ level: "info", message: `Uploading ${files.length} file(s) for pair #${pairId}…` });
    try {
      const res = await uploadBatch(files, pairId, date);
      setBatchId(res.batch_id);
      setProgress({ processed: 0, total: res.total_files, percent: 0, stage: "QUEUED" });
      addLog({ level: "success", message: `Batch #${res.batch_id} created — ${res.total_files} file(s) queued` });
    } catch (e) {
      const msg = e.response?.data?.files?.[0] || e.response?.data?.pair_id?.[0] || e.response?.data?.detail || e.message;
      addLog({ level: "error", message: `Upload failed: ${msg}` });
      setBusy(false);
    }
  };

  const canUpload = files.length > 0 && pairId && date && !busy;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "22px", maxWidth: "660px" }}>
      <div>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" }}>
          Upload Excel Files
        </h2>
        <p style={{ ...body, fontSize: "13px", color: "var(--color-muted)", margin: 0, lineHeight: 1.6 }}>
          Select an active buyer–factory pair, set the inspection date, then upload one or many audit report Excel files.
          The pair determines which extractor and template are used.
        </p>
      </div>

      {/* Pair + date selectors */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
        <div>
          <Label required>BUYER–FACTORY PAIR</Label>
          <select
            value={pairId}
            onChange={e => setPairId(e.target.value)}
            style={{ ...fieldStyle }}
            disabled={busy}
          >
            <option value="">— Select pair —</option>
            {pairs.map(p => (
              <option key={p.id} value={p.id}>
                {p["buyer__name"]} × {p["factory__name"]} [{p.report_type}]
              </option>
            ))}
          </select>
          {selectedPair && (
            <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)", marginTop: "5px" }}>
              Allowed: {selectedPair.available_reports?.join(", ") || "—"}
            </div>
          )}
        </div>
        <div>
          <Label required>INSPECTION DATE</Label>
          <input
            type="date" value={date}
            onChange={e => setDate(e.target.value)}
            style={fieldStyle}
            disabled={busy}
          />
        </div>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDrag(true); }}
        onDragLeave={() => setIsDrag(false)}
        onDrop={onDrop}
        onClick={() => !busy && inputRef.current?.click()}
        style={{
          border: `2px dashed ${isDrag ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "10px", padding: "44px 24px", textAlign: "center",
          cursor: busy ? "not-allowed" : "pointer",
          background: isDrag ? "rgba(99,102,241,0.06)" : "var(--color-surface)",
          transition: "all 0.2s",
        }}
      >
        <input ref={inputRef} type="file" accept=".xlsx,.xls" multiple style={{ display: "none" }}
          onChange={e => { addFiles(e.target.files); e.target.value = ""; }} />
        <div style={{ fontSize: "30px", marginBottom: "10px" }}>📊</div>
        <div style={{ ...body, fontSize: "14px", color: "var(--color-text)", marginBottom: "6px" }}>
          Drag & drop Excel files here, or click to browse
        </div>
        <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>
          .xlsx and .xls · 50 MB per file max · Multiple files supported
        </div>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
          <SectionTitle>{files.length} FILE(S) SELECTED</SectionTitle>
          {files.map((f, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "7px 12px", background: "var(--color-surface)",
              borderRadius: "5px", border: "1px solid var(--color-border)",
            }}>
              <span style={{ ...mono, fontSize: "11px", color: "var(--color-accent2)" }}>📄 {f.name}</span>
              <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>
                  {(f.size / 1024).toFixed(0)} KB
                </span>
                {!busy && (
                  <button
                    onClick={e => { e.stopPropagation(); setFiles(prev => prev.filter((_, j) => j !== i)); }}
                    style={{ background: "none", border: "none", color: "var(--color-error)", cursor: "pointer", fontSize: "12px" }}
                  >✕</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Progress bar */}
      {progress && (
        <div style={{ background: "var(--color-surface)", borderRadius: "8px", padding: "14px", border: "1px solid var(--color-border)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
            <span style={{ ...mono, fontSize: "10px", color: "var(--color-accent2)" }}>{progress.stage}</span>
            <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>{progress.processed}/{progress.total}</span>
          </div>
          <div style={{ height: "4px", background: "var(--color-border)", borderRadius: "2px", overflow: "hidden" }}>
            <div style={{
              height: "100%", width: `${progress.percent}%`,
              background: progress.stage === "DONE" ? "var(--color-success)" : "var(--color-accent)",
              borderRadius: "2px", transition: "width 0.4s ease",
            }} />
          </div>
        </div>
      )}

      <PrimaryBtn onClick={handleUpload} disabled={!canUpload}>
        {busy ? "PROCESSING…" : "UPLOAD & EXTRACT"}
      </PrimaryBtn>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Batch list
// ─────────────────────────────────────────────────────────────────────────────
function AuditBatchList({ data, action, onAction }) {
  const batches = Array.isArray(data) ? data : (data?.results ?? []);
  const sorted  = [...batches].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <h2 style={{ ...disp, fontSize: "16px", fontWeight: 700, margin: "0 0 8px", color: "var(--color-text)" }}>
        Batches <span style={{ color: "var(--color-muted)", fontSize: "12px", fontWeight: 400 }}>({sorted.length})</span>
      </h2>

      {/* Column headers */}
      <div style={{
        display: "grid", gridTemplateColumns: "52px 1fr 90px 100px 90px 80px 96px",
        gap: "8px", padding: "4px 14px",
        ...mono, fontSize: "9px", letterSpacing: "0.08em", color: "var(--color-muted)",
      }}>
        <span>#</span>
        <span>PAIR / USER</span>
        <span>DATE</span>
        <span>STATUS</span>
        <span>FILES</span>
        <span>SUCCESS</span>
        <span style={{ textAlign: "right" }}>ACTIONS</span>
      </div>

      {sorted.length === 0 && (
        <div style={{ ...body, fontSize: "13px", color: "var(--color-muted)", padding: "32px 0", textAlign: "center" }}>
          No batches found.
        </div>
      )}

      {sorted.map(b => (
        <AuditBatchRow key={b.id} batch={b} action={action} onAction={onAction} />
      ))}
    </div>
  );
}

function AuditBatchRow({ batch, action, onAction }) {
  const color    = STATUS_COLOR[batch.status] || "var(--color-muted)";
  const total     = batch.total_files     ?? 0;
  const processed = batch.processed_files ?? 0;
  const failed    = batch.failed_files    ?? 0;
  const pairLabel = batch.pair
    ? `${batch.pair.buyer?.name ?? ""} × ${batch.pair.factory?.name ?? ""}`
    : batch.pair_display ?? `Pair #${batch.pair_id}`;
  const date = batch.inspection_date ?? "—";
  const hasErrors = batch.status === "PARTIAL" || batch.status === "FAILED";

  // When this list is rendered in "retry-download" context (from the sidebar),
  // row click downloads the error JSON directly instead of navigating to detail.
  const isRetryContext = action === "retry-download";
  const handleRowClick = () =>
    isRetryContext ? onAction("retry-download", batch.id) : onAction("view", batch.id);

  return (
    <div
      onClick={handleRowClick}
      style={{
        display: "grid", gridTemplateColumns: "52px 1fr 90px 100px 90px 80px 96px",
        gap: "8px", padding: "10px 14px",
        background: "var(--color-surface)", border: "1px solid var(--color-border)",
        borderLeft: `3px solid ${color}`, borderRadius: "7px",
        alignItems: "center", cursor: "pointer", transition: "border-color 0.15s",
      }}
      onMouseEnter={e => e.currentTarget.style.borderColor = "var(--color-accent)"}
      onMouseLeave={e => e.currentTarget.style.borderLeft = `3px solid ${color}`}
    >
      <span style={{ ...mono, fontSize: "11px", color: "var(--color-accent2)" }}>#{batch.id}</span>
      <div style={{ minWidth: 0 }}>
        <div style={{ ...body, fontSize: "12px", color: "var(--color-text)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {pairLabel}
        </div>
        {batch.created_by && (
          <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>by {batch.created_by.username}</div>
        )}
      </div>
      <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>{date}</span>
      <span style={{ ...mono, fontSize: "9px", color, background: `${color}18`, padding: "2px 7px", borderRadius: "3px", whiteSpace: "nowrap", display: "inline-block" }}>
        {batch.status}
      </span>
      <span style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>
        {processed}/{total}
        {failed > 0 && <span style={{ color: "var(--color-error)", marginLeft: "4px" }}>({failed}✕)</span>}
      </span>
      <span style={{ ...mono, fontSize: "11px", color: batch.success_rate === 100 ? "var(--color-success)" : "var(--color-warning)" }}>
        {batch.success_rate ?? "—"}%
      </span>
      <div style={{ display: "flex", gap: "4px", justifyContent: "flex-end" }} onClick={e => e.stopPropagation()}>
        {isRetryContext ? (
          /* In retry-download context: only show the download button */
          <IconBtn
            title={hasErrors ? "Download error JSON" : "No blocked records"}
            color={hasErrors ? "var(--color-warning)" : undefined}
            disabled={!hasErrors}
            onClick={() => onAction("retry-download", batch.id)}
          >⬇</IconBtn>
        ) : (
          <>
            <IconBtn title="View detail" onClick={() => onAction("view", batch.id)}>◎</IconBtn>
            <IconBtn title="Batch logs" onClick={() => onAction("logs", batch.id)}>∷</IconBtn>
            {hasErrors && (
              <IconBtn
                title="Download error JSON"
                color="var(--color-warning)"
                onClick={() => onAction("retry-download", batch.id)}
              >⬇</IconBtn>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function IconBtn({ children, onClick, title, color, disabled }) {
  return (
    <button onClick={onClick} title={title} disabled={disabled} style={{
      background: "transparent", border: "1px solid var(--color-border)",
      color: disabled ? "var(--color-muted)" : (color || "var(--color-muted)"),
      width: "28px", height: "28px", borderRadius: "5px",
      display: "flex", alignItems: "center", justifyContent: "center",
      cursor: disabled ? "not-allowed" : "pointer",
      fontSize: "13px", opacity: disabled ? 0.35 : 1, transition: "all 0.12s",
    }}
      onMouseEnter={e => { if (!disabled) e.currentTarget.style.background = "var(--color-panel)"; }}
      onMouseLeave={e => { if (!disabled) e.currentTarget.style.background = "transparent"; }}
    >
      {children}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Batch detail
// ─────────────────────────────────────────────────────────────────────────────
function AuditBatchDetail({ data }) {
  const color     = STATUS_COLOR[data?.status] || "var(--color-muted)";
  const total     = data?.total_files     ?? 0;
  const processed = data?.processed_files ?? 0;
  const failed    = data?.failed_files    ?? 0;
  const pairLabel = data?.pair
    ? `${data.pair.buyer?.name ?? ""} × ${data.pair.factory?.name ?? ""}`
    : `Pair #${data?.pair_id}`;

  const reports = data?.reports ?? [];

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: 0 }}>Batch #{data?.id}</h2>
        <span style={{ ...mono, fontSize: "11px", color, background: `${color}18`, padding: "2px 10px", borderRadius: "4px" }}>
          {data?.status}
        </span>
        {data?.created_by && (
          <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>
            by {data.created_by.username}
          </span>
        )}
      </div>

      {/* Meta */}
      <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
        {[
          ["Pair",    pairLabel],
          ["Date",    data?.inspection_date ?? "—"],
          ["Format",  data?.format_type ?? data?.pair?.report_type ?? "—"],
        ].map(([k, v]) => (
          <div key={k} style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>
            <span style={{ opacity: 0.6 }}>{k}: </span>
            <span style={{ color: "var(--color-text)" }}>{v}</span>
          </div>
        ))}
      </div>

      <StatGrid stats={[
        ["Total",     total],
        ["Processed", processed],
        ["Failed",    failed,  failed > 0 ? "var(--color-error)" : undefined],
        ["Success",   `${data?.success_rate ?? 0}%`, data?.success_rate === 100 ? "var(--color-success)" : "var(--color-warning)"],
      ]} />

      {/* Error log */}
      {data?.error_log && (
        <Card accent="var(--color-error)">
          <SectionTitle>ERROR LOG</SectionTitle>
          <pre style={{ ...mono, fontSize: "10px", color: "var(--color-muted)", whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.7, margin: 0 }}>
            {data.error_log}
          </pre>
        </Card>
      )}

      {/* Reports nested */}
      {reports.length > 0 && (
        <div>
          <SectionTitle>REPORTS ({reports.length})</SectionTitle>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {reports.map(r => (
              <div key={r.id} style={{
                display: "grid", gridTemplateColumns: "1fr 120px 120px 120px 80px",
                gap: "10px", padding: "9px 14px",
                background: "var(--color-surface)", border: "1px solid var(--color-border)",
                borderRadius: "5px", alignItems: "center",
              }}>
                <span style={{ ...mono, fontSize: "11px", color: "var(--color-accent2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r.factory || r.file_name}
                </span>
                <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>{r.style_no}</span>
                <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>{r.inspection_type}</span>
                <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>{r.date_of_issue}</span>
                <span style={{
                  ...mono, fontSize: "9px",
                  color: r.audit_result === "PASS" ? "var(--color-success)" : r.audit_result === "FAIL" ? "var(--color-error)" : "var(--color-muted)",
                }}>
                  {r.audit_result}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Batch logs view
// ─────────────────────────────────────────────────────────────────────────────
function AuditBatchLogsView({ data }) {
  const color = STATUS_COLOR[data?.status] || "var(--color-muted)";
  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
      <h2 style={{ ...disp, fontSize: "16px", fontWeight: 700, margin: 0 }}>
        Batch #{data?.id} · Logs
      </h2>
      <StatGrid stats={[
        ["Status",    data?.status,         color],
        ["Total",     data?.total_files],
        ["Processed", data?.processed_files],
        ["Failed",    data?.failed_files,   data?.failed_files > 0 ? "var(--color-error)" : undefined],
      ]} />
      {data?.error_log ? (
        <Card accent="var(--color-error)">
          <SectionTitle>RAW ERROR LOG</SectionTitle>
          <pre style={{ ...mono, fontSize: "10px", color: "var(--color-muted)", whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.7, margin: 0 }}>
            {data.error_log}
          </pre>
        </Card>
      ) : (
        <div style={{ ...mono, fontSize: "11px", color: "var(--color-success)", padding: "8px 0" }}>
          ✓ No errors — all files processed successfully
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Export view
// ─────────────────────────────────────────────────────────────────────────────
function ExportView({ data }) {
  const { addLog } = useOutputStore();
  const options   = data?.options ?? {};
  const [form, setForm] = useState({ factory: "", client: "", date_from: "", date_to: "", style: "", po: "" });
  const [exporting, setExporting] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const canExport = form.factory && form.client && form.date_from && form.date_to;

  const handleExport = async () => {
    if (!canExport || exporting) return;
    setExporting(true);
    addLog({ level: "info", message: `Generating summary for ${form.factory} / ${form.client}…` });
    try {
      const params = {
        factory: form.factory, client: form.client,
        date_from: form.date_from, date_to: form.date_to,
        ...(form.style && { style: form.style }),
        ...(form.po    && { po: form.po }),
      };
      const { blob, headers } = await downloadSummary(params);
      const cd   = headers["content-disposition"] || "";
      const name = cd.match(/filename[^;=\n]*=['"]?([^'"\n]+)['"]?/)?.[1] || "audit_summary.xlsx";
      saveBlob(blob, name);
      addLog({ level: "success", message: `Downloaded: ${name}` });
    } catch (e) {
      const err = e.response?.data;
      // err may be a Blob (responseType mismatch) or JSON
      if (err instanceof Blob) {
        const text = await err.text();
        try { addLog({ level: "error", message: `Export failed: ${JSON.parse(text)?.detail}` }); }
        catch { addLog({ level: "error", message: `Export failed: ${text}` }); }
      } else {
        addLog({ level: "error", message: `Export failed: ${err?.detail || e.message}` });
      }
    } finally {
      setExporting(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "22px", maxWidth: "660px" }}>
      <div>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" }}>
          Download Summary
        </h2>
        <p style={{ ...body, fontSize: "13px", color: "var(--color-muted)", margin: 0, lineHeight: 1.6 }}>
          Filter by factory, buyer, and date range to generate a grouped Excel summary with defect analysis.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
        <div>
          <Label required>FACTORY</Label>
          <input type="text" value={form.factory} placeholder="Type or select…"
            onChange={e => set("factory", e.target.value)} style={fieldStyle} list="ex-factory-opts" />
          <datalist id="ex-factory-opts">
            {(options.factories ?? []).map(f => <option key={f} value={f} />)}
          </datalist>
        </div>
        <div>
          <Label required>BUYER / CLIENT</Label>
          <input type="text" value={form.client} placeholder="Type or select…"
            onChange={e => set("client", e.target.value)} style={fieldStyle} list="ex-client-opts" />
          <datalist id="ex-client-opts">
            {(options.clients ?? []).map(c => <option key={c} value={c} />)}
          </datalist>
        </div>
        <div>
          <Label required>DATE FROM</Label>
          <input type="date" value={form.date_from}
            min={options.min_date || ""} max={form.date_to || options.max_date || ""}
            onChange={e => set("date_from", e.target.value)} style={fieldStyle} />
        </div>
        <div>
          <Label required>DATE TO</Label>
          <input type="date" value={form.date_to}
            min={form.date_from || options.min_date || ""} max={options.max_date || ""}
            onChange={e => set("date_to", e.target.value)} style={fieldStyle} />
        </div>
      </div>

      {/* Optional filters */}
      <div>
        <SectionTitle>OPTIONAL FILTERS</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
          <div>
            <Label>STYLE NO</Label>
            <input type="text" value={form.style} placeholder="Partial match…"
              onChange={e => set("style", e.target.value)} style={fieldStyle} list="ex-style-opts" />
            <datalist id="ex-style-opts">
              {(options.styles ?? []).slice(0, 100).map(s => <option key={s} value={s} />)}
            </datalist>
          </div>
          <div>
            <Label>PO NUMBER</Label>
            <input type="text" value={form.po} placeholder="Partial match…"
              onChange={e => set("po", e.target.value)} style={fieldStyle} list="ex-po-opts" />
            <datalist id="ex-po-opts">
              {(options.po_numbers ?? []).slice(0, 100).map(p => <option key={p} value={p} />)}
            </datalist>
          </div>
        </div>
      </div>

      {/* Query preview */}
      {canExport && (
        <Card>
          <SectionTitle>EXPORT QUERY</SectionTitle>
          <div style={{ ...mono, fontSize: "11px", color: "var(--color-text)", lineHeight: 1.9 }}>
            Factory: <span style={{ color: "var(--color-accent2)" }}>{form.factory}</span><br />
            Buyer: <span style={{ color: "var(--color-accent2)" }}>{form.client}</span><br />
            Period: <span style={{ color: "var(--color-accent2)" }}>{form.date_from} → {form.date_to}</span>
            {form.style && <><br />Style: <span style={{ color: "var(--color-accent2)" }}>{form.style}</span></>}
            {form.po    && <><br />PO: <span style={{ color: "var(--color-accent2)" }}>{form.po}</span></>}
          </div>
        </Card>
      )}

      <PrimaryBtn onClick={handleExport} disabled={!canExport || exporting}>
        {exporting ? "GENERATING…" : "⬇  DOWNLOAD EXCEL SUMMARY"}
      </PrimaryBtn>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Small helper: download error JSON for a single batch_id
// Used inside RetrySearchView results so user can act immediately.
// ─────────────────────────────────────────────────────────────────────────────
function DownloadErrBtn({ batchId, addLog }) {
  const [busy, setBusy] = useState(false);

  const handleDownload = async (e) => {
    e.stopPropagation();
    if (busy) return;
    setBusy(true);
    addLog({ level: "info", message: `Downloading error JSON for Batch #${batchId}…` });
    try {
      const payload = await downloadErrorJson(batchId);
      const blob    = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      saveBlob(blob, `batch-${batchId}-errors.json`);
      addLog({ level: "success", message: `Error JSON downloaded for Batch #${batchId}` });
    } catch (err) {
      addLog({ level: "error", message: `Download failed: ${err.response?.data?.detail || err.message}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={handleDownload}
      disabled={busy}
      title={`Download error JSON for Batch #${batchId}`}
      style={{
        background: busy ? "var(--color-border)" : "rgba(245,158,11,0.1)",
        border: "1px solid rgba(245,158,11,0.3)",
        color: busy ? "var(--color-muted)" : "var(--color-warning)",
        padding: "5px 12px", borderRadius: "5px",
        ...mono, fontSize: "10px", cursor: busy ? "not-allowed" : "pointer",
        whiteSpace: "nowrap", flexShrink: 0, transition: "all 0.15s",
      }}
    >
      {busy ? "…" : `⬇ Batch #${batchId}`}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Retry — search blocked records
// ─────────────────────────────────────────────────────────────────────────────
function RetrySearchView() {
  const { addLog } = useOutputStore();
  const [date,    setDate]    = useState("");
  const [style,   setStyle]   = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    setLoading(true);
    addLog({ level: "info", message: "Searching blocked records…" });
    try {
      const params = {};
      if (date)  params.date  = date;
      if (style) params.style = style;
      const data = await searchBlocked(params);
      setResults(data);
      addLog({ level: "success", message: `Found ${data.count} blocked record(s)` });
    } catch (e) {
      addLog({ level: "error", message: `Search failed: ${e.message}` });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "22px", maxWidth: "720px" }}>
      <div>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" }}>Search Blocked Records</h2>
        <p style={{ ...body, fontSize: "13px", color: "var(--color-muted)", margin: 0, lineHeight: 1.6 }}>
          Find records that failed validation. Download the error JSON for the relevant batch, fix the fields, then re-upload via <strong>Upload Fixed JSON</strong>.
        </p>
      </div>

      <div style={{ display: "flex", gap: "12px", alignItems: "flex-end", flexWrap: "wrap" }}>
        <div>
          <Label>DATE</Label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} style={{ ...fieldStyle, width: "180px" }} />
        </div>
        <div>
          <Label>STYLE NO</Label>
          <input type="text" value={style} placeholder="Partial match…" onChange={e => setStyle(e.target.value)} style={{ ...fieldStyle, width: "200px" }} />
        </div>
        <PrimaryBtn onClick={handleSearch} disabled={loading}>
          {loading ? "SEARCHING…" : "⌕  SEARCH"}
        </PrimaryBtn>
      </div>

      {results && (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <SectionTitle>{results.count} RESULT(S)</SectionTitle>
          {results.records.length === 0 && (
            <div style={{ ...mono, fontSize: "11px", color: "var(--color-success)" }}>✓ No blocked records found.</div>
          )}
          {results.records.map((r, i) => (
            <Card key={i} accent="var(--color-error)">
              <div style={{ display: "flex", gap: "12px", alignItems: "flex-start", flexWrap: "wrap" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ ...mono, fontSize: "11px", color: "var(--color-accent2)", marginBottom: "4px" }}>
                    📄 {r.file_name}
                  </div>
                  <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)", marginBottom: "6px" }}>
                    Batch #{r.batch_id} · {r.factory} · {r.style_no} · {r.date_of_issue}
                  </div>
                  {r.blocking_errors.map((err, j) => (
                    <div key={j} style={{ ...body, fontSize: "11px", color: "var(--color-error)", lineHeight: 1.5 }}>⚠ {err}</div>
                  ))}
                  {r.cross_check_warnings?.map((w, j) => (
                    <div key={j} style={{ ...body, fontSize: "11px", color: "var(--color-warning)", lineHeight: 1.5, marginTop: "2px" }}>⚡ {w}</div>
                  ))}
                </div>
                {/* Download error JSON for this batch directly from the search result */}
                <DownloadErrBtn batchId={r.batch_id} addLog={addLog} />
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Retry — upload fixed JSON
// ─────────────────────────────────────────────────────────────────────────────
function RetryUploadView() {
  const { addLog } = useOutputStore();
  const [batchId,  setBatchId]  = useState("");
  const [file,     setFile]     = useState(null);
  const [result,   setResult]   = useState(null);
  const [busy,     setBusy]     = useState(false);
  const [isDrag,   setIsDrag]   = useState(false);
  const fileInputRef = useRef(null);

  const pickFile = (f) => {
    if (!f) return;
    if (!f.name.endsWith(".json")) {
      addLog({ level: "error", message: "Only .json files are accepted." });
      return;
    }
    setFile(f);
    setResult(null);

    // Auto-detect batch_id: first try reading the JSON content (most reliable),
    // then fall back to parsing the filename e.g. batch-42-errors.json
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target.result);
        if (parsed.batch_id) {
          setBatchId(String(parsed.batch_id));
          return;
        }
      } catch {}
      // Filename fallback
      const m = f.name.match(/batch[-_](\d+)/i);
      if (m) setBatchId(m[1]);
    };
    reader.readAsText(f);
  };

  const handleDrop = (e) => {
    e.preventDefault(); setIsDrag(false);
    pickFile(e.dataTransfer.files?.[0]);
  };

  const handleSubmit = async () => {
    if (!batchId || !file || busy) return;
    setBusy(true);
    addLog({ level: "info", message: `Uploading fixed JSON for Batch #${batchId}…` });
    try {
      const res = await uploadFixedJson(parseInt(batchId, 10), file);
      setResult(res);
      if (res.saved > 0)
        addLog({ level: "success", message: `${res.saved}/${res.submitted} record(s) saved to DB` });
      if (res.still_blocked?.length > 0)
        addLog({ level: "warning", message: `${res.still_blocked.length} record(s) still blocked` });
    } catch (e) {
      addLog({ level: "error", message: `Upload failed: ${e.response?.data?.detail || e.message}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "22px", maxWidth: "600px" }}>
      <div>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" }}>Upload Fixed JSON</h2>
        <p style={{ ...body, fontSize: "13px", color: "var(--color-muted)", margin: 0, lineHeight: 1.6 }}>
          Download the error JSON from <strong>Retry › Download Error JSON</strong>, fix the fields, then upload the corrected file here.
        </p>
      </div>

      <div>
        <Label required>BATCH ID</Label>
        <input type="number" value={batchId} placeholder="e.g. 42"
          onChange={e => setBatchId(e.target.value)} style={{ ...fieldStyle, width: "200px" }} />
      </div>

      {/* JSON drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setIsDrag(true); }}
        onDragLeave={() => setIsDrag(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${isDrag ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "10px", padding: "36px 24px", textAlign: "center",
          cursor: "pointer", background: isDrag ? "rgba(99,102,241,0.06)" : "var(--color-surface)",
          transition: "all 0.2s",
        }}
      >
        <input ref={fileInputRef} type="file" accept=".json" style={{ display: "none" }}
          onChange={e => { pickFile(e.target.files?.[0]); e.target.value = ""; }} />
        <div style={{ fontSize: "28px", marginBottom: "10px" }}>📂</div>
        {file ? (
          <>
            <div style={{ ...mono, fontSize: "12px", color: "var(--color-accent2)", marginBottom: "4px" }}>📄 {file.name}</div>
            <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>
              {(file.size / 1024).toFixed(0)} KB · click to change
            </div>
          </>
        ) : (
          <>
            <div style={{ ...body, fontSize: "13px", color: "var(--color-text)", marginBottom: "6px" }}>
              Drag & drop fixed JSON file here, or click to browse
            </div>
            <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>.json · downloaded from Retry › Download Error JSON</div>
          </>
        )}
      </div>

      {/* Result banner */}
      {result && (
        <Card accent={result.still_blocked?.length === 0 ? "var(--color-success)" : "var(--color-warning)"}>
          <div style={{ ...mono, fontSize: "11px", color: result.still_blocked?.length === 0 ? "var(--color-success)" : "var(--color-warning)", lineHeight: 1.8 }}>
            Submitted: {result.submitted} · Saved: {result.saved} · Still blocked: {result.still_blocked?.length ?? 0}
          </div>
          {result.still_blocked?.length > 0 && (
            <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "4px" }}>
              {result.still_blocked.map((r, i) => (
                <div key={i} style={{ ...body, fontSize: "11px", color: "var(--color-error)" }}>
                  ⚠ {r.file_name}: {Array.isArray(r.blocking_errors) ? r.blocking_errors.join("; ") : r.blocking_errors}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      <PrimaryBtn onClick={handleSubmit} disabled={!batchId || !file || busy}>
        {busy ? "UPLOADING…" : "↺  SUBMIT FIXED RECORDS"}
      </PrimaryBtn>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Settings views (Buyers / Factories / Pairs)
// ─────────────────────────────────────────────────────────────────────────────
function SettingsView({ data, settingsKey }) {
  const records = Array.isArray(data) ? data : (data?.results ?? []);
  const titles  = { buyers: "Buyers", factories: "Factories", pairs: "Buyer–Factory Pairs" };

  const renderRecord = (r) => {
    if (settingsKey === "buyers") {
      return (
        <div key={r.id} style={{ display: "grid", gridTemplateColumns: "1fr 80px 80px", gap: "10px", alignItems: "center" }}>
          <span style={{ ...body, fontSize: "12px", color: "var(--color-text)" }}>{r.name}</span>
          <span style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>{r.code}</span>
          <span style={{ ...mono, fontSize: "9px", color: r.is_active ? "var(--color-success)" : "var(--color-error)", background: r.is_active ? "rgba(34,211,160,0.1)" : "rgba(244,63,94,0.1)", padding: "2px 7px", borderRadius: "3px", textAlign: "center" }}>
            {r.is_active ? "ACTIVE" : "INACTIVE"}
          </span>
        </div>
      );
    }
    if (settingsKey === "factories") {
      return (
        <div key={r.id} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 80px 80px", gap: "10px", alignItems: "center" }}>
          <span style={{ ...body, fontSize: "12px", color: "var(--color-text)" }}>{r.name}</span>
          <span style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>{r.buyer_name ?? `Buyer #${r.buyer}`}</span>
          <span style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>{r.code}</span>
          <span style={{ ...mono, fontSize: "9px", color: r.is_active ? "var(--color-success)" : "var(--color-error)", background: r.is_active ? "rgba(34,211,160,0.1)" : "rgba(244,63,94,0.1)", padding: "2px 7px", borderRadius: "3px", textAlign: "center" }}>
            {r.is_active ? "ACTIVE" : "INACTIVE"}
          </span>
        </div>
      );
    }
    // pairs
    return (
      <div key={r.id} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 100px auto", gap: "10px", alignItems: "center" }}>
        <span style={{ ...body, fontSize: "12px", color: "var(--color-text)" }}>{r.buyer_name ?? `Buyer #${r.buyer}`}</span>
        <span style={{ ...body, fontSize: "12px", color: "var(--color-text)" }}>{r.factory_name ?? `Factory #${r.factory}`}</span>
        <span style={{ ...mono, fontSize: "10px", color: "var(--color-accent2)", background: "rgba(99,102,241,0.1)", padding: "2px 7px", borderRadius: "3px", textAlign: "center" }}>
          {r.report_type}
        </span>
        <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
          {(r.available_reports ?? []).map(ar => (
            <span key={ar} style={{ ...mono, fontSize: "9px", color: "var(--color-muted)", background: "var(--color-panel)", border: "1px solid var(--color-border)", padding: "1px 5px", borderRadius: "3px" }}>
              {ar}
            </span>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <h2 style={{ ...disp, fontSize: "18px", fontWeight: 700, margin: 0, color: "var(--color-text)" }}>
          {titles[settingsKey]}
        </h2>
        <span style={{ ...mono, fontSize: "11px", color: "var(--color-muted)" }}>
          ({records.length} record{records.length !== 1 ? "s" : ""})
        </span>
      </div>
      <div style={{ ...mono, fontSize: "11px", color: "var(--color-muted)", background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.2)", borderRadius: "7px", padding: "10px 14px" }}>
        ⚙ Registration is managed via the Django admin or API. This view is read-only.
        To add or edit records go to <strong>/admin/</strong>.
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        {records.map((r, i) => (
          <div key={r.id ?? i} style={{
            padding: "10px 14px", background: "var(--color-surface)",
            border: "1px solid var(--color-border)", borderRadius: "6px",
          }}>
            {renderRecord(r)}
          </div>
        ))}
        {records.length === 0 && (
          <div style={{ ...body, fontSize: "13px", color: "var(--color-muted)", padding: "24px 0", textAlign: "center" }}>
            No records found.
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Router — dispatches to the right view based on output.type
// ─────────────────────────────────────────────────────────────────────────────
export default function AuditOutput({ output }) {
  const { setOutput, setLoading, addLog } = useOutputStore();

  // Shared action handler used by batch lists
  const handleAction = async (action, id, meta = {}) => {
    switch (action) {
      case "view": {
        setLoading(true);
        try {
          const data = await fetchBatch(id);
          setOutput("audit-batch", data, `Batch #${id}`, { source: "audit" });
          addLog({ level: "info", message: `Loaded Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load Batch #${id}` });
          setLoading(false);
        }
        break;
      }
      case "logs": {
        setLoading(true);
        try {
          const data = await fetchBatch(id);
          setOutput("audit-batch-logs", data, `Logs · Batch #${id}`, { source: "audit" });
          addLog({ level: "info", message: `Logs loaded for Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load logs for Batch #${id}` });
          setLoading(false);
        }
        break;
      }
      case "retry-download": {
        addLog({ level: "info", message: `Downloading error JSON for Batch #${id}…` });
        try {
          const payload = await downloadErrorJson(id);
          const blob    = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
          saveBlob(blob, `batch-${id}-errors.json`);
          addLog({ level: "success", message: `Error JSON downloaded for Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Download failed: ${e.response?.data?.detail || e.message}` });
        }
        break;
      }
      default:
        break;
    }
  };

  switch (output.type) {
    case "audit-upload":
      return <UploadView data={output.data} />;

    case "audit-batch-list":
      return (
        <AuditBatchList
          data={output.data}
          action={output.action}
          onAction={handleAction}
        />
      );

    case "audit-batch":
      return <AuditBatchDetail data={output.data} />;

    case "audit-batch-logs":
      return <AuditBatchLogsView data={output.data} />;

    case "audit-export":
      return <ExportView data={output.data} />;

    case "audit-retry-search":
      return <RetrySearchView />;

    case "audit-retry-upload":
      return <RetryUploadView />;

    case "audit-settings":
      return <SettingsView data={output.data} settingsKey={output.settingsKey} />;

    default:
      return null;
  }
}