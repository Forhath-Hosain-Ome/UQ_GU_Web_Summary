/**
 * ---------------------
 * Replaces FinalSummaryPage.jsx.
 * Follows the same shell as PumaPage / DefectImagePage:
 *   TopNav | LogsPanel | ApiMenu | OutputPanel
 *
 * ApiMenu sections:
 *   UPLOAD   → upload/
 *   BATCHES  → batches/ list, batch detail, batch logs
 *   EXPORT   → export/
 *   RETRY    → retry/search/, retry/<pk>/download/, retry/upload/
 *   SETTINGS → buyers/, factories/, pairs/  (registration)
 *
 * All stage content is rendered via OutputPanel → AuditOutput (new component).
 */

import { useState } from "react";
import TopNav        from "../components/layout/TopNav";
import LogsPanel     from "../components/layout/LogsPanel";
import ApiMenu       from "../components/layout/ApiMenu";
import OutputPanel   from "../components/layout/OutputPanel";
import { useOutputStore } from "../store/outputStore";
import { useAuthStore }   from "../store/authStore";
import {
  fetchBatches,
  fetchPairOptions,
  fetchFilterOptions,
  fetchBuyers,
  fetchFactories,
  fetchPairs,
} from "../services/finalSummaryApi";

// ── Sidebar sections ──────────────────────────────────────────────────────────
const AUDIT_SECTIONS = [
  {
    label: "UPLOAD",
    endpoints: [
      {
        id:     "audit-upload",
        label:  "Upload Excel Files",
        method: "POST",
        path:   "/upload/",
        icon:   "⬆",
      },
    ],
  },
  {
    label: "BATCHES",
    endpoints: [
      {
        id:       "audit-batch-list",
        label:    "List Batches",
        method:   "GET",
        path:     "/batches/",
        icon:     "≡",
        action:   "list",
      },
      {
        id:     "audit-batch-detail",
        label:  "Batch Detail",
        method: "GET",
        path:   "/batches/<pk>/",
        icon:   "◎",
        action: "view",
      },
      {
        id:     "audit-batch-logs",
        label:  "Batch Logs",
        method: "GET",
        path:   "/batches/<pk>/",
        icon:   "∷",
        action: "logs",
      },
    ],
  },
  {
    label: "EXPORT",
    endpoints: [
      {
        id:     "audit-export",
        label:  "Download Summary",
        method: "GET",
        path:   "/export/",
        icon:   "⬇",
      },
    ],
  },
  {
    label: "RETRY",
    endpoints: [
      {
        id:     "audit-retry-search",
        label:  "Search Blocked",
        method: "GET",
        path:   "/retry/search/",
        icon:   "⌕",
      },
      {
        id:     "audit-retry-download",
        label:  "Download Error JSON",
        method: "GET",
        path:   "/retry/<pk>/download/",
        icon:   "⬇",
        action: "download",
      },
      {
        id:     "audit-retry-upload",
        label:  "Upload Fixed JSON",
        method: "POST",
        path:   "/retry/upload/",
        icon:   "⬆",
      },
    ],
  },
  {
    label: "SETTINGS",
    endpoints: [
      {
        id:     "audit-settings-buyers",
        label:  "Manage Buyers",
        method: "GET",
        path:   "/buyers/",
        icon:   "◈",
      },
      {
        id:     "audit-settings-factories",
        label:  "Manage Factories",
        method: "GET",
        path:   "/factories/",
        icon:   "◈",
      },
      {
        id:     "audit-settings-pairs",
        label:  "Manage Pairs",
        method: "GET",
        path:   "/pairs/",
        icon:   "◈",
      },
    ],
  },
];

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AuditSummaryPage() {
  const { user }                          = useAuthStore();
  const { setOutput, setLoading, addLog, clearOutput } = useOutputStore();
  const [activeId, setActiveId]           = useState(null);

  const handleSelect = async (ep) => {
    setActiveId(ep.id);

    switch (ep.id) {

      // ── Upload ──────────────────────────────────────────────────────────
      case "audit-upload": {
        clearOutput();
        // Fetch pair options so the upload form can show a dropdown
        setLoading(true);
        addLog({ level: "info", message: "Loading pair options…" });
        try {
          const options = await fetchPairOptions();
          setOutput(
            "audit-upload",
            { options },
            "Upload Excel Files",
            { source: "audit" }
          );
          addLog({ level: "success", message: `${options.pairs.length} active pair(s) loaded` });
        } catch (e) {
          addLog({ level: "error", message: `Failed to load options: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Batch list ──────────────────────────────────────────────────────
      case "audit-batch-list": {
        setLoading(true);
        addLog({ level: "info", message: "Fetching batches…" });
        try {
          const data = await fetchBatches();
          // Non-staff: filter to own batches on the client side
          let list = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : []);
          if (!user?.is_staff && user?.user_id) {
            list = list.filter(b => b.created_by?.id === user.user_id);
          }
          setOutput("audit-batch-list", list, "All Batches", { source: "audit" });
          addLog({ level: "success", message: `Loaded ${list.length} batch(es)` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Batch detail / logs — show list first so user picks one ────────
      case "audit-batch-detail":
      case "audit-batch-logs": {
        setLoading(true);
        addLog({ level: "info", message: "Fetching batches…" });
        try {
          const data = await fetchBatches();
          let list = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : []);
          if (!user?.is_staff && user?.user_id) {
            list = list.filter(b => b.created_by?.id === user.user_id);
          }
          setOutput(
            "audit-batch-list",
            list,
            `Batches — ${ep.label}`,
            { source: "audit", action: ep.action }
          );
          addLog({ level: "success", message: `Loaded ${list.length} batch(es)` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Export ──────────────────────────────────────────────────────────
      case "audit-export": {
        clearOutput();
        setLoading(true);
        addLog({ level: "info", message: "Loading filter options…" });
        try {
          const opts = await fetchFilterOptions();
          setOutput("audit-export", { options: opts }, "Download Summary", { source: "audit" });
          addLog({ level: "success", message: "Filter options loaded" });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Retry — search blocked records ─────────────────────────────────
      case "audit-retry-search": {
        clearOutput();
        setOutput("audit-retry-search", {}, "Search Blocked Records", { source: "audit" });
        break;
      }

      // ── Retry — download error JSON (pick from batch list) ─────────────
      case "audit-retry-download": {
        setLoading(true);
        addLog({ level: "info", message: "Fetching batches for error JSON download…" });
        try {
          const data = await fetchBatches();
          let list = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : []);
          if (!user?.is_staff && user?.user_id) {
            list = list.filter(b => b.created_by?.id === user.user_id);
          }
          // Only show partial/failed batches — those that have blocked records
          const retryable = list.filter(b => 
            ["PARTIAL", "FAILED"].includes(b.status?.toUpperCase()));
          setOutput(
            "audit-batch-list",
            retryable,
            "Select Batch — Download Error JSON",
            { source: "audit", action: "retry-download" }
          );
          addLog({ level: "success", message: `${retryable.length} batch(es) with errors` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      // ── Retry — upload fixed JSON ───────────────────────────────────────
      case "audit-retry-upload": {
        clearOutput();
        setOutput("audit-retry-upload", {}, "Upload Fixed JSON", { source: "audit" });
        break;
      }

      // ── Settings ────────────────────────────────────────────────────────
      case "audit-settings-buyers":
      case "audit-settings-factories":
      case "audit-settings-pairs": {
        const settingsMap = {
          "audit-settings-buyers":    { key: "buyers",    title: "Manage Buyers" },
          "audit-settings-factories": { key: "factories", title: "Manage Factories" },
          "audit-settings-pairs":     { key: "pairs",     title: "Manage Pairs" },
        };
        const { key, title } = settingsMap[ep.id];
        clearOutput();
        setLoading(true);
        addLog({ level: "info", message: `Loading ${title.toLowerCase()}…` });
        try {
          const fetchers = { buyers: fetchBuyers, factories: fetchFactories, pairs: fetchPairs };
          const data = await fetchers[key]();
          setOutput("audit-settings", data, title, { source: "audit", settingsKey: key });
          addLog({ level: "success", message: `Loaded ${(Array.isArray(data) ? data : data?.results ?? []).length} record(s)` });
        } catch (e) {
          addLog({ level: "error", message: `Failed: ${e.message}` });
          setLoading(false);
        }
        break;
      }

      default:
        break;
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <TopNav />
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <LogsPanel />
        <ApiMenu
          onSelect={handleSelect}
          activeId={activeId}
          sections={AUDIT_SECTIONS}
        />
        <OutputPanel />
      </div>
    </div>
  );
}