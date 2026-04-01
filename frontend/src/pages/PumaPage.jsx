import { useState } from "react";
import TopNav from "../components/layout/TopNav";
import LogsPanel from "../components/layout/LogsPanel";
import ApiMenu from "../components/layout/ApiMenu";
import OutputPanel from "../components/layout/OutputPanel";
import { useOutputStore } from "../store/outputStore";
import { fetchBatches, fetchReports } from "../services/pumaApi";

export default function PumaPage() {
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();
  const [activeId, setActiveId] = useState(null);

  const handleSelect = async (ep) => {
    setActiveId(ep.id);

    switch (ep.id) {
      // ── Direct actions ────────────────────────────────────────────────────
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

      // ── Batch endpoints — show list with action embedded ──────────────────
      case "batch-detail":
      case "batch-retry":
      case "batch-logs":
      case "batch-excel": {
        setLoading(true);
        addLog({ level: "info", message: "Fetching batch list…" });
        try {
          const data = await fetchBatches();
          setOutput("batch-list", data, `Batches — ${ep.label}`, { action: ep.action });
          addLog({ level: "success", message: `Loaded ${(data.results || data).length} batches` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Report endpoints — show list with action embedded ─────────────────
      // "certificate" action now triggers both PDF + DOCX download in ReportOutput
      case "report-detail":
      case "certificate":
      case "cert-logs": {
        setLoading(true);
        addLog({ level: "info", message: "Fetching reports…" });
        try {
          const data = await fetchReports();
          setOutput("report-list", data, `Reports — ${ep.label}`, { action: ep.action });
          addLog({ level: "success", message: `Loaded ${(data.results || data).length} reports` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <TopNav />
      <div style={{ display: "flex", flex: 1, overflow: "hidden", paddingTop: "52px" }}>
        <LogsPanel />
        <ApiMenu onSelect={handleSelect} activeId={activeId} />
        <OutputPanel />
      </div>
    </div>
  );
}