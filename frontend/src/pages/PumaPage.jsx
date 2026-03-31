import { useState } from "react";
import TopNav from "../components/layout/TopNav";
import LogsPanel from "../components/layout/LogsPanel";
import ApiMenu from "../components/layout/ApiMenu";
import OutputPanel from "../components/layout/OutputPanel";
import { useOutputStore } from "../store/outputStore";
import { UploadForm } from "../components/batch/BatchOutput";
import {
  fetchBatches, fetchBatch, fetchBatchLogs, retryBatch, downloadExcel,
  fetchReports, fetchReport, downloadCertificate, fetchCertificateLogs,
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

  const handleSelect = async (ep) => {
    setActiveId(ep.id);

    // Direct endpoints (no ID needed)
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
          setOutput("batch-list", data, "All Batches", { action: "view" });
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
          setOutput("report-list", data, "All Reports", { action: "view" });
          addLog({ level: "success", message: `Loaded ${(data.results || data).length} reports` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;

      // Endpoints that need selection from a list
      case "batch-detail":
      case "batch-retry":
      case "batch-logs":
      case "batch-excel":
        // Show batch list with the appropriate action
        setLoading(true);
        addLog({ level: "info", message: "Fetching batch list…" });
        try {
          const data = await fetchBatches();
          const action = ep.action; // view, retry, logs, excel
          setOutput("batch-list", data, `Batches - ${ep.label}`, { action });
          addLog({ level: "success", message: `Loaded ${(data.results || data).length} batches` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;

      case "report-detail":
      case "certificate":
      case "cert-logs":
        // Show report list with the appropriate action
        setLoading(true);
        addLog({ level: "info", message: "Fetching reports…" });
        try {
          const data = await fetchReports();
          const action = ep.action; // view, certificate, cert-logs
          setOutput("report-list", data, `Reports - ${ep.label}`, { action });
          addLog({ level: "success", message: `Loaded ${(data.results || data).length} reports` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
    }
  };

  // ── List-based handlers ──────────────────────────────────────────────────────

  const handleBatchAction = async (id, action) => {
    switch (action) {
      case "view":
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
        break;
      case "retry":
        addLog({ level: "info", message: `Triggering retry for Batch #${id}…` });
        try {
          const res = await retryBatch(id);
          addLog({ level: "success", message: `Retry started for Batch #${id} — ${res.files_retrying?.length} file(s)` });
          // Also load batch detail after retry
          setLoading(true);
          const data = await fetchBatch(id);
          setOutput("batch", data, `Batch #${id}`);
        } catch (e) {
          addLog({ level: "error", message: `Retry failed: ${e.response?.data?.detail || e.message}` });
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
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = `batch-${id}.xlsx`; a.click();
          URL.revokeObjectURL(url);
          addLog({ level: "success", message: `Excel downloaded for Batch #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Excel download failed: ${e.response?.data?.detail || e.message}` });
        }
        break;
    }
  };

  const handleReportAction = async (id, action) => {
    switch (action) {
      case "view":
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
        break;
      case "certificate":
        addLog({ level: "info", message: `Generating certificate for Report #${id}…` });
        try {
          const blob = await downloadCertificate(id);
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url; a.download = `certificate-report-${id}.docx`; a.click();
          URL.revokeObjectURL(url);
          addLog({ level: "success", message: `Certificate downloaded for Report #${id}` });
        } catch (e) {
          addLog({ level: "error", message: `Certificate failed: ${e.response?.data?.detail || e.message}` });
        }
        break;
      case "cert-logs":
        setLoading(true);
        try {
          const data = await fetchCertificateLogs(id);
          setOutput("report", { certificate_logs: data.results || data, id, style: `Report #${id}` }, `Cert Logs · #${id}`);
          addLog({ level: "info", message: `${(data.results || data).length} certificate events` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load cert logs for Report #${id}` });
          setLoading(false);
        }
        break;
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <TopNav />

      {/* 3-column layout below the fixed nav */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden", paddingTop: "52px" }}>
        <LogsPanel />
        <ApiMenu onSelect={handleSelect} activeId={activeId} />
        <OutputPanel />
      </div>
    </div>
  );
}
