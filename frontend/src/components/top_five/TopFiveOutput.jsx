import { useState, useRef, useCallback, useEffect } from "react";
import { useOutputStore } from "../../store/outputStore";
import { uploadFile, fetchJob, downloadResult } from "../../services/topFiveApi";

// ── Helpers ───────────────────────────────────────────────────────────────────
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Status helpers ────────────────────────────────────────────────────────────
const STATUS_COLOR = {
  DONE:       "var(--color-success)",
  FAILED:     "var(--color-error)",
  PROCESSING: "var(--color-accent2)",
  PENDING:    "var(--color-muted)",
};

const STATUS_LABEL = {
  PENDING:    "Queued…",
  PROCESSING: "Processing…",
  DONE:       "Done ✓",
  FAILED:     "Failed",
};

const mono = { fontFamily: "var(--font-mono)" };

// ── Upload view ───────────────────────────────────────────────────────────────
export function TopFiveUploadView({ initData = {} }) {
  const { addLog, setOutput } = useOutputStore();
  const [file,   setFile]   = useState(null);
  const [isDrag, setIsDrag] = useState(false);
  const [jobId,  setJobId]  = useState(initData.job_id ?? null);
  const [status, setStatus] = useState(initData.status ?? null);
  const [error,  setError]  = useState("");
  const [busy,   setBusy]   = useState(false);
  const inputRef  = useRef(null);
  const pollRef   = useRef(null);

  // Cleanup on unmount
  useEffect(() => () => clearInterval(pollRef.current), []);

  const reset = useCallback(() => {
    clearInterval(pollRef.current);
    setFile(null); setJobId(null); setStatus(null);
    setError(""); setBusy(false);
  }, []);

  const pickFile = useCallback((f) => {
    if (!f) return;
    const name = f.name.toLowerCase();
    if (!name.endsWith(".xlsx") && !name.endsWith(".xls")) {
      setError("Only .xlsx / .xls files are accepted.");
      return;
    }
    setError(""); setFile(f); setStatus(null); setJobId(null);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDrag(false);
    pickFile(e.dataTransfer.files?.[0]);
  }, [pickFile]);

  const startPoll = useCallback((id) => {
    pollRef.current = setInterval(async () => {
      try {
        const job = await fetchJob(id);
        setStatus(job.status);
        useOutputStore.setState((s) => ({
          output: s.output ? { ...s.output, data: { ...s.output.data, status: job.status } } : s.output,
        }));
        if (job.status === "DONE" || job.status === "FAILED") {
          clearInterval(pollRef.current);
          setBusy(false);
          if (job.status === "FAILED") {
            setError(job.error || "Processing failed.");
            addLog({ level: "error", message: `Job #${id} failed: ${job.error || "unknown error"}` });
          } else {
            addLog({ level: "success", message: `Job #${id} completed — ready to download` });
          }
        }
      } catch {
        clearInterval(pollRef.current);
        setBusy(false);
        setError("Could not reach server while polling.");
        addLog({ level: "error", message: "Polling error — lost connection to server" });
      }
    }, 1500);
  }, [addLog]);

  const handleProcess = useCallback(async () => {
    if (!file || busy) return;
    setBusy(true); setError(""); setStatus("PENDING");
    addLog({ level: "info", message: `Uploading ${file.name}…` });
    try {
      const { job_id } = await uploadFile(file);
      setJobId(job_id);
      setStatus("PENDING");
      addLog({ level: "success", message: `Job #${job_id} created — processing queued` });
      startPoll(job_id);
    } catch (e) {
      setBusy(false); setStatus("FAILED");
      const msg = e.response?.data?.detail || e.message;
      setError(msg);
      addLog({ level: "error", message: `Upload failed: ${msg}` });
    }
  }, [file, busy, addLog, startPoll]);

  const handleDownload = useCallback(async () => {
    if (status !== "DONE" || !jobId) return;
    addLog({ level: "info", message: `Downloading result for Job #${jobId}…` });
    try {
      const blob = await downloadResult(jobId);
      const filename = file ? `Audit_Result_${file.name.replace(/\.[^.]+$/, "")}.xlsx` : `top5_result_${jobId}.xlsx`;
      saveBlob(blob, filename);
      addLog({ level: "success", message: `Downloaded: ${filename}` });
    } catch (e) {
      const msg = e.response?.data?.detail || e.message;
      addLog({ level: "error", message: `Download failed: ${msg}` });
    }
  }, [status, jobId, file, addLog]);

  const pill = status ? { color: STATUS_COLOR[status], label: STATUS_LABEL[status] } : null;

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "20px", maxWidth: "560px" }}>
      {/* Header */}
      <div>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" }}>
          Top-5 Defect Report
        </h2>
        <p style={{ ...mono, fontSize: "12px", color: "var(--color-muted)", margin: 0 }}>
          Upload a single audit Excel file. The result will be written into the report template and returned as a download.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDrag(true); }}
        onDragLeave={() => setIsDrag(false)}
        onDrop={handleDrop}
        onClick={() => !busy && inputRef.current?.click()}
        style={{
          border: `2px dashed ${isDrag ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "10px",
          padding: "40px 24px",
          textAlign: "center",
          background: isDrag ? "rgba(99,102,241,0.06)" : "var(--color-surface)",
          cursor: busy ? "not-allowed" : "pointer",
          transition: "all 0.18s",
        }}
      >
        <input
          ref={inputRef} type="file" accept=".xlsx,.xls"
          style={{ display: "none" }}
          onChange={(e) => { pickFile(e.target.files?.[0]); e.target.value = ""; }}
        />
        <div style={{ fontSize: "28px", marginBottom: "10px" }}>📊</div>
        {file ? (
          <>
            <div style={{ ...mono, fontSize: "12px", color: "var(--color-accent2)", marginBottom: "4px" }}>
              📄 {file.name}
            </div>
            <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>
              {(file.size / 1024).toFixed(0)} KB · click to change
            </div>
          </>
        ) : (
          <>
            <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-text)", marginBottom: "6px" }}>
              Drag & drop your Excel file here, or click to browse
            </div>
            <div style={{ ...mono, fontSize: "10px", color: "var(--color-muted)" }}>
              .xlsx or .xls · 50 MB max · must contain a "Final" or "Re-Final" sheet
            </div>
          </>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{
          ...mono, fontSize: "11px", color: "var(--color-error)",
          background: "rgba(244,63,94,0.07)", border: "1px solid rgba(244,63,94,0.2)",
          borderRadius: "7px", padding: "10px 14px",
        }}>
          ⚠ {error}
        </div>
      )}

      {/* Status pill */}
      {pill && (
        <div style={{
          display: "flex", alignItems: "center", gap: "10px",
          background: "var(--color-surface)", border: "1px solid var(--color-border)",
          borderRadius: "10px", padding: "12px 16px",
        }}>
          {(status === "PROCESSING" || status === "PENDING") ? (
            <div style={{
              width: "14px", height: "14px", borderRadius: "50%",
              border: "2px solid var(--color-border)",
              borderTopColor: "var(--color-accent)",
              animation: "spin 0.8s linear infinite",
              flexShrink: 0,
            }} />
          ) : (
            <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: pill.color, flexShrink: 0 }} />
          )}
          <span style={{ ...mono, fontSize: "11px", color: pill.color }}>{pill.label}</span>
          {jobId && (
            <span style={{ ...mono, fontSize: "10px", color: "var(--color-muted)", marginLeft: "auto" }}>
              Job #{jobId}
            </span>
          )}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: "flex", gap: "10px" }}>
        <button
          onClick={handleProcess}
          disabled={!file || busy}
          style={{
            flex: 1,
            background: file && !busy ? "var(--color-accent)" : "var(--color-border)",
            color: file && !busy ? "#fff" : "var(--color-muted)",
            border: "none", padding: "11px 0", borderRadius: "6px",
            fontFamily: "var(--font-display)", fontSize: "13px", fontWeight: 600,
            letterSpacing: "0.06em", cursor: file && !busy ? "pointer" : "not-allowed",
            transition: "all 0.15s",
          }}
        >
          {busy ? "PROCESSING…" : "▶  PROCESS"}
        </button>
        <button
          onClick={handleDownload}
          disabled={status !== "DONE"}
          style={{
            flex: 1,
            background: status === "DONE" ? "rgba(34,211,160,0.12)" : "var(--color-border)",
            color: status === "DONE" ? "var(--color-success)" : "var(--color-muted)",
            border: `1px solid ${status === "DONE" ? "rgba(34,211,160,0.3)" : "var(--color-border)"}`,
            padding: "11px 0", borderRadius: "6px",
            fontFamily: "var(--font-display)", fontSize: "13px", fontWeight: 600,
            letterSpacing: "0.06em", cursor: status === "DONE" ? "pointer" : "not-allowed",
            transition: "all 0.15s",
          }}
        >
          ⬇  DOWNLOAD
        </button>
      </div>

      {/* Reset */}
      {(status === "DONE" || status === "FAILED") && (
        <button
          onClick={reset}
          style={{
            background: "transparent", border: "1px solid var(--color-border)",
            color: "var(--color-muted)", padding: "8px 0", borderRadius: "6px",
            ...mono, fontSize: "11px", cursor: "pointer",
          }}
        >
          ↺  Process another file
        </button>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ── Job list view ─────────────────────────────────────────────────────────────
export function TopFiveJobList({ data, onAction }) {
  const jobs = data?.results || data || [];
  const sorted = [...jobs].sort((a, b) => {
    const da = a.created_at || "";
    const db = b.created_at || "";
    return da !== db ? db.localeCompare(da) : b.id - a.id;
  });

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <h2 style={{ fontFamily: "var(--font-display)", fontSize: "16px", fontWeight: 700, margin: "0 0 8px", color: "var(--color-text)" }}>
        Jobs <span style={{ color: "var(--color-muted)", fontSize: "12px", fontWeight: 400 }}>({sorted.length})</span>
      </h2>

      {/* Column headers */}
      <div style={{
        display: "grid", gridTemplateColumns: "52px 1fr 96px 140px 100px",
        gap: "8px", padding: "4px 14px",
        fontFamily: "var(--font-mono)", fontSize: "9px", letterSpacing: "0.08em", color: "var(--color-muted)",
      }}>
        <span>#ID</span><span>FILE</span><span>STATUS</span><span>CREATED</span><span style={{ textAlign: "right" }}>ACTIONS</span>
      </div>

      {sorted.map((job) => <JobRow key={job.id} job={job} onAction={onAction} />)}

      {sorted.length === 0 && (
        <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-muted)", padding: "32px 0", textAlign: "center" }}>
          No jobs found.
        </div>
      )}
    </div>
  );
}

function JobRow({ job, onAction }) {
  const color = STATUS_COLOR[job.status] || "var(--color-muted)";
  const canDownload = job.status === "DONE";

  const createdAt = job.created_at
    ? new Date(job.created_at).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })
    : "—";

  return (
    <div
      onClick={() => onAction("view", job.id)}
      style={{
        display: "grid", gridTemplateColumns: "52px 1fr 96px 140px 100px",
        gap: "8px", padding: "10px 14px",
        background: "var(--color-surface)", border: "1px solid var(--color-border)",
        borderLeft: `3px solid ${color}`, borderRadius: "7px",
        alignItems: "center", transition: "border-color 0.15s", cursor: "pointer",
      }}
    >
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-accent2)" }}>
        #{job.id}
      </span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--color-text)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {job.input_file || "—"}
        </div>
        {job.created_by_username && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
            by {job.created_by_username}
          </div>
        )}
      </div>
      <span style={{
        fontFamily: "var(--font-mono)", fontSize: "9px", color,
        background: `${color}18`, padding: "2px 7px", borderRadius: "3px",
        whiteSpace: "nowrap", display: "inline-block",
      }}>
        {job.status}
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-muted)" }}>
        {createdAt}
      </span>
      <div
        style={{ display: "flex", gap: "4px", justifyContent: "flex-end" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Download button */}
        <button
          title={canDownload ? "Download result" : "Not ready"}
          disabled={!canDownload}
          onClick={() => onAction("download", job.id, { inputFile: job.input_file })}
          style={{
            background: canDownload ? "rgba(34,211,160,0.08)" : "transparent",
            border: `1px solid ${canDownload ? "rgba(34,211,160,0.25)" : "var(--color-border)"}`,
            color: canDownload ? "var(--color-success)" : "var(--color-muted)",
            width: "28px", height: "28px", borderRadius: "5px",
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: canDownload ? "pointer" : "not-allowed",
            fontSize: "13px", opacity: canDownload ? 1 : 0.35, transition: "all 0.12s",
          }}
        >
          ⬇
        </button>
      </div>
    </div>
  );
}

// ── Job detail view ───────────────────────────────────────────────────────────
export function TopFiveJobDetail({ data, onDownload }) {
  const color = STATUS_COLOR[data?.status] || "var(--color-muted)";
  const canDownload = data?.status === "DONE";

  const fields = [
    ["Job ID",      `#${data?.id}`],
    ["File",        data?.input_file],
    ["Status",      data?.status],
    ["Created At",  data?.created_at ? new Date(data.created_at).toLocaleString() : "—"],
    ["Updated At",  data?.updated_at ? new Date(data.updated_at).toLocaleString() : "—"],
  ];

  return (
    <div className="fade-up" style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 700, margin: 0 }}>
          Job #{data?.id}
        </h2>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color, background: `${color}18`, padding: "2px 10px", borderRadius: "4px" }}>
          {data?.status}
        </span>
        <div style={{ flex: 1 }} />
        {canDownload && (
          <button
            onClick={onDownload}
            style={{
              background: "rgba(34,211,160,0.1)", border: "1px solid rgba(34,211,160,0.25)",
              color: "var(--color-success)", padding: "5px 16px", borderRadius: "5px",
              fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer",
              display: "flex", alignItems: "center", gap: "6px",
            }}
          >
            ⬇ Download Result
          </button>
        )}
      </div>

      {/* Fields */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "8px" }}>
        {fields.map(([label, val]) => val != null && (
          <div key={label} style={{
            background: "var(--color-surface)", border: "1px solid var(--color-border)",
            borderRadius: "6px", padding: "10px 14px",
            borderLeft: label === "Status" ? `2px solid ${color}` : "1px solid var(--color-border)",
          }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--color-muted)", letterSpacing: "0.08em", marginBottom: "4px" }}>
              {label.toUpperCase()}
            </div>
            <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-text)" }}>
              {String(val)}
            </div>
          </div>
        ))}
      </div>

      {/* Error message */}
      {data?.error && (
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-error)",
          background: "rgba(244,63,94,0.07)", border: "1px solid rgba(244,63,94,0.2)",
          borderRadius: "7px", padding: "12px 16px", lineHeight: 1.6,
        }}>
          <div style={{ marginBottom: "4px", letterSpacing: "0.06em", fontSize: "9px" }}>ERROR</div>
          {data.error}
        </div>
      )}
    </div>
  );
}

