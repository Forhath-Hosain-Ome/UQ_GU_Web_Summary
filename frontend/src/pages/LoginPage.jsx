import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { useAuthStore } from "../store/authStore";
import { login } from "../services/pumaApi";

export default function LoginPage() {
  const navigate  = useNavigate();
  const authLogin = useAuthStore((s) => s.login);
  const [error, setError]   = useState("");
  const [loading, setLoading] = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm();

  const onSubmit = async ({ username, password }) => {
    setError("");
    setLoading(true);
    try {
      const { access, refresh } = await login(username, password);
      authLogin(access, refresh);
      navigate("/puma");
    } catch (e) {
      const responseData = e.response?.data;
      const message =
        responseData?.detail ||
        (responseData && typeof responseData === "string" ? responseData : JSON.stringify(responseData)) ||
        e.message ||
        "Invalid credentials.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "var(--color-bg)",
      }}
    >
      {/* Top bar */}
      <header
        style={{
          height: "52px",
          background: "var(--color-surface)",
          borderBottom: "1px solid var(--color-border)",
          display: "flex",
          alignItems: "center",
          padding: "0 24px",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 800,
            fontSize: "15px",
            letterSpacing: "0.12em",
            color: "var(--color-accent2)",
          }}
        >
          QC<span style={{ color: "var(--color-muted)" }}>/</span>PLATFORM
        </span>
      </header>

      {/* Login card */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          className="fade-up"
          style={{
            width: "100%",
            maxWidth: "380px",
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "14px",
            padding: "40px 36px",
          }}
        >
          {/* Header */}
          <div style={{ marginBottom: "32px" }}>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "10px",
                letterSpacing: "0.14em",
                color: "var(--color-accent)",
                marginBottom: "8px",
              }}
            >
              AUTHENTICATION REQUIRED
            </div>
            <h1
              style={{
                fontFamily: "var(--font-display)",
                fontSize: "24px",
                fontWeight: 800,
                margin: 0,
                color: "var(--color-text)",
                letterSpacing: "-0.01em",
              }}
            >
              Sign In
            </h1>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <Field label="USERNAME" error={errors.username?.message}>
              <input
                {...register("username", { required: "Username is required" })}
                placeholder="your_username"
                autoComplete="username"
                style={inputStyle}
              />
            </Field>

            <Field label="PASSWORD" error={errors.password?.message}>
              <input
                {...register("password", { required: "Password is required" })}
                type="password"
                placeholder="••••••••"
                autoComplete="current-password"
                style={inputStyle}
              />
            </Field>

            {error && (
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "11px",
                  color: "var(--color-error)",
                  background: "rgba(244,63,94,0.08)",
                  border: "1px solid rgba(244,63,94,0.2)",
                  padding: "8px 12px",
                  borderRadius: "5px",
                }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                marginTop: "8px",
                background: loading ? "var(--color-border)" : "var(--color-accent)",
                color: loading ? "var(--color-muted)" : "#fff",
                border: "none",
                padding: "12px",
                borderRadius: "7px",
                fontFamily: "var(--font-display)",
                fontSize: "14px",
                fontWeight: 700,
                letterSpacing: "0.08em",
                cursor: loading ? "not-allowed" : "pointer",
                transition: "all 0.15s",
              }}
            >
              {loading ? "SIGNING IN…" : "SIGN IN"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function Field({ label, error, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
      <label
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "9px",
          letterSpacing: "0.1em",
          color: "var(--color-muted)",
        }}
      >
        {label}
      </label>
      {children}
      {error && (
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-error)" }}>
          {error}
        </span>
      )}
    </div>
  );
}

const inputStyle = {
  background: "var(--color-panel)",
  border: "1px solid var(--color-border)",
  borderRadius: "6px",
  padding: "10px 12px",
  color: "var(--color-text)",
  fontFamily: "var(--font-mono)",
  fontSize: "13px",
  outline: "none",
  width: "100%",
  transition: "border-color 0.15s",
};
