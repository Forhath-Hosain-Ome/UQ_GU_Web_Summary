import { useAuthStore } from "../../store/authStore";
import { useNavigate, useLocation } from "react-router-dom";

const SERVICES = [
  { id: "puma", label: "PUMA SUMMARY", path: "/puma" },
  // Future services added here
];

export default function TopNav() {
  const { user, logout } = useAuthStore();
  const navigate  = useNavigate();
  const location  = useLocation();

  return (
    <header
      style={{
        background: "var(--color-surface)",
        borderBottom: "1px solid var(--color-border)",
        height: "52px",
        display: "flex",
        alignItems: "center",
        padding: "0 24px",
        gap: "32px",
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
      }}
    >
      {/* Logo */}
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 800,
          fontSize: "15px",
          letterSpacing: "0.12em",
          color: "var(--color-accent2)",
          whiteSpace: "nowrap",
        }}
      >
        QC<span style={{ color: "var(--color-muted)" }}>/</span>PLATFORM
      </div>

      {/* Service tabs */}
      <nav style={{ display: "flex", gap: "4px", flex: 1 }}>
        {SERVICES.map((s) => {
          const active = location.pathname.startsWith(s.path);
          return (
            <button
              key={s.id}
              onClick={() => navigate(s.path)}
              style={{
                background: active ? "var(--color-accent)" : "transparent",
                color: active ? "#fff" : "var(--color-muted)",
                border: "none",
                padding: "4px 14px",
                borderRadius: "4px",
                fontFamily: "var(--font-mono)",
                fontSize: "11px",
                fontWeight: 500,
                letterSpacing: "0.08em",
                cursor: "pointer",
                transition: "all 0.15s",
              }}
            >
              {s.label}
            </button>
          );
        })}
      </nav>

      {/* User info + logout */}
      {user && (
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              color: "var(--color-muted)",
            }}
          >
            {user.username || "user"}
          </span>
          <button
            onClick={() => { logout(); navigate("/login"); }}
            style={{
              background: "transparent",
              border: "1px solid var(--color-border)",
              color: "var(--color-muted)",
              padding: "3px 10px",
              borderRadius: "4px",
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              letterSpacing: "0.06em",
              cursor: "pointer",
              transition: "all 0.15s",
            }}
            onMouseEnter={(e) => {
              e.target.style.borderColor = "var(--color-error)";
              e.target.style.color = "var(--color-error)";
            }}
            onMouseLeave={(e) => {
              e.target.style.borderColor = "var(--color-border)";
              e.target.style.color = "var(--color-muted)";
            }}
          >
            LOGOUT
          </button>
        </div>
      )}
    </header>
  );
}
