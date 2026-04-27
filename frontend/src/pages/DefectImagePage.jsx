import { useState } from "react";
import TopNav from "../components/layout/TopNav";
import LogsPanel from "../components/layout/LogsPanel";
import ApiMenu from "../components/layout/ApiMenu";
import OutputPanel from "../components/layout/OutputPanel";
import { useOutputStore } from "../store/outputStore";
import { useAuthStore } from "../store/authStore";
import { fetchBatches, fetchReports } from "../services/defectImageApi";
import filterByUser from "../utils/FilterByUser"

const IMAGE_SECTIONS = [
  {
    label: "BATCHES",
    endpoints: [
      { id: "upload", label: "Upload Folders", method: "POST", path: "/folder/upload/", icon: "⬆" },
      { id: "batch-list", label: "List Batches", method: "GET", path: "/folder/batches/", icon: "≡", action: "list", listType: "batch" },
      { id: "batch-detail", label: "Batch Detail", method: "GET", path: "/folder/batches/{id}/", icon: "◎", action: "view" },
      { id: "batch-logs", label: "Batch Logs", method: "GET", path: "/folder/batches/{id}/logs/", icon: "∷", action: "logs" },
    ],
  },
  {
    label: "REPORTS",
    endpoints: [
      { id: "report-list", label: "List Reports", method: "GET", path: "/folder/reports/", icon: "≡", action: "list", listType: "report" },
      { id: "report-detail", label: "Report Detail", method: "GET", path: "/folder/reports/{id}/", icon: "◎", action: "view" },
      { id: "report-pdf", label: "Download PDF", method: "GET", path: "/folder/reports/{id}/pdf/", icon: "⬇", action: "pdf" },
      { id: "report-docx", label: "Download DOCX", method: "GET", path: "/folder/reports/{id}/docx/", icon: "⬇", action: "docx" },
    ],
  },
];

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
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} batches` );
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
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} reports` );
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
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} batches` );
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
        addLog({ level: "info", message: "Fetching reports…" );
        try {
          const data = await fetchReports();
          const filtered = filterByUser(data, user);
          setOutput("report-list", filtered, `Reports — ${ep.label}`, { action: ep.action, source: "image" });
          addLog({ level: "success", message: `Loaded ${(filtered.results || filtered).length} reports` );
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
        <ApiMenu onSelect={handleSelect} activeId={activeId} sections={IMAGE_SECTIONS} />
        <OutputPanel />
      </div>
    </div>
  );
}