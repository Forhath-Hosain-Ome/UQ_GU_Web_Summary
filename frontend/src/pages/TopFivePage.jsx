import { useState, useRef } from "react";
import TopNav from "../components/layout/TopNav";
import top_five_api from "../lib/top_five_api"; // reuse the same axios instance

// ── api calls ─────────────────────────────────────────────────────────────────
const uploadFile  = (file) => {
  const fd = new FormData();
  fd.append("file", file);

  return top_five_api.post("/upload/", fd).then((r) => r.data);
};
const pollStatus  = (jobId) => top_five_api.get(`/jobs/${jobId}/`).then((r) => r.data);
const downloadUrl = (jobId) => `/jobs/${jobId}/download/`;


// ── shared styles ─────────────────────────────────────────────────────────────
const mono = { fontFamily: "var(--font-mono)" };
const card = {
  background: "var(--color-surface)", border: "1px solid var(--color-border)",
  borderRadius: "10px", padding: "24px",
};

export default function Top5Page() {
  const [file,     setFile]     = useState(null);
  const [isDrag,   setIsDrag]   = useState(false);
  const [jobId,    setJobId]    = useState(null);
  const [status,   setStatus]   = useState(null); // PENDING | PROCESSING | DONE | FAILED
  const [error,    setError]    = useState("");
  const [busy,     setBusy]     = useState(false);
  const inputRef  = useRef(null);
  const pollRef   = useRef(null);

  const reset = () => {
    clearInterval(pollRef.current);
    setFile(null); setJobId(null); setStatus(null);
    setError(""); setBusy(false);
  };

  const pickFile = (f) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".xlsx") && !f.name.toLowerCase().endsWith(".xls")) {
      setError("Only .xlsx / .xls files are accepted."); return;
    }
    setError(""); setFile(f); setStatus(null); setJobId(null);
  };

  const handleDrop = (e) => {
    e.preventDefault(); setIsDrag(false);
    pickFile(e.dataTransfer.files?.[0]);
  };

  const startPoll = (id) => {
    pollRef.current = setInterval(async () => {
      try {
        const job = await pollStatus(id);
        setStatus(job.status);
        if (job.status === "DONE" || job.status === "FAILED") {
          clearInterval(pollRef.current);
          setBusy(false);
          if (job.status === "FAILED") setError(job.error || "Processing failed.");
        }
      } catch {
        clearInterval(pollRef.current);
        setBusy(false);
        setError("Could not reach server while polling.");
      }
    }, 1500);
  };

  const handleProcess = async () => {
    if (!file || busy) return;
    setBusy(true); setError(""); setStatus("PENDING");
    try {
      const { job_id } = await uploadFile(file);
      setJobId(job_id);
      startPoll(job_id);
    } catch (e) {
      setBusy(false); setStatus("FAILED");
      setError(e.response?.data?.detail || e.message);
    }
  };

  const handleDownload = () => {
    if (!jobId) return;
    // Trigger browser download via anchor — auth token sent via cookie/interceptor
    const a = document.createElement("a");
    a.href = downloadUrl(jobId);
    a.download = "";
    a.click();
  };

  // ── status pill ──────────────────────────────────────────────────────────────
  const STATUS_STYLE = {
    PENDING:    { color: "var(--color-muted)",    label: "Queued…"      },
    PROCESSING: { color: "var(--color-accent2)",  label: "Processing…"  },
    DONE:       { color: "var(--color-success)",  label: "Done ✓"        },
    FAILED:     { color: "var(--color-error)",    label: "Failed"        },
  };
  const pill = status ? STATUS_STYLE[status] : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <TopNav />

      <main style={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        background: "var(--color-bg)", paddingTop: "52px",
      }}>
        <div style={{ width: "100%", maxWidth: "520px", padding: "0 24px", display: "flex", flexDirection: "column", gap: "20px" }}>

          {/* Header */}
          <div>
            <h2 style={{ fontFamily: "var(--font-display)", fontSize: "20px", fontWeight: 700, margin: "0 0 6px", color: "var(--color-text)" }}>
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
              ...card,
              border: `2px dashed ${isDrag ? "var(--color-accent)" : "var(--color-border)"}`,
              background: isDrag ? "rgba(99,102,241,0.05)" : "var(--color-surface)",
              textAlign: "center", cursor: busy ? "not-allowed" : "pointer",
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
                <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--color-text)", marginBottom: "4px" }}>
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

          {/* Status */}
          {pill && (
            <div style={{
              display: "flex", alignItems: "center", gap: "10px",
              ...card, padding: "12px 16px",
            }}>
              {status === "PROCESSING" || status === "PENDING" ? (
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

          {/* Action buttons */}
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
                background: status === "DONE" ? "var(--color-success)" : "var(--color-border)",
                color: status === "DONE" ? "#fff" : "var(--color-muted)",
                border: "none", padding: "11px 0", borderRadius: "6px",
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

        </div>
      </main>

      {/* Spinner keyframe */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}