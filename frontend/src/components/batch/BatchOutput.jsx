import { useState, useCallback, useEffect, useRef } from "react";
import { useOutputStore } from "../../store/outputStore";
import { useWsProgress } from "../../hooks/useWsProgress";
import {
  uploadBatch as uploadBatchPuma,
  fetchBatch as fetchBatchPuma,
  fetchBatchLogs as fetchBatchLogsPuma,
  retryBatch as retryBatchPuma,
  downloadExcel as downloadExcelPuma,
  downloadCertificate as downloadCertificatePuma,
  downloadReportPDF as downloadReportPDFPuma,
} from "../../services/pumaApi";
import {
  uploadBatch as uploadBatchImage,
  fetchBatch as fetchBatchImage,
  fetchBatchLogs as fetchBatchLogsImage,
  downloadReportPDF as downloadReportPDFImage,
  downloadReportDOCX as downloadReportDOCXImage,
} from "../../services/defectImageApi";

// ── Helpers ───────────────────────────────────────────────────────────────────
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ── Upload form ───────────────────────────────────────────────────────────────
export function UploadForm({ initData = {}, source = "puma" }) {
  const { addLog, setOutput, setLoading } = useOutputStore();
  const [files, setFiles]       = useState([]);
  const [date, setDate]         = useState(initData.date || new Date().toISOString().slice(0, 10));
  const [style, setStyle]       = useState(initData.style || "");
  const [isDragOver, setIsDragOver] = useState(false);
  const [batchId, setBatch]     = useState(initData.batch_id ?? null);
  const [progress, setProgress] = useState(initData.progress ?? null);

  // Refs for inputs
  const folderInputRef = useRef(null);
  const fileInputRef   = useRef(null);

  const isImageUpload = source === "image";
  const serviceUpload = isImageUpload ? uploadBatchImage : uploadBatchPuma;
  const serviceFetchBatch = isImageUpload ? fetchBatchImage : fetchBatchPuma;

  // Keep store in sync so progress survives remounts
  const syncStore = useCallback((patch) => {
    useOutputStore.setState((s) => ({
      output: s.output ? { ...s.output, ...patch } : s.output,
    }));
  }, []);

  // ── File collection helpers ───────────────────────────────────────────────

  // Process a FileList (from input or DataTransfer), preserving webkitRelativePath
  const processFileList = useCallback((fileList) => {
    const accepted = [];
    const validExts = isImageUpload
      ? new Set([".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"])
      : new Set([".pdf"]);

    for (const file of fileList) {
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (validExts.has(ext) && file.size > 0) {
        accepted.push(file);
      }
    }
    if (accepted.length > 0) setFiles(accepted);
  }, [isImageUpload]);

  // ── Drag-and-drop ─────────────────────────────────────────────────────────

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const items = e.dataTransfer?.items;
    if (!items) return;

    // Use DataTransferItemList to get webkitGetAsEntry for folder traversal
    const allFiles = [];
    const promises = [];

    const traverseEntry = (entry) => {
      return new Promise((resolve) => {
        if (entry.isFile) {
          entry.file((file) => {
            // Reconstruct a path that mirrors webkitRelativePath
            // entry.fullPath starts with "/" so we strip it
            const relativePath = entry.fullPath.replace(/^\//, "");
            // Attach the relative path so upload knows folder structure
            Object.defineProperty(file, "webkitRelativePath", {
              value: relativePath,
              writable: false,
            });
            allFiles.push(file);
            resolve();
          }, resolve);
        } else if (entry.isDirectory) {
          const reader = entry.createReader();
          const readAll = () => {
            reader.readEntries((entries) => {
              if (entries.length === 0) { resolve(); return; }
              Promise.all(entries.map(traverseEntry)).then(() => readAll());
            }, resolve);
          };
          readAll();
        } else {
          resolve();
        }
      });
    };

    for (const item of items) {
      const entry = item.webkitGetAsEntry?.();
      if (entry) promises.push(traverseEntry(entry));
    }

    Promise.all(promises).then(() => processFileList(allFiles));
  }, [processFileList]);

  // ── Folder/file input changes ─────────────────────────────────────────────
  const handleFolderInputChange = useCallback((e) => {
    processFileList(e.target.files);
    e.target.value = ""; // allow re-selecting same folder
  }, [processFileList]);

  const handleFileInputChange = useCallback((e) => {
    processFileList(e.target.files);
    e.target.value = "";
  }, [processFileList]);

  // ── Derived folder summary ────────────────────────────────────────────────
  const folderSummary = (() => {
    if (!files.length) return null;
    const byFolder = {};
    for (const f of files) {
      const rel  = f.webkitRelativePath || f.name;
      const parts = rel.split("/");
      const folder = parts.length > 1 ? parts[0] : "(root)";
      if (!byFolder[folder]) byFolder[folder] = 0;
      byFolder[folder]++;
    }
    return byFolder;
  })();

  // ── Upload handler ────────────────────────────────────────────────────────
  const handleUpload = async () => {
    if (!files.length || batchId) return;
    setLoading(true);

    addLog({
      level: "info",
      message: `Uploading ${files.length} file(s) from ${Object.keys(folderSummary || {}).length} folder(s)…`,
    });

    try {
      let res;

      if (isImageUpload) {
        // Extract relative paths from webkitRelativePath, falling back to filename
        const paths = files.map((f) => f.webkitRelativePath || f.name);
        res = await serviceUpload(files, paths, date, style);
      } else {
        res = await serviceUpload(files);
      }

      const totalItems = res.total_pdfs ?? res.total_folders ?? files.length;
      const initialProgress = { processed: 0, total: totalItems, percent: 0, stage: "QUEUED" };
      setBatch(res.batch_id);
      setProgress(initialProgress);
      setOutput(
        "batch-progress",
        { ...res, batch_id: res.batch_id, progress: initialProgress, source, date, style },
        `Batch #${res.batch_id}`
      );
      addLog({
        level: "success",
        message: `Batch #${res.batch_id} created — ${totalItems} folder(s) queued`,
      });
      setLoading(false);
    } catch (e) {
      const detail = e.response?.data?.detail || e.response?.data || e.message;
      addLog({
        level: "error",
        message: `Upload failed: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
      });
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
      addLog({ level: "success", message: `Batch #${msg.batch_id} complete — ${msg.report_count} report(s) saved` });
      if (msg.failed > 0)
        addLog({ level: "warning", message: `${msg.failed} folder(s) failed in Batch #${msg.batch_id}` });
      const full = await serviceFetchBatch(msg.batch_id);
      setOutput("batch", full, `Batch #${msg.batch_id}`, { source });
      setBatch(null);
    },
    onError: (msg) => {
      addLog({ level: "error", message: `Batch #${msg.batch_id} error: ${msg.error_message}` });
      setProgress(null);
      syncStore({ progress: null });
    },
  });

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px", maxWidth: "600px" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: 0, color: "var(--color-text)" }}>
        {isImageUpload ? "Upload Image Folders" : "Upload PDFs"}
      </h2>

      {/* Drop zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{
          border: `2px dashed ${isDragOver ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "10px",
          padding: "40px 24px",
          textAlign: "center",
          background: isDragOver ? "rgba(99,102,241,0.06)" : "var(--color-surface)",
          transition: "all 0.2s",
        }}
      >
        <div style={{ fontSize: "28px", marginBottom: "10px" }}>
          {isImageUpload ? "🗂️" : "📄"}
        </div>
        <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-text)", marginBottom: "6px" }}>
          {isImageUpload
            ? "Drag & drop image folders here"
            : "Drag & drop PDF files here"}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", opacity: 0.7, marginBottom: "16px" }}>
          {isImageUpload
            ? "Each folder becomes one DOCX report · 50 MB per file max"
            : "PDF only · 50 MB per file max"}
        </div>

        {/* Hidden inputs */}
        {isImageUpload && (
          <>
            {/* Folder picker — webkitdirectory lets the user pick an entire folder */}
            <input
              ref={folderInputRef}
              type="file"
              style={{ display: "none" }}
              // These attributes MUST be set as strings on the DOM element —
              // React doesn't support webkitdirectory as a prop on <input>.
              onChange={handleFolderInputChange}
              multiple
            />
            {/* Fallback: individual file picker */}
            <input
              ref={fileInputRef}
              type="file"
              style={{ display: "none" }}
              accept="image/*"
              onChange={handleFileInputChange}
              multiple
            />
          </>
        )}
        {!isImageUpload && (
          <input
            ref={fileInputRef}
            type="file"
            style={{ display: "none" }}
            accept=".pdf"
            onChange={handleFileInputChange}
            multiple
          />
        )}

        <div style={{ display: "flex", gap: "8px", justifyContent: "center", flexWrap: "wrap" }}>
          {isImageUpload && (
            <button
              onClick={() => {
                // Set webkitdirectory imperatively — avoids React JSX limitation
                const input = folderInputRef.current;
                if (input) {
                  input.setAttribute("webkitdirectory", "");
                  input.setAttribute("directory", "");
                  input.click();
                }
              }}
              style={pickBtnStyle}
            >
              📁 Select Folder(s)
            </button>
          )}
          <button
            onClick={() => fileInputRef.current?.click()}
            style={pickBtnStyle}
          >
            {isImageUpload ? "🖼️ Select Images" : "📄 Select PDFs"}
          </button>
        </div>
      </div>

      {/* Date + Style inputs for image mode */}
      {isImageUpload && (
        <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
          <label style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-muted)", display: "flex", flexDirection: "column", gap: "6px" }}>
            Inspection Date
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              style={inputStyle}
            />
          </label>
          <label style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-muted)", display: "flex", flexDirection: "column", gap: "6px" }}>
            Style Name (optional)
            <input
              type="text"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              placeholder="e.g. ABC-001"
              style={inputStyle}
            />
          </label>
        </div>
      )}

      {/* Folder/file preview */}
      {folderSummary && Object.keys(folderSummary).length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "4px" }}>
            {isImageUpload
              ? `${Object.keys(folderSummary).length} FOLDER(S) · ${files.length} IMAGE(S) TOTAL`
              : `${files.length} FILE(S) SELECTED`}
          </div>
          {Object.entries(folderSummary).map(([folder, count]) => (
            <div
              key={folder}
              style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "7px 12px",
                background: "var(--color-surface)",
                borderRadius: "5px",
                border: "1px solid var(--color-border)",
              }}
            >
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)" }}>
                {isImageUpload ? "📁 " : "📄 "}{folder}
              </span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
                {count} {isImageUpload ? "image(s)" : "file(s)"}
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

      {/* Upload button */}
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

