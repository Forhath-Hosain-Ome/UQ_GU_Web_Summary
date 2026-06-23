import { useState } from "react";
import TopNav from "../components/layout/TopNav";
import LogsPanel from "../components/layout/LogsPanel";
import ApiMenu from "../components/layout/ApiMenu";
import OutputPanel from "../components/layout/OutputPanel";
import { useOutputStore } from "../store/outputStore";
import { useAuthStore } from "../store/authStore";
import { fetchBatches, fetchReports } from "../services/defectImageApi";
import filterByUser from "../utils/FilterByUser"

export default function DefectImagePage() {
  const { user } = useAuthStore();
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();
  const [activeId, setActiveId] = useState(null);

  const handleSelect = async (ep) => {
    setActiveId(ep.id);

    switch (ep.id) {
      // ── Direct actions ────────────────────────────────────────────────────
      case "upload":
        clearOutput();
        setOutput("batch-progress", null, "Upload Folder's", { source: "image" });
        break;

      case "batch-list":
        setLoading(true);
        addLog({ level: "info", message: "Fetching batch list…" });
        try {
          const data = await fetchBatches({ _t: Date.now() });
          const filtered = filterByUser(data, user);
          setOutput("batch-list", filtered, "All Batches", { action: "view", source: "image" });
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} batches` });
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
          const filtered = filterByUser(data, user);
          setOutput("report-list", filtered, "All Reports", { action: "view", source: "image" });
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} reports` });
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
          const filtered = filterByUser(data, user);
          setOutput("batch-list", filtered, `Batches — ${ep.label}`, { action: ep.action, source: "image" });
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} batches` });
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
          const filtered = filterByUser(data, user);
          setOutput("report-list", filtered, `Reports — ${ep.label}`, { action: ep.action, source: "image" });
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} reports` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <TopNav />
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <LogsPanel />
        <ApiMenu onSelect={handleSelect} activeId={activeId} />
        <OutputPanel />
      </div>
    </div>
  );
}