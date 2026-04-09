import { useState, useCallback, useEffect, useRef } from "react";
import { useAuthStore } from "../store/authStore";
import TopNav from "../components/layout/TopNav";
import LogsPanel from "../components/layout/LogsPanel";
import { useOutputStore } from "../store/outputStore";

// ── API helpers ───────────────────────────────────────────────────────────────
const BASE = "/api/audit";

async function apiFetch(path, opts = {}) {
  const token = useAuthStore.getState().access;
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { Authorization: `Bearer ${token}`, ...(opts.headers || {}) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res;
}

async function apiJson(path, opts = {}) {
  const res = await apiFetch(path, opts);
  return res.json();
}

// ── WS hook for audit batches ─────────────────────────────────────────────────
function useAuditWs(batchId, { onProgress, onComplete, onError } = {}) {
  const wsRef  = useRef(null);
  const cbsRef = useRef({ onProgress, onComplete, onError });
  useEffect(() => { cbsRef.current = { onProgress, onComplete, onError }; });

  useEffect(() => {
    if (!batchId) return;
    const token = useAuthStore.getState().access;
    if (!token)  return;
    let cancelled = false;

    const url = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/audit-batches/${batchId}/progress/?token=${token}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      if (cancelled) return;
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.event === "progress") cbsRef.current.onProgress?.(msg);
      if (msg.event === "complete") { cbsRef.current.onComplete?.(msg); ws.close(1000); }
      if (msg.event === "error")    cbsRef.current.onError?.(msg);
    };
    ws.onclose = () => {};
    ws.onerror = () => ws.close();

    return () => {
      cancelled = true;
      if (ws.readyState === WebSocket.OPEN) ws.close(1000);
    };
  }, [batchId]);
}

// ── Stage 1: Upload ───────────────────────────────────────────────────────────
function UploadStage({ onComplete }) {
  const { addLog } = useOutputStore();
  const [files, setFiles]       = useState([]);
  const [isDragOver, setIsDrag] = useState(false);
  const [batchId, setBatchId]   = useState(null);
  const [progress, setProgress] = useState(null);
  const [busy, setBusy]         = useState(false);
  const inputRef = useRef(null);

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
    onComplete: (msg) => {
      setProgress({ processed: msg.processed, total: msg.total, percent: 100, stage: "DONE" });
      addLog({ level: "success", message: `Batch #${msg.batch_id} complete — ${msg.report_count} records saved` });
      setBusy(false);
      onComplete(msg.batch_id, msg.report_count);
    },
    onError: (msg) => {
      addLog({ level: "error", message: `Batch error: ${msg.error_message}` });
      setBusy(false); setProgress(null); setBatchId(null);
    },
  });

  const handleUpload = async () => {
    if (!files.length || busy) return;
    setBusy(true);
    addLog({ level: "info", message: `Uploading ${files.length} Excel file(s)…` });
    try {
      const fd = new FormData();
      files.forEach(f => fd.append("files", f));
      const res = await apiFetch("/upload/", { method: "POST", body: fd });
      const data = await res.json();
      setBatchId(data.batch_id);
      setProgress({ processed: 0, total: data.total_files, percent: 0, stage: "QUEUED" });
      addLog({ level: "success", message: `Batch #${data.batch_id} created — ${data.total_files} files queued` });
    } catch (e) {
      addLog({ level: "error", message: `Upload failed: ${e.message}` });
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px", maxWidth: "640px" }}>
      <div>
        <h2 style={hdr}>Stage 1 — Upload Excel Files</h2>
        <p style={sub}>Upload one or many audit report Excel files (.xlsx / .xls). Data is extracted and saved to the database.</p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDrag(true); }}
        onDragLeave={() => setIsDrag(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${isDragOver ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "10px", padding: "48px 24px", textAlign: "center", cursor: "pointer",
          background: isDragOver ? "rgba(99,102,241,0.06)" : "var(--color-surface)",
          transition: "all 0.2s",
        }}
      >
        <input ref={inputRef} type="file" accept=".xlsx,.xls" multiple style={{ display: "none" }}
          onChange={(e) => addFiles(e.target.files)} />
        <div style={{ fontSize: "32px", marginBottom: "12px" }}>📊</div>
        <div style={{ fontFamily: "var(--font-body)", fontSize: "14px", color: "var(--color-text)", marginBottom: "6px" }}>
          Drag & drop Excel files here, or click to browse
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
          .xlsx and .xls · 50 MB per file max · Multiple files supported
        </div>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "4px" }}>
            {files.length} FILE(S) SELECTED
          </div>
          {files.map((f, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "7px 12px", background: "var(--color-surface)",
              borderRadius: "5px", border: "1px solid var(--color-border)",
            }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)" }}>
                📄 {f.name}
              </span>
              <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
                  {(f.size / 1024).toFixed(0)} KB
                </span>
                {!busy && (
                  <button onClick={(e) => { e.stopPropagation(); setFiles(prev => prev.filter((_, j) => j !== i)); }}
                    style={{ background: "none", border: "none", color: "var(--color-error)", cursor: "pointer", fontSize: "12px" }}>
                    ✕
                  </button>
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
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-accent2)" }}>{progress.stage}</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
              {progress.processed}/{progress.total}
            </span>
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

      <button onClick={handleUpload} disabled={!files.length || busy} style={{
        background: files.length && !busy ? "var(--color-accent)" : "var(--color-border)",
        color: files.length && !busy ? "#fff" : "var(--color-muted)",
        border: "none", padding: "11px 28px", borderRadius: "6px",
        fontFamily: "var(--font-display)", fontSize: "13px", fontWeight: 600,
        letterSpacing: "0.06em", cursor: files.length && !busy ? "pointer" : "not-allowed",
        alignSelf: "flex-start", transition: "all 0.15s",
      }}>
        {busy ? "PROCESSING…" : "UPLOAD & EXTRACT"}
      </button>
    </div>
  );
}