const pickBtnStyle = {
  background: "rgba(99,102,241,0.1)",
  border: "1px solid rgba(99,102,241,0.25)",
  color: "var(--color-accent2)",
  padding: "8px 16px",
  borderRadius: "6px",
  fontFamily: "var(--font-mono)",
  fontSize: "11px",
  cursor: "pointer",
  transition: "all 0.15s",
};

const inputStyle = {
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-panel)",
  color: "var(--color-text)",
  fontFamily: "var(--font-mono)",
  fontSize: "12px",
  width: "180px",
};

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
    hasExcel && { key: "excel", label: "Excel (.xlsx)", icon: "📊", desc: "All reports in this batch" },
    activeReportCount > 0 && { key: "pdfs", label: "Reports (.pdf)", icon: "📄", desc: `${activeReportCount} renamed PDF(s)` },
    activeReportCount > 0 && { key: "certificates", label: "Reports (.docx)", icon: "📝", desc: `${activeReportCount} DOCX report(s)` },
    hasExcel && activeReportCount > 0 && { key: "all", label: "All files", icon: "📦", desc: "PDF, DOCX, and Excel for batch" },
  ].filter(Boolean);

  if (!items.length) return <IconBtn title="No downloads available" disabled>⬇</IconBtn>;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <IconBtn title="Downloads" onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }} active={open}>
        ⬇
      </IconBtn>
      {open && (
        <div style={{
          position: "absolute", right: 0, top: "calc(100% + 4px)",
          background: "var(--color-surface)", border: "1px solid var(--color-border)",
          borderRadius: "8px", minWidth: "190px", zIndex: 50,
          boxShadow: "0 8px 24px rgba(0,0,0,0.3)", overflow: "hidden",
        }}>
          <div style={{ padding: "6px 12px 4px", fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", letterSpacing: "0.08em", borderBottom: "1px solid var(--color-border)" }}>
            DOWNLOAD
          </div>
          {items.map((item) => (
            <button
              key={item.key}
              onClick={(e) => { e.stopPropagation(); setOpen(false); onAction(item.key); }}
              style={{ width: "100%", background: "none", border: "none", padding: "9px 14px", display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", textAlign: "left" }}
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

function BatchRow({ batch, onAction }) {
  const color    = STATUS_COLOR[batch.status] || "var(--color-muted)";
  const canRetry = batch.status === "PARTIAL" || batch.status === "FAILED";
  const hasExcel = !!batch.excel_report_path || batch.excel_available;
  const reports  = batch.reports || [];

  // Support both puma (total_pdfs) and image (total_folders) batch types
  const total     = batch.total_folders ?? batch.total_pdfs ?? 0;
  const processed = batch.processed_folders ?? batch.processed_pdfs ?? 0;

  return (
    <div
      onClick={() => onAction("view", batch.id)}
      style={{
        display: "grid", gridTemplateColumns: "48px 1fr 80px 90px 100px 96px",
        gap: "8px", padding: "10px 14px",
        background: "var(--color-surface)", border: "1px solid var(--color-border)",
        borderLeft: `3px solid ${color}`, borderRadius: "7px",
        alignItems: "center", transition: "border-color 0.15s", cursor: "pointer",
      }}
    >
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)" }}>
        #{batch.id}
      </span>
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
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color, background: `${color}18`, padding: "2px 7px", borderRadius: "3px", whiteSpace: "nowrap", display: "inline-block" }}>
        {batch.status}
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-muted)" }}>
        {processed}/{total}
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: batch.success_rate === 100 ? "var(--color-success)" : "var(--color-warning)" }}>
        {batch.success_rate}%
      </span>
      <div style={{ display: "flex", gap: "4px", justifyContent: "flex-end" }} onClick={(e) => e.stopPropagation()}>
        <IconBtn title={canRetry ? "Retry failed" : "No failures to retry"} disabled={!canRetry} color="var(--color-warning)" onClick={() => onAction("retry", batch.id)}>
          ↺
        </IconBtn>
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
    failedPdfs.filter((f) => !f.retried).map((f) => f.filename || f.folder_name)
  );
  const toggle = (name) =>
    setSelected((prev) => prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]);
  const allUnretried = failedPdfs.filter((f) => !f.retried);

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }}>
      <div className="fade-up" style={{
        background: "var(--color-surface)", border: "1px solid var(--color-border)",
        borderRadius: "12px", padding: "24px 28px", minWidth: "400px", maxWidth: "560px",
        display: "flex", flexDirection: "column", gap: "16px",
      }}>
        <div style={{ fontFamily: "var(--font-display)", fontSize: "15px", fontWeight: 700, color: "var(--color-text)" }}>
          Retry Failed Items
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px", maxHeight: "300px", overflowY: "auto" }}>
          {failedPdfs.map((f) => {
            const name = f.filename || f.folder_name;
            return (
              <label key={name} style={{
                display: "flex", alignItems: "flex-start", gap: "10px",
                padding: "8px 12px", borderRadius: "6px",
                background: f.retried ? "rgba(34,211,160,0.05)" : "rgba(244,63,94,0.05)",
                border: `1px solid ${f.retried ? "rgba(34,211,160,0.15)" : "rgba(244,63,94,0.15)"}`,
                cursor: f.retried ? "default" : "pointer", opacity: f.retried ? 0.5 : 1,
              }}>
                <input type="checkbox" disabled={f.retried} checked={selected.includes(name)} onChange={() => toggle(name)} style={{ marginTop: "2px", accentColor: "var(--color-accent)" }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text)", wordBreak: "break-all" }}>
                    {name}{f.retried && <span style={{ color: "var(--color-success)", marginLeft: "8px" }}>✓ already retried</span>}
                  </div>
                  {f.reason && <div style={{ fontFamily: "var(--font-body)", fontSize: "10px", color: "var(--color-muted)", marginTop: "2px" }}>{f.reason}</div>}
                </div>
              </label>
            );
          })}
        </div>
        <div style={{ display: "flex", gap: "8px", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
            {selected.length} of {allUnretried.length} selected
          </span>
          <div style={{ display: "flex", gap: "8px" }}>
            <button onClick={onCancel} style={ghostBtn}>Cancel</button>
            <button disabled={!selected.length} onClick={() => onConfirm(selected)} style={{ ...ghostBtn, background: selected.length ? "var(--color-accent)" : "var(--color-border)", color: selected.length ? "#fff" : "var(--color-muted)", borderColor: selected.length ? "var(--color-accent)" : "var(--color-border)", cursor: selected.length ? "pointer" : "not-allowed" }}>
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
export function BatchDetail({ data, source = "puma" }) {
  const { addLog, setOutput } = useOutputStore();
  const [showRetryModal, setShowRetryModal] = useState(false);
  const isImage = source === "image";

  const color         = STATUS_COLOR[data?.status] || "var(--color-muted)";
  const failedRecords = data?.failed_folder_records || data?.failed_pdf_records || [];
  const failedCount   = data?.failed_folders_count ?? data?.failed_pdfs_count ?? failedRecords.length;
  const hasRetryable  = failedRecords.some((f) => !f.retried);
  const canRetry      = (data?.status === "PARTIAL" || data?.status === "FAILED") && hasRetryable;

  const total     = data?.total_folders ?? data?.total_pdfs ?? 0;
  const processed = data?.processed_folders ?? data?.processed_pdfs ?? 0;

  const handleRetryConfirm = async (names) => {
    setShowRetryModal(false);
    if (isImage) { addLog({ level: "warning", message: "Retry is not supported for image batches yet." }); return; }
    addLog({ level: "info", message: `Retrying ${names.length} item(s) in Batch #${data.id}…` });
    try {
      const res = await retryBatchPuma(data.id, names);
      addLog({ level: "success", message: `Retry started — ${res.files_retrying?.length} file(s)` });
      const updated = await fetchBatchPuma(data.id);
      setOutput("batch", updated, `Batch #${data.id}`);
    } catch (e) {
      addLog({ level: "error", message: `Retry failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  const handleExcel = async () => {
    if (isImage) { addLog({ level: "warning", message: "Excel download unavailable for image batches." }); return; }
    try {
      const blob = await downloadExcelPuma(data.id);
      saveBlob(blob, `batch-${data.id}.xlsx`);
      addLog({ level: "success", message: `Excel downloaded for Batch #${data.id}` });
    } catch (e) {
      addLog({ level: "error", message: `Excel download failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {showRetryModal && (
        <RetryModal failedPdfs={failedRecords} onConfirm={handleRetryConfirm} onCancel={() => setShowRetryModal(false)} />
      )}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: 0 }}>
          Batch #{data?.id}
        </h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color, background: `${color}18`, padding: "2px 10px", borderRadius: "4px" }}>
          {data?.status}
        </span>
        {data?.created_by && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
            by {data.created_by.username}
          </span>
        )}
        <div style={{ flex: 1 }} />
        {data?.excel_available && <Btn onClick={handleExcel} accent>⬇ Excel</Btn>}
        {canRetry && <Btn onClick={() => setShowRetryModal(true)}>↺ Retry Failed</Btn>}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px" }}>
        {[
          ["Total",       total],
          ["Processed",   processed],
          ["Failed",      failedCount],
          ["Success",     `${data?.success_rate}%`],
        ].map(([label, val]) => <Stat key={label} label={label} value={val} />)}
      </div>

      {failedRecords.length > 0 && (
        <Section title="Failed Items">
          {failedRecords.map((f) => (
            <div key={f.id} style={{ padding: "8px 12px", background: "rgba(244,63,94,0.06)", borderRadius: "5px", borderLeft: "2px solid var(--color-error)", marginBottom: "4px" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-error)" }}>
                {f.filename || f.folder_name}
              </div>
              <div style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--color-muted)", marginTop: "2px" }}>{f.reason}</div>
              {f.retried && <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-success)" }}>✓ retried</span>}
            </div>
          ))}
        </Section>
      )}

      {data?.reports?.length > 0 && (
        <Section title={`Reports (${data.reports.length})`}>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {data.reports.map((r) => (
              <div key={r.id} style={{ display: "flex", gap: "12px", padding: "8px 12px", background: "var(--color-panel)", borderRadius: "5px", border: "1px solid var(--color-border)", fontSize: "12px", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-accent2)", minWidth: "80px" }}>
                  {r.folder_name || r.style}
                </span>
                <span style={{ color: "var(--color-muted)" }}>{r.factory_code || r.status}</span>
                <span style={{ color: "var(--color-muted)", fontSize: "10px", flex: 1 }}>
                  {r.image_count ? `${r.image_count} images` : (r.po_numbers?.map((p) => p.number).join(", "))}
                </span>
                <ReportCertBtn reportId={r.id} styleName={r.folder_name || r.style} pdfFilename={r.pdf_filename} source={source} />
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

function ReportCertBtn({ reportId, styleName, pdfFilename, source = "puma" }) {
  const { addLog } = useOutputStore();
  const [busy, setBusy] = useState(false);
  const isImage = source === "image";
  const downloadFn  = isImage ? downloadReportPDFImage  : downloadReportPDFPuma;
  const downloadDocx = isImage ? downloadReportDOCXImage : downloadCertificatePuma;

  const handleClick = async (e) => {
    e.stopPropagation();
    setBusy(true);
    try {
      const blob = await downloadDocx(reportId);
      const name = pdfFilename
        ? pdfFilename.replace(/\.(pdf|docx)$/i, ".docx")
        : `${styleName || "report"}-${reportId}.docx`;
      saveBlob(blob, name);
      addLog({ level: "success", message: `Downloaded: ${name}` });
    } catch (err) {
      addLog({ level: "error", message: `Download failed: ${err.response?.data?.detail || err.message}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={busy}
      title="Download DOCX"
      style={{
        background: "rgba(34,211,160,0.08)", border: "1px solid rgba(34,211,160,0.2)",
        color: "var(--color-success)", padding: "3px 10px", borderRadius: "4px",
        fontFamily: "var(--font-mono)", fontSize: "10px",
        cursor: busy ? "wait" : "pointer", opacity: busy ? 0.6 : 1, whiteSpace: "nowrap",
      }}
    >
      {busy ? "…" : "⬇ docx"}
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
      {(data?.failed_pdfs || data?.failed_folders || []).map((f) => (
        <div key={f.id} style={{ padding: "10px 14px", background: "var(--color-surface)", borderRadius: "6px", borderLeft: `2px solid ${f.retried ? "var(--color-success)" : "var(--color-error)"}` }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: f.retried ? "var(--color-success)" : "var(--color-error)" }}>
            {f.filename || f.folder_name}
          </div>
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
    <button onClick={onClick} style={{ background: accent ? "rgba(99,102,241,0.12)" : "var(--color-surface)", border: `1px solid ${accent ? "rgba(99,102,241,0.3)" : "var(--color-border)"}`, color: accent ? "var(--color-accent2)" : "var(--color-muted)", padding: "5px 14px", borderRadius: "5px", fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer", transition: "all 0.15s" }}>
      {children}
    </button>
  );
}

// ── Router component ──────────────────────────────────────────────────────────
export default function BatchOutput({ output }) {
  const { setOutput, setLoading, addLog } = useOutputStore();
  const isImage = output?.source === "image";
  const fetchBatch      = isImage ? fetchBatchImage      : fetchBatchPuma;
  const fetchBatchLogs  = isImage ? fetchBatchLogsImage  : fetchBatchLogsPuma;
  const downloadPDF     = isImage ? downloadReportPDFImage  : downloadReportPDFPuma;
  const downloadDocx    = isImage ? downloadReportDOCXImage : downloadCertificatePuma;
  const downloadExcel   = isImage ? null : downloadExcelPuma;

  const handleAction = async (action, id, meta = {}) => {
    switch (action) {
      case "view":
      case "retry": {
        setLoading(true);
        try {
          const data = await fetchBatch(id);
          setOutput("batch", data, `Batch #${id}`, { source: output?.source });
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
          const data = await fetchBatchLogs(id);
          setOutput("logs", data, `Logs · Batch #${id}`);
          addLog({ level: "info", message: `Logs loaded — ${data.total_failed} failed` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load logs for Batch #${id}` });
          setLoading(false);
        }
        break;
      }
      case "excel": {
        if (!downloadExcel) { addLog({ level: "warning", message: "Excel unavailable for image batches." }); break; }
        try {
          const blob = await downloadExcel(id);
          saveBlob(blob, `batch-${id}.xlsx`);
          addLog({ level: "success", message: `Excel downloaded for Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Excel download failed: ${e.response?.data?.detail || e.message}` });
        }
        break;
      }
      case "pdfs":
      case "certificates":
      case "all": {
        const reports = meta.reports?.length ? meta.reports : (await fetchBatch(id)).reports || [];
        for (const report of reports) {
          if (action === "pdfs" || action === "all") {
            try {
              const blob = await downloadPDF(report.id);
              const name = report.pdf_filename || `${report.style || report.folder_name || report.id}.pdf`;
              saveBlob(blob, name);
              addLog({ level: "success", message: `PDF: ${name}` });
            } catch (e) {
              addLog({ level: "error", message: `PDF failed: ${e.response?.data?.detail || e.message}` });
            }
          }
          if (action === "certificates" || action === "all") {
            try {
              const blob = await downloadDocx(report.id);
              const name = (report.pdf_filename || `${report.folder_name || report.id}`).replace(/\.(pdf|docx)$/i, ".docx");
              saveBlob(blob, name);
              addLog({ level: "success", message: `DOCX: ${name}` });
            } catch (e) {
              addLog({ level: "error", message: `DOCX failed: ${e.response?.data?.detail || e.message}` });
            }
          }
        }
        if ((action === "all") && downloadExcel && meta.hasExcel) {
          try {
            const blob = await downloadExcel(id);
            saveBlob(blob, `batch-${id}.xlsx`);
            addLog({ level: "success", message: `Excel downloaded` });
          } catch (e) {
            addLog({ level: "error", message: `Excel failed: ${e.response?.data?.detail || e.message}` });
          }
        }
        break;
      }
    }
  };

  if (output.type === "batch-list")     return <BatchList data={output.data} onAction={handleAction} />;
  if (output.type === "batch")          return <BatchDetail data={output.data} source={output.source} />;
  if (output.type === "logs")           return <BatchLogsView data={output.data} />;
  if (output.type === "batch-progress") return <UploadForm initData={output.data ?? {}} source={output.source} />;
  return null;
}