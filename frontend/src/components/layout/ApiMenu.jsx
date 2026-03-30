import { useState } from "react";
import { useOutputStore } from "../../store/outputStore";

const SECTIONS = [
  {
    label: "BATCHES",
    endpoints: [
      { id: "upload",       label: "Upload PDFs",      method: "POST", path: "/batches/upload/",    icon: "⬆" },
      { id: "batch-list",   label: "List Batches",     method: "GET",  path: "/batches/",           icon: "≡" },
      { id: "batch-detail", label: "Batch Detail",     method: "GET",  path: "/batches/{id}/",      icon: "◎" },
      { id: "batch-retry",  label: "Retry Failed",     method: "POST", path: "/batches/{id}/retry/",icon: "↺" },
      { id: "batch-logs",   label: "Batch Logs",       method: "GET",  path: "/batches/{id}/logs/", icon: "∷" },
      { id: "batch-excel",  label: "Download Excel",   method: "GET",  path: "/batches/{id}/excel/",icon: "⬇" },
    ],
  },
  {
    label: "REPORTS",
    endpoints: [
      { id: "report-list",   label: "List Reports",      method: "GET", path: "/reports/",                   icon: "≡" },
      { id: "report-detail", label: "Report Detail",     method: "GET", path: "/reports/{id}/",              icon: "◎" },
      { id: "certificate",   label: "Download Cert",     method: "GET", path: "/reports/{id}/certificate/",  icon: "⬇" },
      { id: "cert-logs",     label: "Certificate Logs",  method: "GET", path: "/reports/{id}/certificates/", icon: "∷" },
    ],
  },
];

const METHOD_COLORS = {
  GET:  { bg: "rgba(34,211,160,0.1)",  text: "var(--color-success)" },
  POST: { bg: "rgba(99,102,241,0.12)", text: "var(--color-accent2)" },
};

export default function ApiMenu({ onSelect, activeId }) {
  const [collapsed, setCollapsed] = useState({});

  return (
    <nav
      style={{
        width: "260px",
        minWidth: "260px",
        background: "var(--color-surface)",
        borderRight: "1px solid var(--color-border)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Inner nav header */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid var(--color-border)",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            fontWeight: 500,
            letterSpacing: "0.1em",
            color: "var(--color-muted)",
          }}
        >
          PUMA SUMMARY · API
        </span>
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "9px",
            color: "var(--color-accent)",
            marginTop: "3px",
          }}
        >
          /api/
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "8px" }}>
        {SECTIONS.map((section) => {
          const isCollapsed = collapsed[section.label];
          return (
            <div key={section.label} style={{ marginBottom: "8px" }}>
              {/* Section header */}
              <button
                onClick={() =>
                  setCollapsed((c) => ({ ...c, [section.label]: !c[section.label] }))
                }
                style={{
                  width: "100%",
                  background: "none",
                  border: "none",
                  padding: "5px 8px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  cursor: "pointer",
                  borderRadius: "4px",
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "9px",
                    fontWeight: 500,
                    letterSpacing: "0.12em",
                    color: "var(--color-muted)",
                  }}
                >
                  {section.label}
                </span>
                <span style={{ color: "var(--color-muted)", fontSize: "9px" }}>
                  {isCollapsed ? "▶" : "▼"}
                </span>
              </button>

              {/* Endpoints */}
              {!isCollapsed &&
                section.endpoints.map((ep) => {
                  const active = activeId === ep.id;
                  const mc     = METHOD_COLORS[ep.method] || METHOD_COLORS.GET;
                  return (
                    <button
                      key={ep.id}
                      onClick={() => onSelect(ep)}
                      style={{
                        width: "100%",
                        background: active ? "var(--color-panel)" : "transparent",
                        border: active
                          ? "1px solid var(--color-border)"
                          : "1px solid transparent",
                        borderLeft: active
                          ? "2px solid var(--color-accent)"
                          : "2px solid transparent",
                        padding: "8px 10px",
                        borderRadius: "5px",
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                        cursor: "pointer",
                        marginBottom: "2px",
                        transition: "all 0.12s",
                        textAlign: "left",
                      }}
                      onMouseEnter={(e) => {
                        if (!active) e.currentTarget.style.background = "var(--color-panel)";
                      }}
                      onMouseLeave={(e) => {
                        if (!active) e.currentTarget.style.background = "transparent";
                      }}
                    >
                      {/* Method badge */}
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "8px",
                          fontWeight: 500,
                          padding: "1px 5px",
                          borderRadius: "3px",
                          background: mc.bg,
                          color: mc.text,
                          minWidth: "32px",
                          textAlign: "center",
                          letterSpacing: "0.05em",
                        }}
                      >
                        {ep.method}
                      </span>

                      {/* Icon + label */}
                      <span style={{ fontSize: "11px", opacity: 0.5 }}>{ep.icon}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          style={{
                            fontFamily: "var(--font-body)",
                            fontSize: "12px",
                            color: active ? "var(--color-text)" : "var(--color-muted)",
                            fontWeight: active ? 500 : 400,
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                        >
                          {ep.label}
                        </div>
                        <div
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "9px",
                            color: "var(--color-muted)",
                            opacity: 0.6,
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                        >
                          {ep.path}
                        </div>
                      </div>
                    </button>
                  );
                })}
            </div>
          );
        })}
      </div>
    </nav>
  );
}
