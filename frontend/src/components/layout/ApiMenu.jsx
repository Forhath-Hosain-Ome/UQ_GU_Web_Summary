import { useState } from "react";

const ENDPOINTS = [
  {
    id: "upload",
    label: "Upload PDFs",
    method: "POST",
    path: "/batches/upload/",
    icon: "⬆",
  },
  {
    id: "batch-list",
    label: "List Batches",
    method: "GET",
    path: "/batches/",
    icon: "≡",
    action: "list",
    listType: "batch",
  },
];

const METHOD_COLORS = {
  GET:  { bg: "rgba(34,211,160,0.1)",  text: "var(--color-success)" },
  POST: { bg: "rgba(99,102,241,0.12)", text: "var(--color-accent2)" },
};

export default function ApiMenu({ onSelect, activeId }) {
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
      {/* Header */}
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

      {/* Section label */}
      <div style={{ padding: "10px 16px 4px" }}>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "9px",
            fontWeight: 500,
            letterSpacing: "0.12em",
            color: "var(--color-muted)",
          }}
        >
          BATCHES
        </span>
      </div>

      {/* Endpoints */}
      <div style={{ flex: 1, overflowY: "auto", padding: "4px 8px 8px" }}>
        {ENDPOINTS.map((ep) => {
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
    </nav>
  );
}