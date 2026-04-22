import { useAuthStore } from "../../store/authStore";
import { useNavigate, useLocation } from "react-router-dom";
import './TopNav.css'

const SERVICES = [
  { id: "puma", label: "PUMA SUMMARY", path: "/puma" },
  { id: "defect_image", label: "Defect Image", path: "/image" },
  { id: "audit", label: "AUDIT SUMMARY", path: "/audit" },
  { id: "top_five", label: "TOP FIVE", path: "/top-five" },
  // Future services added here
];

export default function TopNav() {
  const { user, logout } = useAuthStore();
  const navigate  = useNavigate();
  const location  = useLocation();

  return (
    <header className="header" >
      {/* Logo */}
      <div className="logo" >
        QC<span style={{ color: "var(--color-muted)" }}>/</span>PLATFORM
      </div>

      {/* Service tabs */}
      <nav style={{ display: "flex", gap: "4px", flex: 1 }}>
        {SERVICES.map((s) => {
          const active = location.pathname.startsWith(s.path);
          return (
            <button className={`${styles.custom_button} ${active ? styles.active : styles.inactive}`}
              key={s.id}
              onClick={() => navigate(s.path)}
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