// ── Router ────────────────────────────────────────────────────────────────────
export default function TopFiveOutput({ output }) {
  const { setOutput, setLoading, addLog } = useOutputStore();

  const handleAction = async (action, id, meta = {}) => {
    switch (action) {
      case "view": {
        setLoading(true);
        try {
          const data = await fetchJob(id);
          setOutput("top5-job", data, `Job #${id}`);
          addLog({ level: "info", message: `Loaded Job #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load Job #${id}` });
          setLoading(false);
        }
        break;
      }
      case "download": {
        addLog({ level: "info", message: `Downloading result for Job #${id}…` });
        try {
          const blob = await downloadResult(id);
          const stem = meta.inputFile ? meta.inputFile.replace(/\.[^.]+$/, "") : id;
          saveBlob(blob, `Audit_Result_${stem}.xlsx`);
          addLog({ level: "success", message: `Downloaded result for Job #${id}` });
        } catch (e) {
          const msg = e.response?.data?.detail || e.message;
          addLog({ level: "error", message: `Download failed: ${msg}` });
        }
        break;
      }
    }
  };

  if (output.type === "top5-upload")
    return <TopFiveUploadView initData={output.data ?? {}} />;

  if (output.type === "top5-job-list")
    return <TopFiveJobList data={output.data} onAction={handleAction} />;

  if (output.type === "top5-job")
    return (
      <TopFiveJobDetail
        data={output.data}
        onDownload={() => handleAction("download", output.data?.id, { inputFile: output.data?.input_file })}
      />
    );

  return null;
}