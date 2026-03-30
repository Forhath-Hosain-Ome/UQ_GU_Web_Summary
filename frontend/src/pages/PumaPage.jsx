import { useState } from "react";
import TopNav from "../components/layout/TopNav";
import LogsPanel from "../components/layout/LogsPanel";
import ApiMenu from "../components/layout/ApiMenu";
import OutputPanel from "../components/layout/OutputPanel";
import { useOutputStore } from "../store/outputStore";
import { UploadForm } from "../components/batch/BatchOutput";
import {
  fetchBatches, fetchBatch, fetchBatchLogs,
  fetchReports, fetchReport,
} from "../services/pumaApi";

// ID input modal for endpoints that need a {id}
function IdPrompt({ label, onConfirm, onCancel }) {
  const [val, setVal] = useState("");
  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200,
      }}
    >
      <div
        className="fade-up"
        style={{
          background: "var(--color-surface)", border: "1px solid var(--color-border)",
          borderRadius: "12px", padding: "28px 32px", minWidth: "300px",
          display: "flex", flexDirection: "column", gap: "14px",
        }}
      >
        <div style={{ fontFamily: "var(--font-display)", fontSize: "15px", fontWeight: 700, color: "var(--color-text)" }}>
          {label}
        </div>
        <input
          autoFocus
          placeholder="Enter ID…"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && val && onConfirm(val)}
          style={{
            background: "var(--color-panel)", border: "1px solid var(--color-border)",
            borderRadius: "6px", padding: "10px 12px", color: "var(--color-text)",
            fontFamily: "var(--font-mono)", fontSize: "13px", outline: "none",
          }}
        />
        <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
          <button onClick={onCancel} style={ghostBtn}>Cancel</button>
          <button
            onClick={() => val && onConfirm(val)}
            style={{ ...ghostBtn, background: "var(--color-accent)", color: "#fff", borderColor: "var(--color-accent)" }}
          >
            Go
          </button>
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

export default function PumaPage() {
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();
  const [activeId, setActiveId]   = useState(null);
  const [prompt, setPrompt]       = useState(null); // { label, onConfirm }

  const needsId = (label, handler) => {
    setPrompt({ label, onConfirm: (id) => { setPrompt(null); handler(id); } });
  };

  const handleSelect = async (ep) => {
    setActiveId(ep.id);

    // Endpoints that need an ID
    const idEndpoints = {
      "batch-detail": (id) => loadBatchDetail(id),
      "batch-retry":  (id) => triggerRetry(id),
      "batch-logs":   (id) => loadBatchLogs(id),
      "batch-excel":  (id) => downloadExcelById(id),
      "report-detail":(id) => loadReportDetail(id),
      "certificate":  (id) => downloadCertById(id),
      "cert-logs":    (id) => loadCertLogs(id),
    };

    if (idEndpoints[ep.id]) {
      needsId(`Enter ID for ${ep.label}`, idEndpoints[ep.id]);
      return;
    }

    // Direct endpoints
    switch (ep.id) {
      case "upload":
        clearOutput();
        setOutput("batch-progress", null, "Upload PDFs");
        break;

      case "batch-list":
        setLoading(true);
        addLog({ level: "info", message: "Fetching batch list…" });
        try {
          const data = await fetchBatches();
          setOutput("batch-list", data, "All Batches");
          addLog({ level: "success", message: `Loaded ${(data.results || data).length} batches` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;

      case "report-list":
        setLoading(true);
        addLog({ level: "info", message: "Fetching reports…" });
        try {
          const data = await fetchReports();
          setOutput("report-list", data, "All Reports");
          addLog({ level: "success", message: `Loaded ${(data.results || data).length} reports` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
    }
  };

  // ── ID-based handlers ──────────────────────────────────────────────────────

  const loadBatchDetail = async (id) => {
    setLoading(true);
    addLog({ level: "info", message: `Loading Batch #${id}…` });
    try {
      const data = await fetchBatch(id);
      setOutput("batch", data, `Batch #${id}`);
      addLog({ level: "success", message: `Batch #${id} loaded` });
    } catch (e) {
      addLog({ level: "error", message: `Batch #${id} not found` });
      setLoading(false);
    }
  };

  const triggerRetry = async (id) => {
    addLog({ level: "info", message: `Triggering retry for Batch #${id}…` });
    try {
      const { retryBatch } = await import("../services/pumaApi");
      const res = await retryBatch(id);
      addLog({ level: "success", message: `Retry started for Batch #${id} — ${res.files_retrying?.length} file(s)` });
      await loadBatchDetail(id);
    } catch (e) {
      addLog({ level: "error", message: `Retry failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  const loadBatchLogs = async (id) => {
    setLoading(true);
    addLog({ level: "info", message: `Fetching logs for Batch #${id}…` });
    try {
      const data = await fetchBatchLogs(id);
      setOutput("logs", data, `Logs · Batch #${id}`);
      addLog({ level: "info", message: `Logs loaded — ${data.total_failed} failed` });
    } catch (e) {
      addLog({ level: "error", message: `Failed to load logs for Batch #${id}` });
      setLoading(false);
    }
  };

  const downloadExcelById = async (id) => {
    addLog({ level: "info", message: `Downloading Excel for Batch #${id}…` });
    try {
      const { downloadExcel } = await import("../services/pumaApi");
      const blob = await downloadExcel(id);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = `batch-${id}.xlsx`; a.click();
      URL.revokeObjectURL(url);
      addLog({ level: "success", message: `Excel downloaded for Batch #${id}` });
    } catch (e) {
      addLog({ level: "error", message: `Excel download failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  const loadReportDetail = async (id) => {
    setLoading(true);
    addLog({ level: "info", message: `Loading Report #${id}…` });
    try {
      const data = await fetchReport(id);
      setOutput("report", data, `Report · ${data.style}`);
      addLog({ level: "success", message: `Report ${data.style} loaded` });
    } catch (e) {
      addLog({ level: "error", message: `Report #${id} not found` });
      setLoading(false);
    }
  };

  const downloadCertById = async (id) => {
    addLog({ level: "info", message: `Generating certificate for Report #${id}…` });
    try {
      const { downloadCertificate } = await import("../services/pumaApi");
      const blob = await downloadCertificate(id);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = `certificate-report-${id}.docx`; a.click();
      URL.revokeObjectURL(url);
      addLog({ level: "success", message: `Certificate downloaded for Report #${id}` });
    } catch (e) {
      addLog({ level: "error", message: `Certificate failed: ${e.response?.data?.detail || e.message}` });
    }
  };

  const loadCertLogs = async (id) => {
    setLoading(true);
    addLog({ level: "info", message: `Loading certificate logs for Report #${id}…` });
    try {
      const { fetchCertificateLogs } = await import("../services/pumaApi");
      const data = await fetchCertificateLogs(id);
      setOutput("report", { certificate_logs: data.results || data, id, style: `Report #${id}` }, `Cert Logs · #${id}`);
      addLog({ level: "info", message: `${(data.results || data).length} certificate events` });
    } catch (e) {
      addLog({ level: "error", message: `Failed to load cert logs for Report #${id}` });
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <TopNav />

      {prompt && (
        <IdPrompt
          label={prompt.label}
          onConfirm={prompt.onConfirm}
          onCancel={() => setPrompt(null)}
        />
      )}

      {/* 3-column layout below the fixed nav */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden", paddingTop: "52px" }}>
        <LogsPanel />
        <ApiMenu onSelect={handleSelect} activeId={activeId} />
        <OutputPanel />
      </div>
    </div>
  );
}
