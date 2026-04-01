import auth_api from "../lib/auth_api";

// ── Auth ──────────────────────────────────────────────────────────────────────
export const login = (username, password) =>
  auth_api.post("auth/token/", { username, password }).then((r) => r.data);

