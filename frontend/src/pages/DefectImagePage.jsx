import { useOutputStore } from "../store/outputStore";
import { useAuthStore } from "../store/authStore";
import { fetchBatches, fetchReports } from "../services/defectImageApi";
import filterByUser from "../utils/FilterByUser"
import DashboardLayout from "../components/layout/DashboardLayout";

export default function DefectImagePage() {
  const { user } = useAuthStore();
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();
  

  const handleSelect = async (ep) => {
    
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
    }
  };

  return <DashboardLayout onSelect={handleSelect} />;
}