import { useState } from "react";
import TopNav from "../components/layout/TopNav";
import LogsPanel from "../components/layout/LogsPanel";
import ApiMenu from "../components/layout/ApiMenu";
import OutputPanel from "../components/layout/OutputPanel";
import { useOutputStore } from "../store/outputStore";
import { useAuthStore } from "../store/authStore";
import { fetchJobs } from "../services/topFiveApi";
import filterByUser from "../utils/FilterByUser";
import TopFiveOutput from "../components/top_five/TopFiveOutput"

// ── Top-Five specific menu sections ───────────────────────────────────────────
const TOP_FIVE_SECTIONS = [
  {
    label: "JOBS",
    endpoints: [
      {
        id: "top5-upload",
        label: "Upload Excel",
        method: "POST",
        path: "/top-five/upload/",
        icon: "⬆",
      },
      {
        id: "top5-job-list",
        label: "List Jobs",
        method: "GET",
        path: "/top-five/jobs/",
        icon: "≡",
        action: "list",
      },
    ],
  },
];

export default function TopFivePage() {TopFiveOutput.jsx
  const { user } = useAuthStore();
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();
  const [activeId, setActiveId] = useState(null);

  // Filter jobs to only show those created by the current user
  

  const handleSelect = async (ep) => {
    setActiveId(ep.id);

    switch (ep.id) {
      case "top5-upload":
        clearOutput();
        setOutput("top5-upload", null, "Upload Excel");
        break;

      case "top5-job-list":
        setLoading(true);
        addLog({ level: "info", message: "Fetching jobs…" });
        try {
          const data = await fetchJobs();
          const filtered = filterByUser(data);
          const count = (filtered.results || filtered).length;
          setOutput("top5-job-list", filtered, "All Jobs", { action: "view" });
          addLog({ level: "success", message: `Loaded ${count} job(s)` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <TopNav />
      <div style={{ display: "flex", flex: 1, overflow: "hidden", paddingTop: "52px" }}>
        <LogsPanel />
        <ApiMenu
          onSelect={handleSelect}
          activeId={activeId}
          sections={TOP_FIVE_SECTIONS}
        />
        <OutputPanel />
      </div>
    </div>
  );
}