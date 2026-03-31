import api from "../lib/api";

// ── Auth ──────────────────────────────────────────────────────────────────────
export const login = (username, password) =>
  api.post("/auth/token/", { username, password }).then((r) => r.data);

// ── Batches ───────────────────────────────────────────────────────────────────
export const fetchBatches = (params) =>
  api.get("/batches/", { params }).then((r) => r.data);

export const fetchBatch = (pk) =>
  api.get(`/batches/${pk}/`).then((r) => r.data);

export const uploadBatch = (files) => {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  return api.post("/batches/upload/", fd).then((r) => r.data);
};

/**
 * Retry failed PDFs for a batch.
 * @param {number} pk - Batch ID
 * @param {string[]} [filenames] - Optional list of specific filenames to retry.
 *   Omit (or pass []) to retry ALL unretried failures.
 */
export const retryBatch = (pk, filenames = []) =>
  api
    .post(`/batches/${pk}/retry/`, filenames.length ? { filenames } : {})
    .then((r) => r.data);

export const fetchBatchLogs = (pk) =>
  api.get(`/batches/${pk}/logs/`).then((r) => r.data);

export const downloadExcel = (pk) =>
  api.get(`/batches/${pk}/excel/`, { responseType: "blob" }).then((r) => r.data);

// ── Reports ───────────────────────────────────────────────────────────────────
export const fetchReports = (params) =>
  api.get("/reports/", { params }).then((r) => r.data);

export const fetchReport = (pk) =>
  api.get(`/reports/${pk}/`).then((r) => r.data);

export const downloadCertificate = (pk) =>
  api.get(`/reports/${pk}/certificate/`, { responseType: "blob" }).then((r) => r.data);

export const fetchCertificateLogs = (pk) =>
  api.get(`/reports/${pk}/certificates/`).then((r) => r.data);