// ── Stage 2: Export ───────────────────────────────────────────────────────────
function ExportStage({ lastBatchId, lastCount }) {
  const { addLog } = useOutputStore();
  const [options, setOptions]   = useState(null);
  const [loading, setLoading]   = useState(false);
  const [exporting, setExport]  = useState(false);
  const [form, setForm]         = useState({
    factory: "", client: "", date_from: "", date_to: "", style: "", po: "",
  });

  useEffect(() => {
    setLoading(true);
    apiJson("/options/")
      .then(data => { setOptions(data); setLoading(false); })
      .catch(e  => { addLog({ level: "error", message: `Options load failed: ${e.message}` }); setLoading(false); });
  }, [lastBatchId]); // reload when a new batch finishes

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const canExport = form.factory && form.client && form.date_from && form.date_to;

  const handleExport = async () => {
    if (!canExport || exporting) return;
    setExport(true);
    addLog({ level: "info", message: `Generating summary for ${form.factory} / ${form.client}…` });

    try {
      const params = new URLSearchParams({
        factory:   form.factory,
        client:    form.client,
        date_from: form.date_from,
        date_to:   form.date_to,
        ...(form.style && { style: form.style }),
        ...(form.po    && { po: form.po }),
      });
      const res = await apiFetch(`/export/?${params}`);
      const blob = await res.blob();
      const cd   = res.headers.get("Content-Disposition") || "";
      const name = cd.match(/filename="?([^"]+)"?/)?.[1] || "audit_summary.xlsx";
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = name; a.click();
      URL.revokeObjectURL(url);
      addLog({ level: "success", message: `Downloaded: ${name}` });
    } catch (e) {
      addLog({ level: "error", message: `Export failed: ${e.message}` });
    } finally {
      setExport(false);
    }
  };

  const fieldStyle = {
    width: "100%", padding: "9px 12px",
    background: "var(--color-panel)", border: "1px solid var(--color-border)",
    borderRadius: "6px", color: "var(--color-text)",
    fontFamily: "var(--font-mono)", fontSize: "12px", outline: "none",
  };

  const Label = ({ children }) => (
    <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "5px" }}>
      {children}
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px", maxWidth: "640px" }}>
      <div>
        <h2 style={hdr}>Stage 2 — Download Summary</h2>
        <p style={sub}>Filter by factory, buyer, and date range to generate a grouped Excel summary with defect analysis charts.</p>
      </div>

      {lastBatchId && (
        <div style={{ background: "rgba(34,211,160,0.08)", border: "1px solid rgba(34,211,160,0.2)", borderRadius: "7px", padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-success)" }}>
          ✓ Batch #{lastBatchId} saved {lastCount} record(s) to the database. Filter below to export.
        </div>
      )}

      {loading ? (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-muted)", padding: "20px 0" }}>
          Loading filter options…
        </div>
      ) : options && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>

          {/* Required fields */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <Label>FACTORY *</Label>
              <select value={form.factory} onChange={e => set("factory", e.target.value)} style={fieldStyle}>
                <option value="">Select factory…</option>
                {options.factories.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
            <div>
              <Label>BUYER / CLIENT *</Label>
              <select value={form.client} onChange={e => set("client", e.target.value)} style={fieldStyle}>
                <option value="">Select buyer…</option>
                {options.clients.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <Label>DATE FROM *</Label>
              <input type="date" value={form.date_from} min={options.min_date || ""} max={form.date_to || options.max_date || ""}
                onChange={e => set("date_from", e.target.value)} style={fieldStyle} />
            </div>
            <div>
              <Label>DATE TO *</Label>
              <input type="date" value={form.date_to} min={form.date_from || options.min_date || ""} max={options.max_date || ""}
                onChange={e => set("date_to", e.target.value)} style={fieldStyle} />
            </div>
          </div>

          {/* Optional filters */}
          <div style={{ borderTop: "1px solid var(--color-border)", paddingTop: "16px" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "12px" }}>
              OPTIONAL FILTERS
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <div>
                <Label>STYLE NO</Label>
                <input type="text" value={form.style} placeholder="Partial match…"
                  onChange={e => set("style", e.target.value)} style={fieldStyle} list="style-opts" />
                <datalist id="style-opts">
                  {options.styles.slice(0, 100).map(s => <option key={s} value={s} />)}
                </datalist>
              </div>
              <div>
                <Label>PO NUMBER</Label>
                <input type="text" value={form.po} placeholder="Partial match…"
                  onChange={e => set("po", e.target.value)} style={fieldStyle} list="po-opts" />
                <datalist id="po-opts">
                  {options.po_numbers.slice(0, 100).map(p => <option key={p} value={p} />)}
                </datalist>
              </div>
            </div>
          </div>

          {/* Summary + button */}
          {canExport && (
            <div style={{ background: "var(--color-surface)", borderRadius: "7px", padding: "12px 16px", border: "1px solid var(--color-border)" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", marginBottom: "6px" }}>EXPORT QUERY</div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text)", lineHeight: 1.7 }}>
                Factory: <span style={{ color: "var(--color-accent2)" }}>{form.factory}</span><br />
                Buyer: <span style={{ color: "var(--color-accent2)" }}>{form.client}</span><br />
                Period: <span style={{ color: "var(--color-accent2)" }}>{form.date_from} → {form.date_to}</span>
                {form.style && <><br />Style: <span style={{ color: "var(--color-accent2)" }}>{form.style}</span></>}
                {form.po    && <><br />PO: <span style={{ color: "var(--color-accent2)" }}>{form.po}</span></>}
              </div>
            </div>
          )}

          <button onClick={handleExport} disabled={!canExport || exporting} style={{
            background: canExport && !exporting ? "var(--color-success)" : "var(--color-border)",
            color: canExport && !exporting ? "#fff" : "var(--color-muted)",
            border: "none", padding: "11px 28px", borderRadius: "6px",
            fontFamily: "var(--font-display)", fontSize: "13px", fontWeight: 600,
            letterSpacing: "0.06em", cursor: canExport && !exporting ? "pointer" : "not-allowed",
            alignSelf: "flex-start", transition: "all 0.15s",
            display: "flex", alignItems: "center", gap: "8px",
          }}>
            {exporting ? "GENERATING…" : "⬇ DOWNLOAD EXCEL SUMMARY"}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Batch history sidebar ─────────────────────────────────────────────────────
function BatchHistory({ refreshKey }) {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    apiJson("/batches/")
      .then(data => { setBatches(data.results || data); setLoading(false); })
      .catch(() => setLoading(false));
  }, [refreshKey]);

  const STATUS_COLOR = {
    COMPLETED: "var(--color-success)", PARTIAL: "var(--color-warning)",
    FAILED: "var(--color-error)",      PROCESSING: "var(--color-accent2)", PENDING: "var(--color-muted)",
  };

  return (
    <div style={{ width: "260px", minWidth: "260px", background: "var(--color-surface)", borderLeft: "1px solid var(--color-border)", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--color-border)" }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", letterSpacing: "0.1em", color: "var(--color-muted)" }}>
          UPLOAD HISTORY
        </span>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "8px" }}>
        {loading && <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", padding: "16px 8px" }}>Loading…</div>}
        {!loading && batches.length === 0 && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", padding: "16px 8px", lineHeight: 1.8 }}>
            No batches yet.<br /><span style={{ opacity: 0.5 }}>Upload Excel files to begin.</span>
          </div>
        )}
        {batches.map(b => (
          <div key={b.id} style={{
            padding: "9px 12px", marginBottom: "4px",
            background: "var(--color-panel)", borderRadius: "6px",
            border: `1px solid var(--color-border)`,
            borderLeft: `3px solid ${STATUS_COLOR[b.status] || "var(--color-muted)"}`,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-accent2)" }}>#{b.id}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: STATUS_COLOR[b.status], background: `${STATUS_COLOR[b.status]}18`, padding: "1px 6px", borderRadius: "3px" }}>
                {b.status}
              </span>
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)" }}>
              {b.processed_files}/{b.total_files} files · {b.report_count || 0} records
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", marginTop: "2px" }}>
              {new Date(b.created_at).toLocaleDateString()}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Shared styles ─────────────────────────────────────────────────────────────
const hdr = { fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" };
const sub = { fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-muted)", margin: 0, lineHeight: 1.6 };

// ── Stage tab ─────────────────────────────────────────────────────────────────
function StageTab({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      background: active ? "var(--color-accent)" : "transparent",
      color: active ? "#fff" : "var(--color-muted)",
      border: "none", padding: "6px 18px", borderRadius: "5px",
      fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 500,
      letterSpacing: "0.08em", cursor: "pointer", transition: "all 0.15s",
    }}>
      {label}
    </button>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function FinalSummaryPage() {
  const [stage, setStage]       = useState("upload");    // "upload" | "export"
  const [lastBatchId, setLast]  = useState(null);
  const [lastCount, setCount]   = useState(0);
  const [historyKey, setHistKey] = useState(0);

  const handleBatchComplete = (batchId, reportCount) => {
    setLast(batchId);
    setCount(reportCount);
    setHistKey(k => k + 1);
    setStage("export");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <TopNav />
      <div style={{ display: "flex", flex: 1, overflow: "hidden", paddingTop: "52px" }}>
        <LogsPanel />

        {/* Main content */}
        <main style={{ flex: 1, background: "var(--color-bg)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Toolbar */}
          <div style={{ height: "44px", background: "var(--color-surface)", borderBottom: "1px solid var(--color-border)", display: "flex", alignItems: "center", padding: "0 16px", gap: "8px" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.1em", marginRight: "8px" }}>
              AUDIT SUMMARY
            </span>
            <StageTab label="1 · UPLOAD"   active={stage === "upload"} onClick={() => setStage("upload")} />
            <StageTab label="2 · EXPORT"   active={stage === "export"} onClick={() => setStage("export")} />
          </div>

          {/* Stage content */}
          <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px" }}>
            <div className="fade-up" key={stage}>
              {stage === "upload" && <UploadStage onComplete={handleBatchComplete} />}
              {stage === "export" && <ExportStage lastBatchId={lastBatchId} lastCount={lastCount} />}
            </div>
          </div>
        </main>

        {/* Batch history sidebar */}
        <BatchHistory refreshKey={historyKey} />
      </div>
    </div>
  );
}